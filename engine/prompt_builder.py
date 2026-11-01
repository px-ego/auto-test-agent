"""
PromptBuilder - 根据技能注册表和知识库动态构建 LLM 提示词

模板字符串由外部（bootstrap）注入，本模块不读文件。
"""
import json
from typing import Optional

from engine.skill_registry import SkillRegistry
from engine.intent_schema import TestIntent


class PromptBuilder:
    """根据技能列表和知识文本构建规划/报告提示词"""

    def __init__(
        self,
        skill_registry: SkillRegistry,
        knowledge_texts: Optional[list[str]] = None,
        plan_template: str = "",
        report_template: str = "",
    ):
        self.skill_registry = skill_registry
        self.knowledge_texts: list[str] = knowledge_texts or []
        self._plan_template = plan_template
        self._report_template = report_template

    def build_planner_prompt(self, user_instruction: str = "") -> list[dict]:
        """构建 YAML 测试计划生成的 system + user 消息"""
        skills_info = json.dumps(self.skill_registry.summary(), ensure_ascii=False, indent=2)

        knowledge_block = ""
        if self.knowledge_texts:
            knowledge_block = "\n\n## 设备知识\n\n" + "\n\n---\n\n".join(self.knowledge_texts)

        system = self._plan_template.replace('{{skills}}', f"```json\n{skills_info}\n```")
        system = system.replace('{{knowledge}}', knowledge_block)
        system += "\n\n## JSON Schema\n" + json.dumps(TestIntent.model_json_schema(), ensure_ascii=False)

        messages: list[dict] = [{"role": "system", "content": system}]

        user_content = user_instruction if user_instruction else "请根据可用技能和设备知识，生成一份可执行的测试计划。"
        messages.append({"role": "user", "content": user_content})

        return messages

    def build_reporter_prompt(self, test_results) -> list[dict]:
        """构建测试报告生成的 system + user 消息"""
        system = self._report_template

        if self.knowledge_texts:
            knowledge_block = "\n\n## 设备知识\n\n" + "\n\n---\n\n".join(self.knowledge_texts)
            system += knowledge_block

        results_json = json.dumps(test_results, ensure_ascii=False, indent=2)
        user_content = f"以下是测试执行结果，请生成测试报告：\n\n```json\n{results_json}\n```"

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

    def add_knowledge(self, text: str):
        """添加知识文本"""
        self.knowledge_texts.append(text)
