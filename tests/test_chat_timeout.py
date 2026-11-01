from concurrent.futures import ThreadPoolExecutor
import threading
from types import SimpleNamespace

import pytest

from engine.chat import Chat


def test_timed_out_request_cannot_pollute_next_diagnostic_context():
    entered, release = threading.Event(), threading.Event()
    calls = []

    def create(**kwargs):
        calls.append(kwargs["messages"])
        if len(calls) == 1:
            entered.set()
            assert release.wait(timeout=5)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))])

    chat = Chat("http://localhost:1/v1", "test")
    chat._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    try:
        chat.set_system_prompt("old task")
        with pytest.raises(TimeoutError):
            chat.ask("old request", timeout=0.05)
        assert entered.is_set()
        chat.set_system_prompt("new task")
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(chat.ask, "new request")
            release.set()
            assert future.result(timeout=5) == "answer"
        assert calls[1][0]["content"] == "new task"
        assert all(item["content"] != "old request" for item in chat._messages)
    finally:
        release.set()
        chat.stop()
