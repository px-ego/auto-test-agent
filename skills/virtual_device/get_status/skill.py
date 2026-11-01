"""获取设备状态"""
import random

from shared.skill_base import BaseSkill, SkillMetadata


class GetStatusSkill(BaseSkill):
    """获取设备状态"""

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            action="get_status",
            description="获取设备状态",
            params={
                "required": [],
                "optional": {}
            }
        )

    def execute(self, params: dict) -> dict:
        temperature = round(random.uniform(35.0, 45.0), 1)
        uptime_seconds = random.randint(100, 10000)

        return {
            "success": True,
            "message": f"设备运行正常，温度 {temperature}°C，已运行 {uptime_seconds}s",
            "connected": True,
            "temperature": temperature,
            "fps": 30,
            "exposure_ms": 100,
            "gain": 1.0,
            "resolution": "2048x2048",
            "uptime_seconds": uptime_seconds
        }


skill_class = GetStatusSkill
