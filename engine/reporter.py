"""
TestReporter - 调用 LLM 生成 markdown 测试报告（纯内容生成，不写文件）
"""
import json
from datetime import datetime

from engine.chat import Chat
from engine.prompt_builder import PromptBuilder


class TestReporter:
    """通过 LLM 生成测试报告，只返回内容，不负责文件写入"""

    def __init__(self, chat: Chat, prompt_builder: PromptBuilder):
        self.chat = chat
        self.prompt_builder = prompt_builder

    def generate_report(self, plan: dict, results) -> tuple[str, str]:
        """
        生成 markdown 测试报告

        Args:
            plan: 测试计划
            results: 测试执行结果（list[dict] 来自 TestExecutor，dict 来自 YamlRunner）

        Returns:
            (report_id, report_content)
        """
        messages = self.prompt_builder.build_reporter_prompt(results)
        if isinstance(results, dict) and results.get("diagnosis"):
            messages[0]["content"] += "\n诊断为只读检查后的推断，不得改写失败结果。系统另附诊断证据附录，请勿重复生成诊断章节。"

        # 将测试计划作为补充上下文追加到 user 消息
        plan_json = json.dumps(plan, ensure_ascii=False, indent=2)
        user_content = messages[-1]["content"] + f"\n\n对应的测试计划：\n\n```json\n{plan_json}\n```"

        self.chat.set_system_prompt(messages[0]["content"])
        report = self.chat.ask(user_content)

        report_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        return report_id, report
