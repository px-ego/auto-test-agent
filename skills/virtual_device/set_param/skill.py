"""设置设备参数"""
from shared.skill_base import BaseSkill, SkillMetadata


# 参数定义：名称 -> (类型, 最小值, 最大值, 默认值)
KNOWN_PARAMS = {
    "exposure_ms": (int, 1, 10000, 100),
    "gain": (float, 0.1, 64.0, 1.0),
    "frame_rate": (int, 1, 120, 30),
    "resolution": (str, None, None, "2048x2048"),
}

VALID_RESOLUTIONS = ["512x512", "1024x1024", "2048x2048"]

# 模拟当前参数状态
_current_params = {
    "exposure_ms": 100,
    "gain": 1.0,
    "frame_rate": 30,
    "resolution": "2048x2048",
}


class SetParamSkill(BaseSkill):
    """设置设备参数"""

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            action="set_param",
            description="设置设备参数",
            params={
                "required": ["name", "value"],
                "optional": {}
            }
        )

    def validate(self, params: dict) -> tuple[bool, str]:
        valid, msg = super().validate(params)
        if not valid:
            return valid, msg

        name = params.get("name", "")
        value = params.get("value")

        if name not in KNOWN_PARAMS:
            known = ", ".join(KNOWN_PARAMS.keys())
            return False, f"未知参数: {name}，支持的参数: {known}"

        typ, min_val, max_val, _ = KNOWN_PARAMS[name]

        if name == "resolution":
            if str(value) not in VALID_RESOLUTIONS:
                return False, f"无效分辨率: {value}，支持: {', '.join(VALID_RESOLUTIONS)}"
            return True, ""

        try:
            numeric_value = typ(value)
        except (ValueError, TypeError):
            return False, f"参数 {name} 的值必须是 {typ.__name__} 类型"

        if numeric_value < min_val or numeric_value > max_val:
            return False, f"参数 {name} 的值必须在 {min_val}-{max_val} 范围内"

        return True, ""

    def execute(self, params: dict) -> dict:
        name = params["name"]
        value = params["value"]

        previous = _current_params.get(name)

        # 类型转换
        typ = KNOWN_PARAMS[name][0]
        if name != "resolution":
            value = typ(value)

        _current_params[name] = value

        return {
            "success": True,
            "message": f"参数 {name} 已从 {previous} 设置为 {value}",
            "param": name,
            "value": value,
            "previous": previous
        }


skill_class = SetParamSkill
