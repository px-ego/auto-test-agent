from copy import deepcopy
import json
import socket
from types import SimpleNamespace

import pytest
from langgraph.types import Command

from conftest import wait_for_worker
from engine.config import DiagnosticsConfig
from engine.diagnostic_tools import DiagnosticTools, redact
from engine.intent_converter import IntentConverter


class ScriptedChat:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []
        self.contexts = []
        self.cancelled = False

    def set_system_prompt(self, prompt):
        self.prompts.append(prompt)

    def ask(self, message, on_progress=None, timeout=None):
        self.contexts.append(json.loads(message))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response(on_progress)
        return response if isinstance(response, str) else json.dumps(response)

    def cancel(self):
        self.cancelled = True


def tool(name="read_execution_log", arguments=None):
    return {"action": "call_tool", "tool": name, "arguments": arguments or {},
            "reason": "Inspect the recorded evidence before drawing a conclusion"}


def final(evidence_ids=None):
    return {"action": "conclude", "conclusion": {
        "summary": "Device check failed; verify the connection using the recorded evidence.",
        "confidence": "low", "findings": [{"cause": "Connection may be unavailable",
        "evidence_ids": evidence_ids or ["failure-1", "check-1"]}],
        "recommendations": ["Inspect the device connection manually before any restart."]}}


def start_failed(h, intent):
    h.skill.result = {"success": False, "error": "device probe failed", "output": "no response"}
    task = h.workflow.create("test_station", [], IntentConverter(h.registry).convert(intent))
    h.service.review_plan(task["task_id"], 1, True)
    h.service.start_test(task_id=task["task_id"], revision=1)
    wait_for_worker(h.service)
    return h.service.get_state()


def test_evidence_drives_next_decision_and_report_preserves_failure(harness, intent):
    chat = ScriptedChat([tool(), final()])
    h = harness(diagnostic_chat=chat)
    state = start_failed(h, intent)
    diagnosis = state["diagnosis"]
    assert state["state"] == "done"
    assert state["results"]["summary"] == {"total": 1, "passed": 0, "failed": 1}
    assert h.skill.calls == 1
    assert diagnosis["status"] == "completed"
    assert diagnosis["tool_calls"] == 1 and diagnosis["rounds"] == 2
    assert chat.contexts[1]["evidence"][-1]["id"] == "check-1"
    assert "no response" in chat.contexts[1]["evidence"][-1]["content"]
    assert "失败诊断" in state["report"] and "check-1" in state["report"]
    assert any(event["type"] == "diagnosis_updated" for event in h.events)
    assert state["results"]["results"][0]["skill"] == "probe"


def test_unknown_and_unsafe_tools_are_blocked(harness, intent, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("unsafe tool or network call executed")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    chat = ScriptedChat([tool("power_off"), tool("check_tcp_port", {"target": "host", "port": 22}),
                         tool("read_execution_log", {"path": "C:/secret.txt"}), final(["failure-1"])])
    h = harness(diagnostic_chat=chat)
    state = start_failed(h, intent)
    assert [event["success"] for event in state["diagnosis"]["evidence"][1:]] == [False, False, False]
    assert all(turn["status"] == "blocked" for turn in state["diagnosis"]["trace"])
    assert h.skill.calls == 1


@pytest.mark.parametrize("responses,config", [
    ([tool(), tool()], DiagnosticsConfig(max_rounds=2, max_tool_calls=1)),
    (["invalid JSON", "invalid JSON"], DiagnosticsConfig(max_rounds=2)),
])
def test_budget_exhaustion_finishes_without_reexecuting_test(harness, intent, responses, config):
    h = harness(diagnostic_chat=ScriptedChat(responses), diagnostics=config)
    state = start_failed(h, intent)
    assert state["diagnosis"]["status"] == "limited"
    assert state["diagnosis"]["rounds"] <= config.max_rounds
    assert state["diagnosis"]["tool_calls"] <= config.max_tool_calls
    assert state["state"] == "done" and h.skill.calls == 1


def test_duplicate_check_is_not_run_twice(harness, intent):
    h = harness(diagnostic_chat=ScriptedChat([tool(), tool(), final()]))
    state = start_failed(h, intent)
    assert state["diagnosis"]["evidence"][-1]["success"] is False
    assert "duplicate" in state["diagnosis"]["evidence"][-1]["content"]


def test_fabricated_evidence_is_rejected(harness, intent):
    chat = ScriptedChat([final(["invented-proof"]), final(["failure-1"])])
    h = harness(diagnostic_chat=chat)
    state = start_failed(h, intent)
    assert state["diagnosis"]["rounds"] == 2
    assert state["diagnosis"]["trace"][0]["status"] == "blocked"
    assert "invented-proof" not in json.dumps(state["diagnosis"]["conclusion"])


def test_model_unavailable_does_not_lose_test_results(harness, intent):
    h = harness(diagnostic_chat=ScriptedChat([ConnectionError("offline")]))
    state = start_failed(h, intent)
    assert state["diagnosis"]["status"] == "unavailable"
    assert state["diagnosis"]["conclusion"]["confidence"] == "low"
    assert state["results"]["summary"]["failed"] == 1 and state["report"]


def test_expired_deadline_prevents_model_calls(harness, intent):
    chat = ScriptedChat([])
    h = harness(diagnostic_chat=chat)
    h.diagnostician.remaining = lambda diagnosis: -1
    state = start_failed(h, intent)
    assert state["diagnosis"]["status"] == "limited"
    assert chat.contexts == []


def test_disabled_diagnostics_and_successful_plans_skip_model(harness, intent):
    chat = ScriptedChat([])
    h = harness(diagnostic_chat=chat, diagnostics=DiagnosticsConfig(enabled=False))
    state = start_failed(h, intent)
    assert state["diagnosis"] is None and chat.contexts == []


def test_tcp_check_uses_only_approved_target_and_allowed_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        config = DiagnosticsConfig(allowed_ports=[port])
        tools = DiagnosticTools({"variables": {"ip": "127.0.0.1"}}, {"results": []}, config)
        result = tools.invoke("check_tcp_port", {"target": "ip", "port": port})
        assert result["reachable"] is True
        assert "127.0.0.1" not in json.dumps(result)
        for arguments in ({"target": "ip", "port": 22}, {"target": "host", "port": port},
                          {"target": "ip", "port": port, "host": "8.8.8.8"}):
            with pytest.raises(ValueError):
                tools.invoke("check_tcp_port", arguments)


def test_serial_tool_only_enumerates(monkeypatch):
    from engine import diagnostic_tools
    monkeypatch.setattr(diagnostic_tools, "comports", lambda: [SimpleNamespace(device="COM7", description="test adapter")])
    tools = DiagnosticTools({}, {"results": []}, DiagnosticsConfig())
    assert tools.invoke("list_serial_ports", {})["ports"][0]["device"] == "COM7"


def test_logs_are_bounded_redacted_and_never_read_files():
    results = {"results": [{"name": "probe", "error": "password=test-secret 192.0.2.1",
                            "output": "x" * 20000}]}
    tools = DiagnosticTools({}, results, DiagnosticsConfig(output_chars=1000))
    output = tools.invoke("read_execution_log", {"tail_lines": 2})
    assert len(json.dumps(output, ensure_ascii=False)) < 1300
    assert "test-secret" not in json.dumps(output)
    assert redact({"api_key": "secret-value"})["api_key"] == "[已脱敏]"


def test_restarts_continue_diagnostics_without_rerunning_hardware(harness, intent):
    h = harness(diagnostic_chat=ScriptedChat([tool()]))
    h.skill.result = {"success": False, "error": "probe failed"}
    task = h.workflow.create("test_station", [], IntentConverter(h.registry).convert(intent))
    h.service.review_plan(task["task_id"], 1, True)
    h.workflow.graph.invoke(Command(resume={"start": True, "revision": 1}),
                            h.workflow._config(task["task_id"]), interrupt_after=["diagnostic_tool"])
    assert h.skill.calls == 1
    h.service.close()
    chat = ScriptedChat([final()])
    restored = harness(diagnostic_chat=chat)
    assert restored.service.get_state()["state"] == "diagnostic_failed"
    restored.service.resume_diagnosis(task["task_id"])
    wait_for_worker(restored.service)
    state = restored.service.get_state()
    assert state["state"] == "done"
    assert state["diagnosis"]["tool_calls"] == 1
    assert chat.contexts[0]["evidence"][-1]["id"] == "check-1"
    assert restored.skill.calls == 0


def test_report_retry_preserves_diagnosis_without_new_checks(harness, intent):
    def unavailable(*args):
        raise ConnectionError("report model offline")
    h = harness(diagnostic_chat=ScriptedChat([tool(), final()]), reporter=SimpleNamespace(generate_report=unavailable))
    state = start_failed(h, intent)
    assert state["state"] == "report_failed"
    h.service.close()
    chat = ScriptedChat([])
    restored = harness(diagnostic_chat=chat)
    restored.service.retry_report(state["task_id"])
    wait_for_worker(restored.service)
    assert restored.service.get_state()["diagnosis"]["status"] == "completed"
    assert chat.contexts == [] and restored.skill.calls == 0


def test_stop_diagnostics_preserves_failed_test_and_generates_report(harness, intent):
    import threading
    entered, release = threading.Event(), threading.Event()
    def slow(on_progress):
        entered.set()
        assert release.wait(timeout=5)
        return final(["failure-1"])
    chat = ScriptedChat([slow])
    h = harness(diagnostic_chat=chat)
    h.skill.result = {"success": False, "error": "probe failed"}
    task = h.workflow.create("test_station", [], IntentConverter(h.registry).convert(intent))
    h.service.review_plan(task["task_id"], 1, True)
    h.service.start_test(task_id=task["task_id"], revision=1)
    assert entered.wait(timeout=5)
    h.service.stop_test()
    release.set()
    wait_for_worker(h.service)
    state = h.service.get_state()
    assert chat.cancelled
    assert state["diagnosis"]["status"] == "stopped"
    assert state["results"]["summary"]["failed"] == 1
    assert state["state"] == "done" and h.skill.calls == 1


@pytest.mark.parametrize("result", [{"success": False, "error": "invalid args"}, {"success": True, "passed": False, "reading": 0}])
def test_runner_propagates_action_and_business_failures(harness, intent, result):
    h = harness(diagnostic_chat=ScriptedChat([final(["failure-1"])]))
    h.skill.result = result
    task = h.workflow.create("test_station", [], IntentConverter(h.registry).convert(intent))
    h.service.review_plan(task["task_id"], 1, True)
    h.service.start_test(task_id=task["task_id"], revision=1)
    wait_for_worker(h.service)
    state = h.service.get_state()
    assert state["results"]["summary"]["failed"] == 1
    assert state["diagnosis"]["failure_count"] == 1
    assert h.skill.calls == 1
