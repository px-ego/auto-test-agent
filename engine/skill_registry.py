"""
SkillRegistry - 技能注册表，支持多目录加载
"""
import os
import importlib.util
from typing import Dict, Optional
from shared.skill_base import BaseSkill


class SkillRegistry:
    """技能注册表，支持从多个目录加载技能，后加载的覆盖先加载的同名技能"""

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}
        self._skill_docs: Dict[str, str] = {}  # action -> skill.md 内容

    def discover(self, *dirs: str):
        """
        从多个目录发现并加载技能。后面的目录覆盖前面的同名技能。

        Args:
            dirs: 技能目录路径列表
        """
        for d in dirs:
            if not os.path.isdir(d):
                continue
            for name in sorted(os.listdir(d)):
                skill_dir = os.path.join(d, name)
                skill_py = os.path.join(skill_dir, 'skill.py')
                if not os.path.isfile(skill_py):
                    continue
                skill = self._load_skill(skill_py, name)
                if skill:
                    action = skill.metadata.action
                    self._skills[action] = skill
                    # 读取同目录的 skill.md
                    skill_md = os.path.join(skill_dir, 'skill.md')
                    if os.path.isfile(skill_md):
                        try:
                            with open(skill_md, 'r', encoding='utf-8') as f:
                                self._skill_docs[action] = f.read()
                        except Exception:
                            pass

    def _load_skill(self, path: str, name: str) -> Optional[BaseSkill]:
        """从 skill.py 文件加载技能实例"""
        try:
            spec = importlib.util.spec_from_file_location(f"skill_{name}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            # 优先使用 skill_class 模块变量
            if hasattr(mod, 'skill_class'):
                return mod.skill_class()

            # 自动检测 BaseSkill 子类
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (isinstance(attr, type)
                        and issubclass(attr, BaseSkill)
                        and attr is not BaseSkill):
                    return attr()
        except Exception as e:
            print(f"[SkillRegistry] 加载技能 {name} 失败: {e}")
        return None

    def get(self, action: str) -> Optional[BaseSkill]:
        """获取指定 action 的技能"""
        return self._skills.get(action)

    def list_skills(self) -> Dict[str, BaseSkill]:
        """返回所有已注册技能"""
        return dict(self._skills)

    def summary(self) -> list[dict]:
        """返回所有技能的摘要信息（用于 API 和 prompt）"""
        result = []
        for action, skill in self._skills.items():
            meta = skill.metadata
            item = {
                'action': meta.action,
                'description': meta.description,
                'params': meta.params,
            }
            # 如果有 skill.md 文档，也带上
            if action in self._skill_docs:
                item['documentation'] = self._skill_docs[action]
            result.append(item)
        return result
