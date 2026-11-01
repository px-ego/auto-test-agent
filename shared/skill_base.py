"""
BaseSkill - 测试技能基类（零依赖层，供 skills 和 engine 共同引用）
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class SkillMetadata:
    """技能元数据"""
    def __init__(self, action: str, description: str, params: Dict[str, Any]):
        self.action = action
        self.description = description
        self.params = params


class BaseSkill(ABC):
    """测试技能基类"""

    @property
    @abstractmethod
    def metadata(self) -> SkillMetadata:
        """返回技能元数据"""
        pass

    def validate(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        验证参数

        Args:
            params: 参数字典

        Returns:
            (是否有效, 错误信息)
        """
        # 默认实现：检查必需参数
        required = self.metadata.params.get('required', [])
        for param in required:
            if param not in params:
                return False, f"缺少必需参数: {param}"
        return True, None

    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行技能

        Args:
            params: 参数字典

        Returns:
            执行结果字典，至少包含 'success' 字段
        """
        pass
