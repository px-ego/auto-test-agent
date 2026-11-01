"""
自动化测试 Agent - 入口
启动 HTTP + WebSocket 服务
"""
import os
import sys
import asyncio
import threading
import argparse

# 确保项目根目录在 sys.path 中
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

from engine.config import AppConfig
from engine.bootstrap import create_agent
from server.http_server import start_http_server
from server.ws_server import WSServer


def main():
    parser = argparse.ArgumentParser(description="Device test agent")
    parser.add_argument("--http-port", type=int)
    parser.add_argument("--ws-port", type=int)
    parser.add_argument("--database", help="Override the workflow SQLite path")
    options = parser.parse_args()
    config = AppConfig.from_yaml(os.path.join(ROOT_DIR, 'config.yaml'))
    for option in ("http_port", "ws_port"):
        value = getattr(options, option)
        if value is not None:
            if not 1 <= value <= 65535:
                parser.error("ports must be between 1 and 65535")
            setattr(config.server, option, value)
    if options.database:
        config.workflow.database_path = options.database
    service, event_bus, chats = create_agent(config, ROOT_DIR)

    # 创建 WebSocket 服务，通过事件总线订阅
    ws_server = WSServer()
    event_bus.subscribe(ws_server.broadcast_sync)

    # 服务配置
    host = config.server.host
    http_port = config.server.http_port
    ws_port = config.server.ws_port
    web_dir = os.path.join(ROOT_DIR, 'web')

    # 在独立线程启动 HTTP 服务
    http_thread = threading.Thread(
        target=start_http_server,
        args=(service, host, http_port, web_dir),
        daemon=True,
    )
    http_thread.start()

    # 在主线程运行 asyncio 事件循环（WebSocket）
    print(f"[Main] 打开浏览器访问: http://localhost:{http_port}")
    try:
        asyncio.run(ws_server.start(host, ws_port))
    finally:
        for chat in chats:
            chat.stop()
        service.close()


if __name__ == '__main__':
    main()
