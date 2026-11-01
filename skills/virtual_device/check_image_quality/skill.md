---
action: check_image_quality
description: 检查图像质量
---

# 检查图像质量 (check_image_quality)

对拍摄的图像进行质量评估。

## 参数

- `image_id` (可选): 要检查的图像ID，不指定则检查最近一张

## 示例

用户说："检查图像质量"
解析为：
```json
{
  "action": "check_image_quality",
  "params": {}
}
```

用户说："检查图像 IMG-20260318_100000 的质量"
解析为：
```json
{
  "action": "check_image_quality",
  "params": {"image_id": "IMG-20260318_100000"}
}
```

## 质量指标

| 指标 | 通过标准 | 说明 |
|------|----------|------|
| SNR | > 30 dB | 信噪比 |
| sharpness | > 0.7 | 清晰度 |
| uniformity | > 0.90 | 均匀性（参考） |
| defect_pixels | < 5 | 坏点数（参考） |

## 注意事项

- SNR 和 sharpness 是判定通过/未通过的核心指标
- uniformity 和 defect_pixels 作为参考指标，不影响通过判定
- 建议在拍摄后立即进行质量检查
