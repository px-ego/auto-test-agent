"""
PlanStore - 测试计划持久化存储（完整 bundle：计划 + 知识文档 + YAML 可执行计划）
"""
import os
import time
from typing import Optional

import yaml


class PlanStore:
    """将测试计划及其完整上下文以 YAML 文件形式持久化到磁盘"""

    def __init__(self, output_dir: str = "plans"):
        self._dir = output_dir
        os.makedirs(self._dir, exist_ok=True)

    def save(self, plan: dict, knowledge_texts: list[str] = None,
             plan_id: str = None) -> str:
        """保存完整 bundle，返回 plan_id"""
        if not plan_id:
            plan_id = str(int(time.time() * 1000))

        bundle = {
            "plan": plan,
            "knowledge_texts": knowledge_texts or [],
            "yaml_plan": plan,
        }

        path = os.path.join(self._dir, f"plan_{plan_id}.yaml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(bundle, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return plan_id

    def load(self, plan_id: str) -> Optional[dict]:
        """加载完整 bundle，返回 {plan, knowledge_texts, yaml_plan}"""
        path = os.path.join(self._dir, f"plan_{plan_id}.yaml")
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # 兼容旧格式（直接存的 plan dict，没有 bundle 包装）
        if isinstance(data, dict) and "plan" in data:
            return data
        # 旧格式：整个文件就是 plan
        return {"plan": data, "knowledge_texts": [], "yaml_plan": None}

    def delete(self, plan_id: str) -> bool:
        """删除指定计划"""
        path = os.path.join(self._dir, f"plan_{plan_id}.yaml")
        if os.path.isfile(path):
            os.remove(path)
            return True
        return False

    def list_plans(self) -> list[dict]:
        """列出所有已保存计划，按时间倒序"""
        plans = []
        if not os.path.isdir(self._dir):
            return plans

        for fname in os.listdir(self._dir):
            if not fname.startswith("plan_") or not fname.endswith(".yaml"):
                continue
            plan_id = fname[5:-5]  # strip "plan_" and ".yaml"
            path = os.path.join(self._dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                # 兼容新旧格式提取 name/description
                if "plan" in data and isinstance(data["plan"], dict):
                    plan_data = data["plan"]
                else:
                    plan_data = data
                plans.append({
                    "plan_id": plan_id,
                    "name": plan_data.get("name", "未命名计划"),
                    "description": plan_data.get("description", ""),
                    "created_at": os.path.getmtime(path),
                })
            except Exception:
                continue

        plans.sort(key=lambda p: p["created_at"], reverse=True)
        return plans
