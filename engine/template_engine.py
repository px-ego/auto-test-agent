"""
TemplateEngine - 变量解析与表达式求值
"""
import re
import time
import random
from typing import Any

from simpleeval import simple_eval, EvalWithCompoundTypes


# ${...} 模式匹配
_TEMPLATE_RE = re.compile(r'\$\{([^}]+)\}')


class TemplateEngine:
    """管理变量上下文，提供模板替换和表达式求值"""

    def __init__(self, variables: dict = None):
        self.variables: dict = dict(variables or {})

    def set(self, key: str, value: Any):
        self.variables[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)

    def resolve(self, value: Any) -> Any:
        """
        递归解析值中的 ${var} 占位符。

        - 字符串：替换所有 ${...} 引用
        - dict / list：递归处理
        - 其他类型：原样返回
        """
        if isinstance(value, str):
            return self._resolve_string(value)
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(item) for item in value]
        return value

    def resolve_expr(self, text: str) -> Any:
        """
        解析字符串，如果整个字符串是单个 ${expr} 则求值返回原始类型，
        否则做字符串插值。
        """
        if not isinstance(text, str):
            return text

        # 整个字符串恰好是一个 ${expr}
        m = re.fullmatch(r'\$\{(.+)\}', text.strip())
        if m:
            return self._eval(m.group(1).strip())

        # 多个占位符混合文本 → 字符串插值
        return self._resolve_string(text)

    def eval_condition(self, condition: str) -> bool:
        """求值布尔条件表达式，返回 bool"""
        resolved = self._resolve_string(condition)
        result = self._eval(resolved)
        return bool(result)

    def resolve_params(self, params: dict) -> dict:
        """递归解析 dict 中所有值"""
        return self.resolve(params)

    # ── 内部方法 ──────────────────────────────────────────

    def _resolve_string(self, text: str) -> Any:
        """
        替换字符串中的 ${...} 占位符。
        如果整个字符串恰好是单个占位符，返回原始类型（int/dict 等）。
        """
        matches = list(_TEMPLATE_RE.finditer(text))
        if not matches:
            return text

        # 整个字符串就是一个 ${expr}
        if len(matches) == 1 and matches[0].start() == 0 and matches[0].end() == len(text):
            return self._eval(matches[0].group(1).strip())

        # 多个占位符或混合文本 → 全部替换为字符串
        def replacer(m):
            return str(self._eval(m.group(1).strip()))

        return _TEMPLATE_RE.sub(replacer, text)

    def _eval(self, expr: str) -> Any:
        """
        求值表达式。先尝试简单变量查找（含点号访问），
        再回退到 simpleeval 做算术/比较运算。
        """
        # 简单变量名（如 fail_count）
        if re.fullmatch(r'[a-zA-Z_]\w*', expr):
            if expr in self.variables:
                return self.variables[expr]

        # 点号访问（如 result.success）— 先尝试直接查找
        if re.fullmatch(r'[a-zA-Z_]\w*(\.\w+)+', expr):
            val = self._dot_access(expr)
            if val is not _SENTINEL:
                return val

        # simpleeval 求值
        evaluator = EvalWithCompoundTypes(names=self.variables, functions={
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "abs": abs,
            "min": min,
            "max": max,
            "round": round,
            "time": time.time,
            "random_int": random.randint,
            "random_float": lambda a, b: round(random.uniform(a, b), 2),
        })
        return evaluator.eval(expr)

    def _dot_access(self, expr: str) -> Any:
        """处理 a.b.c 形式的属性/键访问"""
        parts = expr.split('.')
        obj = self.variables.get(parts[0], _SENTINEL)
        if obj is _SENTINEL:
            return _SENTINEL
        for part in parts[1:]:
            if isinstance(obj, dict):
                if part in obj:
                    obj = obj[part]
                else:
                    return _SENTINEL
            elif hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                return _SENTINEL
        return obj


# 哨兵值，区分 None 和"未找到"
_SENTINEL = object()
