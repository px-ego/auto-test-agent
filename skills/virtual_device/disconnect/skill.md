---
action: disconnect
description: 断开虚拟设备连接
---

# 断开连接 (disconnect)

安全断开与虚拟设备的连接。

## 参数

无需参数。

## 示例

用户说："断开连接"
解析为：
```json
{
  "action": "disconnect",
  "params": {}
}
```

用户说："关闭设备"
解析为：
```json
{
  "action": "disconnect",
  "params": {}
}
```

## 注意事项

- 断开前会自动停止所有正在进行的采集任务
- 断开后需要重新连接才能执行其他操作
- 典型断开延迟约 300ms
