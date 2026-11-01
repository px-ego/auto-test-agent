from copy import deepcopy
from types import SimpleNamespace
import threading

import pytest

from conftest import wait_for_worker
from engine.intent_converter import IntentConverter
from engine.workflow import WorkflowConflict


def new_task(h, intent):
    return h.workflow.create("test_station", [], IntentConverter(h.registry).convert(intent))


def test_persistent_review_and_execution_gate(harness, intent):
    h = harness()
    task = new_task(h, intent)
    assert task["state"] == "awaiting_review"
    assert h.skill.calls == 0
    h.service.close()
    restored = harness()
    assert restored.service.get_state()["task_id"] == task["task_id"]
    assert restored.service.get_state()["state"] == "awaiting_review"
    approved = restored.service.review_plan(task["task_id"], 1, True, "Reviewed")
    assert approved["state"] == "approved"
    assert approved["reviews"][0]["comment"] == "Reviewed"
    assert restored.skill.calls == 0
    restored.service.close()
    restarted = harness()
    assert restarted.service.get_state()["approval"]["approved"] is True
    restarted.service.start_test(task_id=task["task_id"], revision=1)
    wait_for_worker(restarted.service)
    final = restarted.service.get_state()
    assert final["state"] == "done"
    assert restarted.skill.calls == 1
    assert final["results"]["summary"]["passed"] == 1
    assert (restarted.root / "reports" / f"report_{final['report_id']}.md").is_file()


def test_edited_plan_invalidates_approval_and_rejects_stale_review(harness, intent):
    h = harness()
    task = new_task(h, intent)
    h.service.review_plan(task["task_id"], 1, True)
    plan = deepcopy(task["plan"])
    plan["variables"]["operator_note"] = "new"
    edited = h.service.update_plan(plan, 1, task["task_id"])
    assert edited["revision"] == 2
    assert edited["approval"] is None
    assert len(edited["reviews"]) == 1
    for revision in (None, 1, 2):
        with pytest.raises(WorkflowConflict):
            h.service.start_test(task_id=task["task_id"], revision=revision)
    with pytest.raises(WorkflowConflict):
        h.service.review_plan(task["task_id"], 1, True)
    assert h.service.review_plan(task["task_id"], 2, True)["state"] == "approved"


def test_reject_is_persistent_and_cannot_execute(harness, intent):
    h = harness()
    task = new_task(h, intent)
    h.service.review_plan(task["task_id"], 1, False, "Missing checks")
    h.service.close()
    restored = harness()
    assert restored.service.get_state()["state"] == "rejected"
    with pytest.raises(WorkflowConflict):
        restored.service.start_test(task_id=task["task_id"], revision=1)
    assert restored.skill.calls == 0


def test_report_retry_after_restart_does_not_execute_hardware_again(harness, intent):
    def unavailable(*args):
        raise RuntimeError("Model offline")
    h = harness(reporter=SimpleNamespace(generate_report=unavailable))
    task = new_task(h, intent)
    h.service.review_plan(task["task_id"], 1, True)
    h.service.start_test(task_id=task["task_id"], revision=1)
    wait_for_worker(h.service)
    assert h.service.get_state()["state"] == "report_failed"
    assert h.skill.calls == 1
    h.service.close()
    restored = harness()
    restored.service.retry_report(task["task_id"])
    wait_for_worker(restored.service)
    assert restored.service.get_state()["state"] == "done"
    assert restored.skill.calls == 0


def test_rejected_plan_can_be_revised_without_losing_review_history(harness, intent):
    h = harness()
    task = new_task(h, intent)
    h.service.review_plan(task["task_id"], 1, False, "Needs revision")
    edited = h.service.update_plan(task["plan"], 1, task["task_id"])
    assert edited["state"] == "awaiting_review" and edited["revision"] == 2
    assert edited["reviews"][0]["approved"] is False
    h.service.review_plan(task["task_id"], 2, True)
    assert len(h.service.get_state()["reviews"]) == 2


def test_crashed_execution_is_not_automatically_replayed(harness, intent):
    h = harness()
    task = new_task(h, intent)
    h.service.review_plan(task["task_id"], 1, True)
    h.workflow._set_status(task["task_id"], "executing")
    h.service.close()
    restored = harness()
    assert restored.service.get_state()["state"] == "execution_uncertain"
    with pytest.raises(WorkflowConflict):
        restored.service.start_test(task_id=task["task_id"], revision=1)
    assert restored.skill.calls == 0


def test_restart_reconciles_review_checkpoint_before_status_update(harness, intent):
    h = harness()
    task = new_task(h, intent)
    h.service.review_plan(task["task_id"], 1, True)
    h.workflow._set_status(task["task_id"], "awaiting_review")
    h.service.close()
    restored = harness()
    assert restored.service.get_state()["state"] == "approved"
    assert restored.skill.calls == 0
    restored.service.start_test(task_id=task["task_id"], revision=1)
    wait_for_worker(restored.service)
    assert restored.skill.calls == 1


def test_restart_at_execution_boundary_requires_manual_recovery(harness, intent):
    h = harness()
    task = new_task(h, intent)
    h.service.review_plan(task["task_id"], 1, True)
    h.workflow.graph.update_state(h.workflow._config(task["task_id"]), {}, as_node="execution_gate")
    h.service.close()
    restored = harness()
    assert restored.service.get_state()["state"] == "execution_uncertain"
    assert restored.skill.calls == 0


def test_busy_job_rejects_duplicate_start_and_reset(harness, intent):
    h = harness()
    task = new_task(h, intent)
    h.service.review_plan(task["task_id"], 1, True)
    entered, release = threading.Event(), threading.Event()
    execute = h.skill.execute
    def slow(params):
        entered.set()
        assert release.wait(timeout=5)
        return execute(params)
    h.skill.execute = slow
    h.service.start_test(task_id=task["task_id"], revision=1)
    assert entered.wait(timeout=5)
    try:
        with pytest.raises(WorkflowConflict):
            h.service.start_test(task_id=task["task_id"], revision=1)
        with pytest.raises(WorkflowConflict):
            h.service.reset()
    finally:
        release.set()
    wait_for_worker(h.service)
    assert h.skill.calls == 1
