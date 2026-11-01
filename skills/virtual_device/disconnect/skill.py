"""断开虚拟设备连接"""
import time

from shared.skill_base import BaseSkill, SkillMetadata


class DisconnectSkill(BaseSkill):
    """断开虚拟设备连接"""

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            action="disconnect",
            description="断开虚拟设备连接",
            params={
                "required": [],
                "optional": {}
            }
        )

    def execute(self, params: dict) -> dict:
        # 模拟断开延迟
        time.sleep(0.3)

        return {
            "success": True,
            "message": "设备已断开连接",
            "connected": False
        }


skill_class = DisconnectSkill
