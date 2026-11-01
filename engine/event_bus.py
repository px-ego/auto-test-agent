"""
EventBus - 简单发布/订阅，替代单一 callback
"""
from typing import Callable


class EventBus:
    """支持多个监听者的事件总线"""

    def __init__(self):
        self._listeners: list[Callable[[dict], None]] = []

    def subscribe(self, listener: Callable[[dict], None]):
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[dict], None]):
        self._listeners = [l for l in self._listeners if l is not listener]

    def emit(self, event: dict):
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                print(f"[EventBus] listener error: {e}")
