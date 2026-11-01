---
action: capture_image
description: 拍摄图像
---

# 拍摄图像 (capture_image)

使用当前参数拍摄一张图像。

## 参数

- `exposure_ms` (可选): 曝光时间，单位毫秒，范围 1-10000，默认 100
- `gain` (可选): 增益倍数，范围 0.1-64.0，默认 1.0

## 示例

用户说："拍一张照片"
解析为：
```json
{
  "action": "capture_image",
  "params": {}
}
```

用户说："曝光200毫秒，增益2倍，拍摄图像"
解析为：
```json
{
  "action": "capture_image",
  "params": {"exposure_ms": 200, "gain": 2.0}
}
```

用户说："用500ms曝光拍照"
解析为：
```json
{
  "action": "capture_image",
  "params": {"exposure_ms": 500}
}
```

## 注意事项

- 曝光时间超过 5000ms 时会有过曝风险，系统会给出警告
- 增益超过 32.0 时噪声显著增大，建议谨慎使用
- 连续拍摄间隔建议不低于 50ms
- 拍摄延迟约 800ms
- 返回的图像ID可用于后续质量检查
