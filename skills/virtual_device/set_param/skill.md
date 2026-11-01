---
action: set_param
description: 设置设备参数
---

# 设置设备参数 (set_param)

修改虚拟设备的运行参数。

## 参数

- `name` (必需): 参数名称，支持 exposure_ms, gain, frame_rate, resolution
- `value` (必需): 参数值

## 参数范围

| 参数 | 类型 | 范围 | 默认值 |
|------|------|------|--------|
| exposure_ms | int | 1-10000 | 100 |
| gain | float | 0.1-64.0 | 1.0 |
| frame_rate | int | 1-120 | 30 |
| resolution | str | 512x512, 1024x1024, 2048x2048 | 2048x2048 |

## 示例

用户说："把曝光设置为200毫秒"
解析为：
```json
{
  "action": "set_param",
  "params": {"name": "exposure_ms", "value": 200}
}
```

用户说："分辨率改成1024"
解析为：
```json
{
  "action": "set_param",
  "params": {"name": "resolution", "value": "1024x1024"}
}
```

用户说："增益调到2.5"
解析为：
```json
{
  "action": "set_param",
  "params": {"name": "gain", "value": 2.5}
}
```

## 注意事项

- 设置超出范围的值会被拒绝
- 修改参数后立即生效，无需重启
- 返回结果包含修改前的旧值，便于回滚
