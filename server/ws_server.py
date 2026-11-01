"""
WebSocket 服务 - 实时推送测试执行进度
"""
import asyncio
import json
from typing import Set

import websockets
from websockets.server import serve


class WSServer:
    """WebSocket 服务器，管理客户端连接和消息广播"""

    def __init__(self):
        self.clients: Set = set()
        self._loop: asyncio.AbstractEventLoop = None

    async def handler(self, websocket):
        """处理新的 WebSocket 连接"""
        self.clients.add(websocket)
        print(f"[WebSocket] 客户端连接，当前 {len(self.clients)} 个")
        try:
            async for message in websocket:
                pass
        finally:
            self.clients.discard(websocket)
            print(f"[WebSocket] 客户端断开，当前 {len(self.clients)} 个")

    async def _do_broadcast(self, message: dict):
        """实际执行广播（在事件循环线程中调用）"""
        if not self.clients:
            return
        data = json.dumps(message, ensure_ascii=False)
        closed = set()
        for ws in self.clients:
            try:
                await ws.send(data)
            except Exception:
                closed.add(ws)
        self.clients -= closed

    def broadcast_sync(self, message: dict):
        """同步版本的广播（从非 async 线程调用）"""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._do_broadcast(message), self._loop)

    async def start(self, host: str = '0.0.0.0', port: int = 8081):
        """启动 WebSocket 服务"""
        self._loop = asyncio.get_running_loop()
        async with serve(self.handler, host, port):
            print(f"[WebSocket] 服务启动: ws://{host}:{port}")
            await asyncio.Future()  # run forever
