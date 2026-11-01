"""
IntentConverter - 将 LLM 生成的 JSON 测试意图转换为 YamlRunner 标准 plan dict

两遍扫描：
  1. _scan_steps: 收集需要自动生成的变量（设备参数、计数器、timer_total）
  2. _convert_module / _convert_step: 递归转换每个步骤
"""
from engine.skill_registry import SkillRegistry
from engine.intent_schema import validate_intent, validate_plan


class IntentConvertError(ValueError):
    """意图转换校验失败"""
    pass


class IntentConverter:

    # 允许的步骤类型白名单（对应 YamlRunner 内置 action）
    ALLOWED_TYPES = frozenset({
        "call_skill", "wait", "repeat", "while_loop", "for_each",
        "condition", "set_var", "timer_start", "timer_stop", "log", "summary",
    })

    def __init__(self, skill_registry: SkillRegistry):
        self._registry = skill_registry

    def convert(self, intent: dict) -> dict:
        """主入口：JSON 意图 → YamlRunner plan dict"""
        intent = validate_intent(intent)
        modules = intent.get("modules", [])

        # 第一遍：扫描收集变量
        variables = {}
        self._scan_steps_list(modules, variables)

        # 第二遍：转换步骤
        steps = [self._convert_module(m) for m in modules]

        return validate_plan({
            "version": intent.get("version", "1.0"),
            "name": intent.get("name", "未命名计划"),
            "description": intent.get("description", ""),
            "variables": variables,
            "steps": steps,
        }, self._registry)

    # ── 第一遍：扫描变量 ──────────────────────────────────

    def _scan_steps_list(self, items: list, variables: dict):
        """递归扫描步骤列表，收集需要自动声明的变量"""
        for item in items:
            # module 层有 steps
            steps = item.get("steps", [])
            self._scan_steps(steps, variables)

    def _scan_steps(self, steps: list, variables: dict):
        for step in steps:
            step_type = step.get("type", "")

            if step_type == "call_skill":
                skill_name = step.get("skill", "")
                skill = self._registry.get(skill_name)
                if skill:
                    for param in skill.metadata.params.get("required", []):
                        if param not in variables:
                            variables[param] = ""

            elif step_type == "set_var":
                var_name = step.get("variable", "")
                if var_name and var_name not in variables:
                    # 计数器默认初始化为 0
                    variables[var_name] = 0

            elif step_type == "timer_stop":
                if step.get("accumulate"):
                    total_key = f"{step.get('timer', '')}_total"
                    if total_key not in variables:
                        variables[total_key] = 0

            # 递归子步骤
            for key in ("steps", "else_steps", "on_fail_steps"):
                sub = step.get(key, [])
                if sub:
                    self._scan_steps(sub, variables)

    # ── 第二遍：转换步骤 ──────────────────────────────────

    def _convert_module(self, module: dict) -> dict:
        """module → group"""
        return {
            "name": module.get("name", "未命名模块"),
            "action": "group",
            "steps": [self._convert_step(s) for s in module.get("steps", [])],
        }

    def _convert_step(self, step: dict) -> dict:
        step_type = step.get("type", "")

        # 校验步骤类型白名单
        if step_type not in self.ALLOWED_TYPES:
            allowed = ", ".join(sorted(self.ALLOWED_TYPES))
            raise IntentConvertError(
                f"不允许的步骤类型 \"{step_type}\"，"
                f"只能使用以下类型: {allowed}"
            )

        handler = {
            "call_skill": self._convert_call_skill,
            "wait": self._convert_wait,
            "repeat": self._convert_repeat,
            "while_loop": self._convert_while,
            "for_each": self._convert_for_each,
            "condition": self._convert_condition,
            "set_var": self._convert_set_var,
            "timer_start": self._convert_timer_start,
            "timer_stop": self._convert_timer_stop,
            "log": self._convert_log,
            "summary": self._convert_summary,
        }[step_type]

        return handler(step)

    def _convert_call_skill(self, step: dict) -> dict:
        skill_name = step.get("skill", "")

        # 校验 skill 名必须在注册表中
        if not self._registry.get(skill_name):
            available = ", ".join(sorted(self._registry.list_skills().keys()))
            raise IntentConvertError(
                f"技能 \"{skill_name}\" 不存在，"
                f"只能使用已注册的技能: {available}"
            )

        result = {
            "name": step.get("name", skill_name),
            "action": "skill",
            "skill": skill_name,
        }

        # 自动注入 required params 的 ${var} 引用
        params = dict(step.get("params", {}))
        skill = self._registry.get(skill_name)
        if skill:
            for param in skill.metadata.params.get("required", []):
                if param not in params:
                    params[param] = f"${{{param}}}"
        if params:
            result["params"] = params

        if step.get("save_as"):
            result["save_result_as"] = step["save_as"]
        if step.get("on_fail"):
            result["on_fail"] = step["on_fail"]
        if step.get("fail_message"):
            result["fail_message"] = step["fail_message"]
        if step.get("on_fail_steps"):
            result["on_fail_steps"] = [self._convert_step(s) for s in step["on_fail_steps"]]

        return result

    def _convert_wait(self, step: dict) -> dict:
        result = {"name": step.get("name", "等待"), "action": "wait"}
        if "seconds_min" in step:
            result["seconds_min"] = step["seconds_min"]
        if "seconds_max" in step:
            result["seconds_max"] = step["seconds_max"]
        if "seconds" in step:
            result["seconds"] = step["seconds"]
        return result

    def _convert_repeat(self, step: dict) -> dict:
        return {
            "name": step.get("name", "repeat"),
            "action": "repeat",
            "count": step.get("count", 1),
            "steps": [self._convert_step(s) for s in step.get("steps", [])],
        }

    def _convert_while(self, step: dict) -> dict:
        result = {
            "name": step.get("name", "while"),
            "action": "while",
            "condition": step.get("condition", "False"),
            "steps": [self._convert_step(s) for s in step.get("steps", [])],
        }
        if "max_iterations" in step:
            result["max_iterations"] = step["max_iterations"]
        return result

    def _convert_for_each(self, step: dict) -> dict:
        result = {
            "name": step.get("name", "for_each"),
            "action": "for_each",
            "items": step.get("items", []),
            "steps": [self._convert_step(s) for s in step.get("steps", [])],
        }
        if "item_var" in step:
            result["item_var"] = step["item_var"]
        return result

    def _convert_condition(self, step: dict) -> dict:
        result = {
            "name": step.get("name", "if"),
            "action": "if",
            "condition": step.get("condition", "False"),
            "steps": [self._convert_step(s) for s in step.get("steps", [])],
        }
        if step.get("else_steps"):
            result["else_steps"] = [self._convert_step(s) for s in step["else_steps"]]
        return result

    def _convert_set_var(self, step: dict) -> dict:
        return {
            "name": step.get("name", "set_variable"),
            "action": "set_variable",
            "variable": step.get("variable", ""),
            "value": step.get("value"),
        }

    def _convert_timer_start(self, step: dict) -> dict:
        return {
            "name": step.get("name", f"计时开始: {step.get('timer', '')}"),
            "action": "timer_start",
            "timer": step.get("timer", ""),
        }

    def _convert_timer_stop(self, step: dict) -> dict:
        result = {
            "name": step.get("name", f"计时结束: {step.get('timer', '')}"),
            "action": "timer_stop",
            "timer": step.get("timer", ""),
        }
        if step.get("accumulate"):
            result["accumulate"] = True
        return result

    def _convert_log(self, step: dict) -> dict:
        return {
            "name": step.get("name", "log"),
            "action": "log",
            "params": {"message": step.get("message", "")},
        }

    def _convert_summary(self, step: dict) -> dict:
        return {
            "name": step.get("name", "summary"),
            "action": "summary",
            "params": {"message": step.get("message", "")},
        }
