"""
YamlRunner - YAML 测试用例执行引擎
"""
import time
import random
import threading
from typing import Any, Optional

from engine.template_engine import TemplateEngine
from engine.skill_registry import SkillRegistry
from engine.event_bus import EventBus
from engine.chat import Chat


class YamlRunner:
    """解析并执行 YAML 格式的测试计划"""

    def __init__(self, skill_registry: SkillRegistry, event_bus: EventBus, chat: Chat):
        self.skill_registry = skill_registry
        self.event_bus = event_bus
        self.chat = chat
        self._engine: Optional[TemplateEngine] = None
        self._step_counter = 0
        self._total_steps = 0
        self._results: list[dict] = []
        self._aborted = False
        self._has_failure = False  # 模块内是否有断言/步骤失败（含 on_fail:continue）
        # 模块级上下文
        self._module_index = 0
        self._total_modules = 0
        self._current_module = ""
        self._module_step = 0
        self._module_total_steps = 0
        self._nesting_depth = 0  # 模块内嵌套深度，0=直接子步骤
        # 执行控制
        self._stopped = False
        self._paused = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # 初始为非暂停状态

    def stop(self):
        """停止执行（不可恢复）"""
        self._stopped = True
        self._paused = False
        self._pause_event.set()  # 解除暂停阻塞，让线程能退出

    def pause(self):
        """暂停执行"""
        if not self._stopped:
            self._paused = True
            self._pause_event.clear()
            self.event_bus.emit({"type": "execution_paused"})

    def resume(self):
        """恢复执行"""
        self._paused = False
        self._pause_event.set()
        self.event_bus.emit({"type": "execution_resumed"})

    @property
    def is_paused(self):
        return self._paused

    @property
    def is_stopped(self):
        return self._stopped

    def _check_control(self):
        """每个步骤执行前检查：暂停则阻塞，停止则标记 abort"""
        self._pause_event.wait()  # 暂停时阻塞在这里
        if self._stopped:
            self._aborted = True

    def execute_plan(self, plan: dict) -> dict:
        """
        执行 YAML 测试计划。

        Args:
            plan: 解析后的 YAML dict，包含 version, name, variables, steps

        Returns:
            {"plan_name", "variables", "results", "summary"}
        """
        plan_name = plan.get("name", "未命名计划")
        self._engine = TemplateEngine(plan.get("variables", {}))
        self._step_counter = 0
        self._total_steps = self._count_steps(plan.get("steps", []))
        self._results = []
        self._aborted = False
        self._has_failure = False
        # 重置控制状态
        self._stopped = False
        self._paused = False
        self._pause_event.set()

        # 识别顶层 group 作为测试模块
        steps = plan.get("steps", [])
        self._total_modules = sum(1 for s in steps if s.get("action") == "group")
        self._module_index = 0
        self._current_module = ""
        self._module_step = 0
        self._module_total_steps = 0

        self.event_bus.emit({
            "type": "execution_started",
            "plan_name": plan_name,
            "total_modules": self._total_modules,
            "total_steps": self._total_steps,
        })

        self._execute_steps(steps)

        summary = self._build_summary()
        self.event_bus.emit({"type": "all_completed", "summary": summary})

        return {
            "plan_name": plan_name,
            "variables": dict(self._engine.variables),
            "results": self._results,
            "summary": summary,
            "stopped": self._stopped,
        }

    # ── 步骤调度 ─────────────────────────────────────────

    def _execute_steps(self, steps: list[dict]):
        """顺序执行步骤列表"""
        for step in steps:
            self._check_control()
            if self._aborted:
                break
            self._execute_step(step)

    def _execute_step(self, step: dict) -> dict:
        """按 action 分发到对应 handler"""
        self._step_counter += 1
        action = step.get("action", "")
        name = step.get("name", f"步骤 {self._step_counter}")

        # 只有模块直接子步骤（深度 0）才递增模块级计数
        is_direct_step = self._current_module and self._nesting_depth == 0
        if is_direct_step:
            self._module_step += 1

        # group 不发 step 事件，由 _action_group 发 module 事件
        if action != "group":
            self.event_bus.emit({
                "type": "step_started",
                "step": self._module_step if is_direct_step else 0,
                "total_steps": self._module_total_steps if is_direct_step else 0,
                "name": name,
                "action": action,
                "module": self._current_module,
                "module_index": self._module_index,
                "depth": self._nesting_depth,
            })

        handler = {
            "skill": self._action_skill,
            "wait": self._action_wait,
            "set_variable": self._action_set_variable,
            "assert": self._action_assert,
            "log": self._action_log,
            "repeat": self._action_repeat,
            "while": self._action_while,
            "for_each": self._action_for_each,
            "if": self._action_if,
            "llm_analyze": self._action_llm_analyze,
            "group": self._action_group,
            "timer_start": self._action_timer_start,
            "timer_stop": self._action_timer_stop,
            "summary": self._action_summary,
        }.get(action)

        if not handler:
            result = {"success": False, "error": f"未知 action: {action}"}
            self._record(name, action, result)
            self._has_failure = True
            self._aborted = True
            return result

        try:
            result = handler(step)
            failed = result.get("success") is False or result.get("passed") is False
            if failed:
                self._has_failure = True
            # group 的完成事件由 _action_group 自己发，不重复发
            if action != "group":
                self.event_bus.emit({
                    "type": "step_failed" if failed else "step_completed",
                    "step": self._module_step if is_direct_step else 0,
                    "total_steps": self._module_total_steps if is_direct_step else 0,
                    "name": name,
                    "action": action,
                    "module": self._current_module,
                    "module_index": self._module_index,
                    "depth": self._nesting_depth,
                    "error": (result.get("error") or result.get("message") or "步骤未通过") if failed else None,
                })
            return result
        except Exception as e:
            result = {"success": False, "error": str(e)}
            self.event_bus.emit({
                "type": "step_failed",
                "step": self._module_step if is_direct_step else 0,
                "total_steps": self._module_total_steps if is_direct_step else 0,
                "name": name,
                "action": action,
                "error": str(e),
                "module": self._current_module,
                "module_index": self._module_index,
                "depth": self._nesting_depth,
            })
            self._record(name, action, result)
            self._aborted = True
            return result

    # ── Action Handlers ──────────────────────────────────

    def _action_skill(self, step: dict) -> dict:
        skill_name = step.get("skill", "")
        skill = self.skill_registry.get(skill_name)
        if not skill:
            result = {"success": False, "error": f"技能 {skill_name} 未找到"}
            return self._complete_skill(step, result)

        raw_params = step.get("params", {})
        params = self._engine.resolve_params(raw_params) if raw_params else {}

        # 自动从 variables 中补充 skill required params（用户填写的设备参数）
        required = skill.metadata.params.get('required', [])
        for param_name in required:
            if param_name not in params:
                val = self._engine.variables.get(param_name)
                if val is not None:
                    params[param_name] = val

        valid, err = skill.validate(params)
        if not valid:
            result = {"success": False, "error": f"参数验证失败: {err}"}
            return self._complete_skill(step, result)

        result = skill.execute(params)
        return self._complete_skill(step, result)

    def _complete_skill(self, step, result):
        save_as = step.get("save_result_as")
        skill_name = step.get("skill", "")

        if save_as:
            self._engine.set(save_as, result)

        self._record(step.get("name", ""), "skill", result, skill=skill_name)

        # 自动验证 skill 执行结果
        if not result.get("success") or result.get("passed") is False:
            on_fail = step.get("on_fail", "abort")
            fail_message = step.get("fail_message", result.get("error", "技能执行失败"))
            self._has_failure = True

            self.event_bus.emit({
                "type": "assert_result",
                "name": step.get("name", skill_name),
                "passed": False,
                "message": str(fail_message),
                "module_index": self._module_index,
            })

            on_fail_steps = step.get("on_fail_steps", [])
            if on_fail_steps:
                self._execute_steps(on_fail_steps)

            if on_fail == "abort":
                self._aborted = True

        return result

    def _action_wait(self, step: dict) -> dict:
        if "seconds_min" in step or "seconds_max" in step:
            sec_min = float(self._engine.resolve_expr(step.get("seconds_min", 0)))
            sec_max = float(self._engine.resolve_expr(step.get("seconds_max", sec_min)))
            seconds = random.uniform(sec_min, sec_max)
        else:
            seconds = float(self._engine.resolve_expr(step.get("seconds", 1)))
        seconds = round(seconds, 2)
        time.sleep(seconds)
        result = {"success": True, "message": f"等待 {seconds} 秒"}
        self._record(step.get("name", ""), "wait", result)
        return result

    def _action_set_variable(self, step: dict) -> dict:
        var_name = step.get("variable", "")
        raw_value = step.get("value")
        value = self._engine.resolve_expr(raw_value)
        self._engine.set(var_name, value)
        result = {"success": True, "variable": var_name, "value": value}
        self._record(step.get("name", ""), "set_variable", result)
        return result

    def _action_assert(self, step: dict) -> dict:
        condition = step.get("condition", "")
        raw_message = step.get("message", "验证失败")
        on_fail = step.get("on_fail", "abort")
        name = step.get("name", "验证")

        # 解析 message 中的变量引用，让日志对用户可读
        try:
            message = self._engine.resolve(raw_message)
        except Exception:
            message = raw_message

        try:
            passed = self._engine.eval_condition(condition)
        except Exception as e:
            passed = False
            message = f"{message}（内部错误: 条件表达式求值失败）"

        self.event_bus.emit({
            "type": "assert_result",
            "name": name,
            "passed": passed,
            "message": str(message),
            "module_index": self._module_index,
        })

        if passed:
            result = {"success": True, "passed": True, "condition": condition}
            self._record(step.get("name", ""), "assert", result)
            return result

        # 断言失败
        self._has_failure = True
        result = {"success": False, "passed": False, "condition": condition, "message": message}
        self._record(step.get("name", ""), "assert", result)

        # 执行 on_fail_steps
        on_fail_steps = step.get("on_fail_steps", [])
        if on_fail_steps:
            self._execute_steps(on_fail_steps)

        if on_fail == "abort":
            self._aborted = True

        return result

    def _action_log(self, step: dict) -> dict:
        params = step.get("params", {})
        raw_msg = params.get("message", "")
        message = self._engine.resolve(raw_msg)
        self.event_bus.emit({"type": "log", "message": str(message)})
        result = {"success": True, "message": str(message)}
        self._record(step.get("name", ""), "log", result)
        return result

    def _action_repeat(self, step: dict) -> dict:
        count = int(self._engine.resolve_expr(step.get("count", 0)))
        sub_steps = step.get("steps", [])
        name = step.get("name", "repeat")

        self._nesting_depth += 1
        for i in range(count):
            if self._aborted:
                break
            self._engine.set("_loop_index", i)
            self.event_bus.emit({
                "type": "loop_progress",
                "name": name,
                "iteration": i + 1,
                "total": count,
                "module_index": self._module_index,
            })
            self._execute_steps(sub_steps)
        self._nesting_depth -= 1

        result = {"success": not self._aborted, "iterations": count}
        self._record(name, "repeat", result)
        return result

    def _action_while(self, step: dict) -> dict:
        condition = step.get("condition", "False")
        max_iter = int(step.get("max_iterations", 1000))
        sub_steps = step.get("steps", [])
        name = step.get("name", "while")
        iteration = 0

        self._nesting_depth += 1
        while iteration < max_iter:
            if self._aborted:
                break
            if not self._engine.eval_condition(condition):
                break
            self._engine.set("_loop_index", iteration)
            self.event_bus.emit({
                "type": "loop_progress",
                "name": name,
                "iteration": iteration + 1,
                "max_iterations": max_iter,
                "module_index": self._module_index,
            })
            self._execute_steps(sub_steps)
            iteration += 1
        self._nesting_depth -= 1

        result = {"success": not self._aborted, "iterations": iteration}
        self._record(name, "while", result)
        return result

    def _action_for_each(self, step: dict) -> dict:
        raw_items = step.get("items", [])
        items = self._engine.resolve_expr(raw_items) if isinstance(raw_items, str) else self._engine.resolve(raw_items)
        if not isinstance(items, (list, tuple)):
            items = [items]

        item_var = step.get("item_var", "_item")
        sub_steps = step.get("steps", [])
        name = step.get("name", "for_each")
        total = len(items)

        self._nesting_depth += 1
        for i, item in enumerate(items):
            if self._aborted:
                break
            self._engine.set(item_var, item)
            self._engine.set("_loop_index", i)
            self.event_bus.emit({
                "type": "loop_progress",
                "name": name,
                "iteration": i + 1,
                "total": total,
                "module_index": self._module_index,
            })
            self._execute_steps(sub_steps)
        self._nesting_depth -= 1

        result = {"success": not self._aborted, "iterations": total}
        self._record(name, "for_each", result)
        return result

    def _action_if(self, step: dict) -> dict:
        condition = step.get("condition", "False")
        name = step.get("name", "if")

        self._nesting_depth += 1
        if self._engine.eval_condition(condition):
            self._execute_steps(step.get("steps", []))
            branch = "then"
        else:
            self._execute_steps(step.get("else_steps", []))
            branch = "else"
        self._nesting_depth -= 1

        result = {"success": True, "branch": branch}
        self._record(name, "if", result)
        return result

    def _action_llm_analyze(self, step: dict) -> dict:
        raw_prompt = step.get("prompt", "")
        prompt = self._engine.resolve(raw_prompt)
        name = step.get("name", "LLM 分析")

        def on_progress(char_count, elapsed):
            self.event_bus.emit({
                "type": "pipeline_progress",
                "phase": "llm_analyze",
                "message": f"{name}: LLM 分析中 (已生成 {char_count} 字符)",
                "elapsed_seconds": round(elapsed, 2),
            })

        self.chat.set_system_prompt("你是一个专业的测试分析助手，请根据提供的数据进行分析。")
        analysis = self.chat.ask(str(prompt), on_progress=on_progress)

        save_as = step.get("save_result_as")
        if save_as:
            self._engine.set(save_as, analysis)

        result = {"success": True, "analysis": analysis}
        self._record(step.get("name", ""), "llm_analyze", result)
        return result

    def _action_group(self, step: dict) -> dict:
        name = step.get("name", "未命名模块")
        sub_steps = step.get("steps", [])

        # 进入模块上下文
        self._module_index += 1
        prev_module = self._current_module
        prev_module_step = self._module_step
        prev_module_total = self._module_total_steps
        prev_aborted = self._aborted
        prev_has_failure = self._has_failure
        prev_depth = self._nesting_depth

        self._current_module = name
        self._module_step = 0
        self._module_total_steps = len(sub_steps)
        self._aborted = False
        self._has_failure = False
        self._nesting_depth = 0  # 模块直接子步骤从深度 0 开始

        self.event_bus.emit({
            "type": "module_started",
            "module_index": self._module_index,
            "total_modules": self._total_modules,
            "name": name,
            "total_steps": len(sub_steps),
        })

        self._execute_steps(sub_steps)

        passed = not self._aborted and not self._has_failure
        self.event_bus.emit({
            "type": "module_completed",
            "module_index": self._module_index,
            "total_modules": self._total_modules,
            "name": name,
            "passed": passed,
        })

        # 恢复上层上下文，模块内的 abort 不影响后续模块
        self._aborted = prev_aborted
        self._has_failure = prev_has_failure
        self._current_module = prev_module
        self._module_step = prev_module_step
        self._module_total_steps = prev_module_total
        self._nesting_depth = prev_depth

        result = {"success": passed}
        self._record(name, "group", result)
        return result

    def _action_timer_start(self, step: dict) -> dict:
        timer_name = step.get("timer", "")
        self._engine.set(f"_timer_{timer_name}_start", time.time())
        result = {"success": True, "timer": timer_name}
        self._record(step.get("name", ""), "timer_start", result)
        return result

    def _action_timer_stop(self, step: dict) -> dict:
        timer_name = step.get("timer", "")
        start_key = f"_timer_{timer_name}_start"
        start_time = self._engine.variables.get(start_key)
        if start_time is None:
            result = {"success": False, "error": f"计时器 {timer_name} 未启动"}
            self._record(step.get("name", ""), "timer_stop", result)
            return result

        elapsed = round(time.time() - float(start_time), 2)
        self._engine.set(timer_name, elapsed)

        if step.get("accumulate"):
            total_key = f"{timer_name}_total"
            prev = float(self._engine.variables.get(total_key, 0))
            self._engine.set(total_key, round(prev + elapsed, 2))

        self.event_bus.emit({"type": "log", "message": f"计时 {timer_name}: {elapsed} 秒"})
        result = {"success": True, "timer": timer_name, "elapsed": elapsed}
        self._record(step.get("name", ""), "timer_stop", result)
        return result

    def _action_summary(self, step: dict) -> dict:
        params = step.get("params", {})
        raw_msg = params.get("message", "")
        message = self._engine.resolve(raw_msg)
        self.event_bus.emit({"type": "log", "message": str(message)})
        result = {"success": True, "message": str(message)}
        self._record(step.get("name", ""), "summary", result)
        return result

    # ── 辅助方法 ──────────────────────────────────────────

    def _record(self, name: str, action: str, result: dict, **context):
        """记录步骤结果"""
        self._results.append({
            "step": self._step_counter,
            "name": name,
            "action": action,
            "module": self._current_module,
            "module_index": self._module_index,
            **result,
            **context,
        })

    def _build_summary(self) -> dict:
        """构建测试摘要，按模块（group）统计"""
        module_results = [r for r in self._results if r.get("action") == "group"]
        if module_results:
            total = len(module_results)
            passed = sum(1 for r in module_results if r.get("success"))
        else:
            # 没有 group 时按全部步骤统计
            total = len(self._results)
            passed = sum(1 for r in self._results if r.get("success") and r.get("passed") is not False)
        return {"total": total, "passed": passed, "failed": total - passed}

    @staticmethod
    def _count_steps(steps: list[dict]) -> int:
        """粗略统计顶层步骤数（用于进度展示）"""
        return len(steps)
