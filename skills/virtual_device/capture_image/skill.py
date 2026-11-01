"""拍摄图像"""
import time
import random
from datetime import datetime

from shared.skill_base import BaseSkill, SkillMetadata


class CaptureImageSkill(BaseSkill):
    """拍摄图像"""

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            action="capture_image",
            description="拍摄图像",
            params={
                "required": [],
                "optional": {
                    "exposure_ms": {"type": "int", "default": 100, "range": [1, 10000]},
                    "gain": {"type": "float", "default": 1.0, "range": [0.1, 64.0]}
                }
            }
        )

    def validate(self, params: dict) -> tuple[bool, str]:
        exposure_ms = params.get("exposure_ms", 100)
        if not isinstance(exposure_ms, (int, float)) or exposure_ms < 1 or exposure_ms > 10000:
            return False, "曝光时间必须在 1-10000 ms 范围内"

        gain = params.get("gain", 1.0)
        if not isinstance(gain, (int, float)) or gain < 0.1 or gain > 64.0:
            return False, "增益必须在 0.1-64.0 范围内"

        if exposure_ms > 5000:
            return True, f"警告：曝光时间 {exposure_ms}ms 较长，可能导致过曝"

        if gain > 32.0:
            return True, f"警告：增益 {gain} 较高，图像噪声可能显著增大"

        return True, ""

    def execute(self, params: dict) -> dict:
        exposure_ms = params.get("exposure_ms", 100)
        gain = params.get("gain", 1.0)

        # 模拟拍摄延迟
        time.sleep(0.8)

        # 生成模拟图像数据
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        image_id = f"IMG-{timestamp}"

        # 模拟像素值（受曝光和增益影响）
        base_mean = 1200
        mean_value = int(base_mean * (exposure_ms / 100) * gain)
        mean_value = min(mean_value, 4095)  # 12-bit 最大值
        mean_value = max(mean_value, 100)

        max_value = min(int(mean_value * random.uniform(2.5, 3.5)), 4095)

        return {
            "success": True,
            "message": f"图像拍摄完成: {image_id}",
            "image_id": image_id,
            "resolution": "2048x2048",
            "bit_depth": 12,
            "exposure_ms": exposure_ms,
            "gain": gain,
            "mean_value": mean_value,
            "max_value": max_value,
            "timestamp": timestamp
        }


skill_class = CaptureImageSkill
