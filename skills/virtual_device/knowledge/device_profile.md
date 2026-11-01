---
device_name: virtual-device-v1
device_type: camera
manufacturer: Virtual Instruments Co.
firmware_version: 2.1.0
---

# 虚拟设备 virtual-device-v1

用于演示和自动化测试的虚拟相机设备模拟器，无需真实硬件即可验证完整测试流程。

## 设备参数

| 参数 | 范围 | 默认值 | 单位 |
|------|------|--------|------|
| resolution | 512x512, 1024x1024, 2048x2048 | 2048x2048 | px |
| exposure_ms | 1 - 10000 | 100 | ms |
| gain | 0.1 - 64.0 | 1.0 | x |
| frame_rate | 1 - 120 | 30 | fps |

## 测试指标

- 图像质量 SNR > 30 dB
- 图像清晰度 sharpness > 0.7
- 均匀性 uniformity > 0.90
- 坏点数 defect_pixels < 5
- 连接延迟 < 100 ms

## 安全约束

- 曝光时间超过 5000ms 时需确认，防止过曝
- gain 超过 32.0 时图像噪声显著增大，建议谨慎使用
- 连续拍摄间隔不应低于 50ms
- 断开连接前应确保无正在进行的采集任务
