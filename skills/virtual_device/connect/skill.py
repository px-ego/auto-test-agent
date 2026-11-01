"""连接虚拟设备"""
import time

from shared.skill_base import BaseSkill, SkillMetadata


class ConnectSkill(BaseSkill):
    """连接到虚拟设备"""

    def __init__(self):
        super().__init__()
        self._connected = False
        self._device_id = None

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            action="connect",
            description="连接到虚拟设备",
            params={
                "required": ["ip"],
                "optional": {
                    "port": {"type": "int", "default": 8000}
                }
            }
        )

    def validate(self, params: dict) -> tuple[bool, str]:
        valid, msg = super().validate(params)
        if not valid:
            return valid, msg

        ip = params.get("ip", "")
        if not ip:
            return False, "IP地址不能为空"

        port = params.get("port", 8000)
        if not isinstance(port, int) or port < 1 or port > 65535:
            return False, "端口号必须在 1-65535 范围内"

        return True, ""

    def execute(self, params: dict) -> dict:
        ip = params["ip"]
        port = params.get("port", 8000)

        # 模拟连接延迟
        time.sleep(0.5)

        self._connected = True
        self._device_id = "VD-001"

        return {
            "success": True,
            "message": f"成功连接到设备 {ip}:{port}",
            "connected": True,
            "device_id": self._device_id,
            "ip": ip,
            "port": port
        }


skill_class = ConnectSkill
