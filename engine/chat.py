"""
Chat - 封装 OpenAI 调用 + 消息历史 + 专属工作线程
"""
import time
import threading
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from queue import Queue
from typing import Callable, Optional

from openai import OpenAI


class CancelledError(Exception):
    """LLM 调用被取消"""
    pass


class Chat:
    """LLM 对话对象，所有 API 调用在后台线程执行"""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "EMPTY",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        request_timeout: float = None,
        max_retries: int = 2,
    ):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        client_options = {"max_retries": max_retries}
        if request_timeout is not None:
            client_options["timeout"] = request_timeout
        self._client = OpenAI(base_url=base_url, api_key=api_key, **client_options)
        self._messages: list[dict] = []
        self._messages_lock = threading.Lock()
        self._generation = 0
        self._queue: Queue = Queue()
        self._cancelled = threading.Event()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def set_system_prompt(self, prompt: str):
        """设置/替换 system prompt，清空对话历史"""
        with self._messages_lock:
            self._generation += 1
            self._messages = [{"role": "system", "content": prompt}]

    def ask(self, message: str, on_progress: Optional[Callable[[int, float], None]] = None,
            timeout: float = None) -> str:
        """
        发送消息，阻塞调用者直到 LLM 返回。

        Args:
            message: 用户消息
            on_progress: 可选的流式进度回调 (已生成字符数, 已耗时秒数)
        """
        cancelled = threading.Event()
        with self._messages_lock:
            self._cancelled = cancelled
            generation = self._generation
            messages = [*self._messages, {"role": "user", "content": message}]
        future: Future = Future()
        self._queue.put((messages, generation, cancelled, future, on_progress))
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            cancelled.set()
            raise

    def cancel(self):
        """取消正在进行的 LLM 调用"""
        self._cancelled.set()

    def clear_history(self):
        """清空历史，保留 system prompt"""
        with self._messages_lock:
            self._generation += 1
            if self._messages and self._messages[0]["role"] == "system":
                self._messages = [self._messages[0]]
            else:
                self._messages = []

    def stop(self):
        """停止后台线程"""
        self._cancelled.set()
        self._queue.put(None)
        self._worker.join(timeout=10)

    def _run(self):
        """后台线程：从队列取请求，调用 LLM"""
        while True:
            item = self._queue.get()
            if item is None:
                break
            messages, generation, cancelled, future, on_progress = item
            try:
                if cancelled.is_set():
                    raise CancelledError("已取消")
                if on_progress:
                    content = self._stream_call(on_progress, messages, cancelled)
                else:
                    response = self._client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                    )
                    if cancelled.is_set():
                        raise CancelledError("已取消")
                    content = response.choices[0].message.content
                with self._messages_lock:
                    if generation == self._generation and not cancelled.is_set():
                        self._messages = [*messages, {"role": "assistant", "content": content}]
                future.set_result(content)
            except Exception as e:
                future.set_exception(e)

    def _stream_call(self, on_progress: Callable[[int, float], None], messages, cancelled) -> str:
        """流式调用 LLM，定期触发 on_progress 回调，支持取消"""
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )
        chunks = []
        char_count = 0
        start = time.time()
        last_cb = 0.0

        try:
            for chunk in stream:
                if cancelled.is_set():
                    raise CancelledError("已取消")
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    chunks.append(delta.content)
                    char_count += len(delta.content)

                now = time.time()
                if now - last_cb >= 2.0:
                    on_progress(char_count, now - start)
                    last_cb = now
        finally:
            stream.close()

        # 最后一次回调
        on_progress(char_count, time.time() - start)
        return "".join(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()
