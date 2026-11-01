"""
TestPlanner - 调用 LLM 生成 JSON 测试意图，再通过 IntentConverter 转换为 YamlRunner plan dict
"""
import json
import re

from engine.chat import Chat
from engine.prompt_builder import PromptBuilder
from engine.skill_registry import SkillRegistry
from engine.intent_converter import IntentConverter, IntentConvertError


class TestPlanner:
    """通过 LLM 生成测试计划（JSON 意图 → IntentConverter → plan dict）"""

    MAX_RETRIES = 2

    def __init__(self, chat: Chat, prompt_builder: PromptBuilder,
                 skill_registry: SkillRegistry = None):
        self.chat = chat
        self.prompt_builder = prompt_builder
        self.skill_registry = skill_registry

    def generate_plan(self, user_instruction: str = "", format: str = "yaml",
                      on_progress=None, on_retry=None) -> dict:
        messages = self.prompt_builder.build_planner_prompt(user_instruction)
        self.chat.set_system_prompt(messages[0]["content"])
        content = self.chat.ask(messages[1]["content"], on_progress=on_progress)

        converter = IntentConverter(self.skill_registry)

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                intent = self._parse_json(content)
                return converter.convert(intent)
            except (IntentConvertError, ValueError) as e:
                if attempt >= self.MAX_RETRIES:
                    raise ValueError(f"重试 {self.MAX_RETRIES} 次后仍无法生成合法计划: {e}")
                if on_retry:
                    on_retry(attempt, self.MAX_RETRIES, str(e))
                content = self.chat.ask(
                    f"你生成的计划校验失败：{e}\n请修正后重新输出完整的 JSON。",
                    on_progress=on_progress,
                )

    @staticmethod
    def _parse_json(text: str) -> dict:
        if not text:
            raise ValueError("LLM 返回了空响应，请重试")

        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        json_str = match.group(1).strip() if match else text.strip()

        try:
            result = json.loads(json_str)
            if not isinstance(result, dict):
                raise ValueError("JSON 解析结果不是字典")
            return result
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM 返回的内容无法解析为 JSON: {e}")
