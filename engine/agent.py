"""
TestAgent - 状态机，编排 计划→执行→报告 完整流程
"""
import time
from enum import Enum
from typing import Optional, Union

from engine.event_bus import EventBus


class AgentState(Enum):
    IDLE = "idle"
    PLANNING = "planning"
    PLAN_READY = "plan_ready"
    EXECUTING = "executing"
    REPORTING = "reporting"
    DONE = "done"
    ERROR = "error"


class TestAgent:
    """自动化测试 Agent，管理 计划→执行→报告 的完整生命周期"""

    def __init__(self, event_bus: EventBus, planner, reporter,
                 skill_registry, yaml_runner, prompt_builder, diagnostician=None):
        self.event_bus = event_bus
        self.planner = planner
        self.reporter = reporter
        self.skill_registry = skill_registry
        self.yaml_runner = yaml_runner
        self.prompt_builder = prompt_builder
        self.diagnostician = diagnostician

        self.state = AgentState.IDLE
        self.plan: Optional[dict] = None
        self.results: Optional[Union[list[dict], dict]] = None
        self.report: Optional[str] = None
        self.report_id: Optional[str] = None

    def generate_plan(self, user_instruction: str = "") -> dict:
        """调用 LLM 直接生成可执行测试计划（流式，带进度推送）"""
        self.state = AgentState.PLANNING
        try:
            self._emit_progress("planning", "正在生成测试计划...")
            yaml_plan = self.planner.generate_plan(
                user_instruction,
                format="yaml",
                on_progress=self._make_llm_progress_cb("planning", "生成测试计划中"),
                on_retry=self._on_plan_retry,
            )
            self.plan = yaml_plan
            self.state = AgentState.PLAN_READY
            self._emit_progress("planning", "测试计划生成完成")
            return yaml_plan
        except Exception:
            self.state = AgentState.ERROR
            raise

    def _on_plan_retry(self, attempt: int, max_retries: int, error: str):
        """计划校验失败时的重试回调"""
        self._emit_progress(
            "planning",
            f"计划校验失败（第 {attempt}/{max_retries} 次），正在让 LLM 修正: {error}",
        )

    def update_plan(self, plan: dict):
        """手动更新/替换测试计划（YAML 格式）"""
        self.plan = plan
        self.state = AgentState.PLAN_READY

    def _emit_progress(self, phase: str, message: str, elapsed: float = None):
        """发送流程进度事件，让前端实时展示当前阶段"""
        event = {
            "type": "pipeline_progress",
            "phase": phase,
            "message": message,
        }
        if elapsed is not None:
            event["elapsed_seconds"] = round(elapsed, 2)
        self.event_bus.emit(event)
        elapsed_str = f" ({elapsed:.2f}s)" if elapsed is not None else ""
        print(f"[Agent] {message}{elapsed_str}")

    def _make_llm_progress_cb(self, phase: str, label: str):
        """创建 LLM 流式进度回调，定期向前端发送心跳"""
        def on_progress(char_count: int, elapsed: float):
            self._emit_progress(phase, f"{label} (已生成 {char_count} 字符)", elapsed)
        return on_progress

    def execute(self) -> Union[list[dict], dict]:
        """执行当前 YAML 测试计划"""
        if not self.plan:
            raise ValueError("没有测试计划")

        total_start = time.time()
        self.state = AgentState.EXECUTING
        try:
            t0 = time.time()
            self._emit_progress("executing", "开始执行测试计划...")
            self.results = self.yaml_runner.execute_plan(self.plan)
            self._emit_progress("executing", "测试计划执行完成",
                                time.time() - t0)

            self.state = AgentState.REPORTING
            return self.results
        except Exception:
            self._emit_progress("error", "执行过程中发生错误",
                                time.time() - total_start)
            self.state = AgentState.ERROR
            raise

    def generate_report(self) -> tuple[str, str]:
        """根据测试结果生成报告"""
        if not self.results:
            raise ValueError("没有测试结果")
        try:
            self.report_id, self.report = self.reporter.generate_report(self.plan, self.results)
            self.state = AgentState.DONE
            return self.report_id, self.report
        except Exception:
            self.state = AgentState.ERROR
            raise

    def reset(self):
        """重置 Agent 状态"""
        self.state = AgentState.IDLE
        self.plan = None
        self.results = None
        self.report = None
        self.report_id = None
