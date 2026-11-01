"""Checkpointed test lifecycle. Hardware execution is never replayed on startup."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
import sqlite3
import threading
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from engine.intent_schema import validate_plan
from engine.diagnostic_tools import failure_records
from engine.diagnostician import diagnosis_markdown


class WorkflowConflict(ValueError):
    pass


class TaskNotFound(LookupError):
    pass


class TaskState(TypedDict, total=False):
    task_id: str
    instruction: str
    station: str
    knowledge_texts: list[str]
    plan: dict
    revision: int
    status: str
    approval: dict | None
    reviews: list[dict]
    results: Any
    report: str | None
    report_id: str | None
    diagnosis: dict | None
    diagnostic_action: dict


def _now():
    return datetime.now(timezone.utc).isoformat()


def _digest(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class TestWorkflow:
    def __init__(self, agent, database_path: str, reports_dir: str):
        self.agent = agent
        self.reports_dir = reports_dir
        os.makedirs(os.path.dirname(os.path.abspath(database_path)), exist_ok=True)
        self._db = sqlite3.connect(database_path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS test_tasks (
                task_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, status TEXT NOT NULL, error TEXT
            );
            CREATE TABLE IF NOT EXISTS workflow_meta (key TEXT PRIMARY KEY, value TEXT);
        """)
        self._db.commit()
        self._db_lock = threading.RLock()
        self._checkpoint_db = sqlite3.connect(database_path, check_same_thread=False)
        self.checkpointer = SqliteSaver(self._checkpoint_db)
        builder = StateGraph(TaskState)
        builder.add_node("prepare", self._prepare)
        builder.add_node("review", self._review)
        builder.add_node("execution_gate", self._execution_gate)
        builder.add_node("execute", self._execute)
        builder.add_node("diagnostic_prepare", self._diagnostic_prepare)
        builder.add_node("diagnostic_decide", self._diagnostic_decide)
        builder.add_node("diagnostic_tool", self._diagnostic_tool)
        builder.add_node("diagnostic_finish", self._diagnostic_finish)
        builder.add_node("report", self._report)
        builder.add_edge(START, "prepare")
        builder.add_edge("prepare", "review")
        builder.add_conditional_edges("review", lambda state: state["status"],
                                      {"approved": "execution_gate", "rejected": END})
        builder.add_edge("execution_gate", "execute")
        builder.add_conditional_edges("execute", self._after_execution,
                                      {"diagnose": "diagnostic_prepare", "report": "report"})
        builder.add_edge("diagnostic_prepare", "diagnostic_decide")
        builder.add_conditional_edges("diagnostic_decide", lambda state: state["diagnostic_action"]["action"],
                                      {"call_tool": "diagnostic_tool", "retry": "diagnostic_decide",
                                       "finish": "diagnostic_finish"})
        builder.add_conditional_edges("diagnostic_tool", lambda state: state["diagnosis"]["status"],
                                      {"running": "diagnostic_decide", "limited": "diagnostic_finish",
                                       "stopped": "diagnostic_finish"})
        builder.add_edge("diagnostic_finish", "report")
        builder.add_edge("report", END)
        self.graph = builder.compile(checkpointer=self.checkpointer)
        self._closed = False
        # A crash during a hardware node leaves an uncertain physical outcome.
        for task in self.list_tasks():
            snapshot = self.graph.get_state(self._config(task["task_id"]))
            values = snapshot.values
            if task["state"] in ("executing", "diagnosing", "reporting", "planning"):
                if values.get("status") in ("done", "stopped"):
                    self._set_status(task["task_id"], values["status"])
                elif values.get("results") is not None:
                    if any(node.startswith("diagnostic_") for node in snapshot.next):
                        self._set_status(task["task_id"], "diagnostic_failed", "服务重启，可继续只读诊断")
                    else:
                        self._set_status(task["task_id"], "report_failed", "服务重启，可重试报告生成")
                elif task["state"] == "planning" and values.get("status") == "awaiting_review":
                    self._drive(task["task_id"], None)
                else:
                    status = "execution_uncertain" if task["state"] == "executing" else "error"
                    self._set_status(task["task_id"], status, "服务中断，任务未自动重放，请检查设备后创建新任务")
            elif task["state"] in ("awaiting_review", "approved"):
                if snapshot.next == ("execute",):
                    self._set_status(task["task_id"], "execution_uncertain", "启动过程被中断，请检查设备后创建新任务")
                elif values.get("status") in ("awaiting_review", "approved"):
                    # Complete only review/gate bookkeeping, never hardware execution.
                    self._drive(task["task_id"], None)
                elif values.get("status") == "rejected":
                    self._set_status(task["task_id"], "rejected")

    @staticmethod
    def _config(task_id):
        return {"configurable": {"thread_id": task_id}, "recursion_limit": 64}

    @property
    def current_id(self):
        with self._db_lock:
            row = self._db.execute("SELECT value FROM workflow_meta WHERE key='current'").fetchone()
        return row[0] if row else None

    def select(self, task_id):
        self.get_task(task_id)
        with self._db_lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO workflow_meta VALUES ('current', ?)", (task_id,))

    def clear_current(self):
        with self._db_lock, self._db:
            self._db.execute("DELETE FROM workflow_meta WHERE key='current'")

    def _set_status(self, task_id, status, error=None):
        with self._db_lock, self._db:
            self._db.execute("UPDATE test_tasks SET status=?, error=?, updated_at=? WHERE task_id=?",
                             (status, error, _now(), task_id))
        self.agent.event_bus.emit({"type": "task_progress", "task_id": task_id, "state": status})

    def list_tasks(self):
        with self._db_lock:
            ids = self._db.execute("SELECT task_id FROM test_tasks ORDER BY updated_at DESC").fetchall()
        return [self.get_task(row[0], summary=True) for row in ids]

    def get_task(self, task_id=None, summary=False):
        task_id = task_id or self.current_id
        if not task_id:
            return None
        with self._db_lock:
            row = self._db.execute("SELECT created_at, updated_at, status, error FROM test_tasks WHERE task_id=?",
                                   (task_id,)).fetchone()
        if not row:
            raise TaskNotFound("任务不存在")
        snapshot = self.graph.get_state(self._config(task_id))
        values = snapshot.values
        task = {"task_id": task_id, "created_at": row[0], "updated_at": row[1],
                "state": row[2], "error": row[3], "revision": values.get("revision", 1),
                "name": (values.get("plan") or {}).get("name", "新测试任务"),
                "approval": values.get("approval"), "reviews": values.get("reviews", [])}
        if not summary:
            task.update({key: deepcopy(values.get(key)) for key in
                         ("plan", "results", "report", "report_id", "knowledge_texts", "station", "diagnosis")})
        return task

    def create(self, station, knowledge_texts, plan=None, instruction=""):
        if plan is not None:
            plan = validate_plan(plan, self.agent.skill_registry)
        task_id = uuid4().hex
        with self._db_lock, self._db:
            self._db.execute("INSERT INTO test_tasks VALUES (?, ?, ?, 'planning', NULL)",
                             (task_id, _now(), _now()))
        self.select(task_id)
        self._drive(task_id, {"task_id": task_id, "station": station,
                             "knowledge_texts": list(knowledge_texts), "plan": plan,
                             "instruction": instruction, "revision": 1, "approval": None,
                             "reviews": [], "results": None, "report": None, "report_id": None, "diagnosis": None})
        return self.get_task(task_id)

    def edit(self, plan, revision):
        if type(revision) is not int:
            raise WorkflowConflict("请提供计划版本")
        task = self._expect({"awaiting_review", "approved", "rejected"}, revision)
        plan = validate_plan(plan, self.agent.skill_registry)
        if plan == task["plan"] and task["state"] != "rejected":
            return task
        self.graph.update_state(self._config(task["task_id"]),
                                {"plan": plan, "revision": revision + 1,
                                 "approval": None, "status": "awaiting_review"}, as_node="prepare")
        self._set_status(task["task_id"], "awaiting_review")
        # Materialize the new review interrupt before accepting a review request.
        self._drive(task["task_id"], None)
        return self.get_task()

    def review(self, approved: bool, revision: int, comment: str = ""):
        if type(revision) is not int or not isinstance(comment, str):
            raise ValueError("请提供有效的计划版本和审核备注")
        task = self._expect({"awaiting_review"}, revision)
        if not isinstance(approved, bool):
            raise ValueError("approved 必须是布尔值")
        self._drive(task["task_id"], Command(resume={"approved": approved, "revision": revision,
                                                    "comment": comment, "reviewed_at": _now()}))
        return self.get_task()

    def check_start(self, revision):
        if type(revision) is not int:
            raise WorkflowConflict("请提供审核过的计划版本")
        task = self._expect({"approved"}, revision)
        if not task["approval"] or task["approval"]["plan_hash"] != _digest(task["plan"]):
            raise WorkflowConflict("计划已改变，需要重新审核")
        validate_plan(task["plan"], self.agent.skill_registry)
        return task

    def start(self, revision):
        task = self.check_start(revision)
        self._drive(task["task_id"], Command(resume={"start": True, "revision": revision}))

    def retry_report(self):
        task = self._expect({"report_failed"})
        snapshot = self.graph.get_state(self._config(task["task_id"]))
        if task["results"] is None or snapshot.next != ("report",):
            raise WorkflowConflict("没有可重试的报告节点")
        self._drive(task["task_id"], None)

    def resume_diagnosis(self):
        task = self._expect({"diagnostic_failed"})
        snapshot = self.graph.get_state(self._config(task["task_id"]))
        if task["results"] is None or not snapshot.next or not all(node.startswith("diagnostic_") for node in snapshot.next):
            raise WorkflowConflict("没有可继续的诊断节点")
        if not self.agent.diagnostician:
            raise WorkflowConflict("诊断组件未配置")
        self.agent.diagnostician.reset_cancel()
        self._drive(task["task_id"], None)

    def _expect(self, statuses, revision=None):
        task = self.get_task()
        if not task or task["state"] not in statuses:
            raise WorkflowConflict("当前任务状态不允许此操作")
        if revision is not None and (type(revision) is not int or task["revision"] != revision):
            raise WorkflowConflict("计划版本已变化，请刷新后重新审核")
        return task

    def _drive(self, task_id, graph_input):
        try:
            self.graph.invoke(graph_input, self._config(task_id), durability="sync")
            values = self.graph.get_state(self._config(task_id)).values
            self._set_status(task_id, values.get("status", "awaiting_review"))
        except Exception as error:
            values = self.graph.get_state(self._config(task_id)).values
            snapshot = self.graph.get_state(self._config(task_id))
            if values.get("results") is not None:
                status = "diagnostic_failed" if any(node.startswith("diagnostic_") for node in snapshot.next) else "report_failed"
            else:
                status = "error"
            self._set_status(task_id, status, str(error))
            raise
        finally:
            task = self.get_task(task_id)
            public_task = {key: value for key, value in task.items() if key != "knowledge_texts"}
            self.agent.event_bus.emit({"type": "task_updated", "task": public_task})

    def _prepare(self, state):
        self._set_status(state["task_id"], "planning")
        plan = state.get("plan")
        if plan is None:
            plan = self.agent.generate_plan(state.get("instruction", ""))
        plan = validate_plan(plan, self.agent.skill_registry)
        return {"plan": plan, "status": "awaiting_review"}

    def _review(self, state):
        decision = interrupt({"kind": "plan_review", "task_id": state["task_id"],
                              "revision": state["revision"], "plan": state["plan"]})
        if decision.get("revision") != state["revision"] or type(decision.get("approved")) is not bool:
            raise WorkflowConflict("审核版本或审核结果无效")
        plan = validate_plan(state["plan"], self.agent.skill_registry)
        review = {**decision, "plan_hash": _digest(plan)}
        return {"approval": review, "reviews": [*state.get("reviews", []), review],
                "status": "approved" if review["approved"] else "rejected"}

    def _execution_gate(self, state):
        decision = interrupt({"kind": "start_test", "task_id": state["task_id"],
                              "revision": state["revision"]})
        if not decision.get("start") or decision.get("revision") != state["revision"]:
            raise WorkflowConflict("启动请求无效")
        return {}

    def _execute(self, state):
        if self.agent.diagnostician:
            self.agent.diagnostician.reset_cancel()
        self._set_status(state["task_id"], "executing")
        if state["approval"]["plan_hash"] != _digest(state["plan"]):
            raise WorkflowConflict("审核后的计划已改变")
        self.agent.plan = validate_plan(state["plan"], self.agent.skill_registry)
        try:
            results = self.agent.execute()
        except Exception as error:
            # Persist the failure, so diagnosis/reporting never needs to rerun hardware.
            results = {"results": [{"action": "execution", "name": "执行异常", "success": False,
                                    "error": str(error)}], "summary": {"total": 1, "passed": 0, "failed": 1},
                       "stopped": self.agent.yaml_runner.is_stopped, "execution_error": True}
            self.agent.results = results
        return {"results": results, "status": "reporting"}

    def _after_execution(self, state):
        diagnostician = self.agent.diagnostician
        if diagnostician and diagnostician.config.enabled and not state["results"].get("stopped") and failure_records(state["results"]):
            return "diagnose"
        return "report"

    def _diagnostic_prepare(self, state):
        self._set_status(state["task_id"], "diagnosing")
        return {"diagnosis": self.agent.diagnostician.prepare(state["task_id"], state["results"]),
                "status": "diagnosing"}

    def _diagnostic_decide(self, state):
        self._set_status(state["task_id"], "diagnosing")
        diagnosis, decision = self.agent.diagnostician.decide(
            state["task_id"], state["plan"], state["results"], state["diagnosis"])
        return {"diagnosis": diagnosis, "diagnostic_action": decision}

    def _diagnostic_tool(self, state):
        self._set_status(state["task_id"], "diagnosing")
        diagnosis = self.agent.diagnostician.run_tool(
            state["task_id"], state["plan"], state["results"], state["diagnosis"], state["diagnostic_action"])
        return {"diagnosis": diagnosis}

    def _diagnostic_finish(self, state):
        diagnosis = self.agent.diagnostician.finish(state["task_id"], state["diagnosis"])
        return {"diagnosis": diagnosis, "status": "reporting"}

    def _report(self, state):
        self._set_status(state["task_id"], "reporting")
        report_results = deepcopy(state["results"])
        if state.get("diagnosis"):
            report_results["diagnosis"] = state["diagnosis"]
        _, report = self.agent.reporter.generate_report(state["plan"], report_results)
        if state.get("diagnosis"):
            report += diagnosis_markdown(state["diagnosis"])
        report_id = f"{state['task_id']}_{state['revision']}"
        os.makedirs(self.reports_dir, exist_ok=True)
        path = os.path.join(self.reports_dir, f"report_{report_id}.md")
        with open(path + ".tmp", "w", encoding="utf-8") as file:
            file.write(report)
        os.replace(path + ".tmp", path)
        status = "stopped" if state["results"].get("stopped") else "done"
        self.agent.event_bus.emit({"type": "pipeline_progress", "phase": "done",
                                   "message": "本轮测试、诊断与报告流程已结束" if state.get("diagnosis") else "本轮测试与报告流程已结束"})
        return {"report": report, "report_id": report_id, "status": status}

    def close(self):
        if not self._closed:
            self._checkpoint_db.close()
            self._db.close()
            self._closed = True
