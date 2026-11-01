"""
plan_exporter - 测试计划导出/导入（zip 打包）

导出：计划 + 知识文档 + 技能组 → zip 字节流
导入：zip 字节流 → 解包技能到磁盘，返回计划和知识文档
"""
import io
import json
import os
import zipfile

import yaml


def _collect_skill_names(steps: list) -> set[str]:
    """递归扫描 steps，收集所有 action:'skill' 引用的技能名称"""
    names = set()
    if not steps:
        return names
    for step in steps:
        if step.get("action") == "skill" and step.get("skill"):
            names.add(step["skill"])
        # 递归嵌套步骤
        for key in ("steps", "on_fail_steps", "else_steps"):
            names |= _collect_skill_names(step.get(key) or [])
    return names


def export_plan_zip(
    plan: dict,
    knowledge_texts: list[str],
    station_name: str,
    root_dir: str,
) -> bytes:
    """将计划、知识文档、引用的技能打包为 zip，返回字节流"""
    skill_names = _collect_skill_names(plan.get("steps") or [])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # manifest.json
        manifest = {
            "station_name": station_name,
            "skills": sorted(skill_names),
            "version": "1.0",
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        # plan_bundle.yaml（与 PlanStore 格式一致）
        bundle = {
            "plan": plan,
            "knowledge_texts": knowledge_texts or [],
            "yaml_plan": plan,
        }
        zf.writestr(
            "plan_bundle.yaml",
            yaml.dump(bundle, allow_unicode=True, default_flow_style=False, sort_keys=False),
        )

        # 技能目录（仅计划引用的，不含 common）
        station_skills_dir = os.path.join(root_dir, "skills", station_name)
        for skill_name in sorted(skill_names):
            skill_dir = os.path.join(station_skills_dir, skill_name)
            if not os.path.isdir(skill_dir):
                continue
            for dirpath, dirnames, filenames in os.walk(skill_dir):
                # 跳过 __pycache__
                dirnames[:] = [d for d in dirnames if d != "__pycache__"]
                for fname in filenames:
                    if fname.endswith(".pyc"):
                        continue
                    full_path = os.path.join(dirpath, fname)
                    arc_name = os.path.join(
                        "skills",
                        skill_name,
                        os.path.relpath(full_path, skill_dir),
                    )
                    zf.write(full_path, arc_name)

    return buf.getvalue()


def import_plan_zip(zip_bytes: bytes, root_dir: str) -> dict:
    """
    解包 zip，将技能文件写入磁盘，返回 {station_name, plan, knowledge_texts}。

    安全检查：拒绝含 '..' 或以 '/' 开头的路径。
    """
    buf = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(buf, "r") as zf:
        # 安全检查
        for name in zf.namelist():
            if ".." in name or name.startswith("/"):
                raise ValueError(f"zip 包含不安全路径: {name}")

        # 校验必要文件
        names = set(zf.namelist())
        if "manifest.json" not in names:
            raise ValueError("zip 缺少 manifest.json")
        if "plan_bundle.yaml" not in names:
            raise ValueError("zip 缺少 plan_bundle.yaml")

        # 读取 manifest
        manifest = json.loads(zf.read("manifest.json"))
        station_name = manifest["station_name"]

        # 读取 plan bundle
        bundle = yaml.safe_load(zf.read("plan_bundle.yaml"))
        plan = bundle.get("yaml_plan") or bundle["plan"]
        knowledge_texts = bundle.get("knowledge_texts") or []

        # 写入技能文件到 skills/<station_name>/
        station_skills_dir = os.path.join(root_dir, "skills", station_name)
        for entry in zf.namelist():
            if not entry.startswith("skills/"):
                continue
            # skills/<skill_name>/... → skills/<station_name>/<skill_name>/...
            rel = entry[len("skills/"):]  # e.g. "power_on/skill.py"
            if not rel or entry.endswith("/"):
                continue
            dest = os.path.join(station_skills_dir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(zf.read(entry))

    return {
        "station_name": station_name,
        "plan": plan,
        "knowledge_texts": knowledge_texts,
    }
