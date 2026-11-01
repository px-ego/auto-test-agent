---
action: get_status
description: 获取设备状态
---

# 获取设备状态 (get_status)

查询虚拟设备的当前运行状态。

## 参数

无需参数。

## 示例

用户说："查看设备状态"
解析为：
```json
{
  "action": "get_status",
  "params": {}
}
```

用户说："设备温度多少"
解析为：
```json
{
  "action": "get_status",
  "params": {}
}
```

## 返回信息

- connected: 连接状态
- temperature: 设备温度 (°C)
- fps: 当前帧率
- exposure_ms: 当前曝光时间
- gain: 当前增益
- resolution: 当前分辨率
- uptime_seconds: 设备运行时间 (秒)
