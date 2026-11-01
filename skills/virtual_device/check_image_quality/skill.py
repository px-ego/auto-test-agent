"""检查图像质量"""
import random

from shared.skill_base import BaseSkill, SkillMetadata


class CheckImageQualitySkill(BaseSkill):
    """检查图像质量"""

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            action="check_image_quality",
            description="检查图像质量",
            params={
                "required": [],
                "optional": {
                    "image_id": {"type": "str", "description": "要检查的图像ID"}
                }
            }
        )

    def execute(self, params: dict) -> dict:
        image_id = params.get("image_id", "latest")

        # 模拟质量指标
        snr_db = round(random.uniform(28.0, 40.0), 1)
        sharpness = round(random.uniform(0.6, 1.0), 3)
        uniformity = round(random.uniform(0.85, 0.99), 3)
        defect_pixels = random.randint(0, 10)

        # 判定是否通过
        passed = snr_db > 30 and sharpness > 0.7

        status = "通过" if passed else "未通过"
        reasons = []
        if snr_db <= 30:
            reasons.append(f"SNR {snr_db}dB < 30dB")
        if sharpness <= 0.7:
            reasons.append(f"清晰度 {sharpness} < 0.7")

        message = f"图像质量检查{status}"
        if reasons:
            message += f"，原因: {'; '.join(reasons)}"

        return {
            "success": True,
            "message": message,
            "image_id": image_id,
            "snr_db": snr_db,
            "sharpness": sharpness,
            "uniformity": uniformity,
            "defect_pixels": defect_pixels,
            "passed": passed
        }


skill_class = CheckImageQualitySkill
