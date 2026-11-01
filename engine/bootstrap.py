"""
bootstrap - 依赖组装，构造完整依赖图
"""
import os
import time
import glob as glob_mod

from engine.config import AppConfig
from engine.event_bus import EventBus
from engine.skill_registry import SkillRegistry
from engine.chat import Chat
from engine.prompt_builder import PromptBuilder
from engine.planner import TestPlanner
from engine.reporter import TestReporter
from engine.agent import TestAgent
from engine.agent_service import AgentService
from engine.plan_store import PlanStore
from engine.yaml_runner import YamlRunner
from engine.diagnostician import FailureDiagnostician
from knowledge.loader import load_knowledge


def _load_template(path: str) -> str:
    """读取模板文件，返回内容字符串"""
    path = os.path.normpath(path)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _load_station_knowledge(station_dir: str) -> list[str]:
    """加载技能组下所有知识文档"""
    knowledge_dir = os.path.join(station_dir, 'knowledge')
    texts = []
    if not os.path.isdir(knowledge_dir):
        return texts
    for fp in sorted(glob_mod.glob(os.path.join(knowledge_dir, '*.md'))):
        _, body = load_knowledge(fp)
        if body:
            texts.append(body)
    return texts


def _make_chat(llm, temperature=None) -> Chat:
    """创建 Chat 实例的工厂函数"""
    return Chat(
        base_url=llm.base_url,
        model=llm.model,
        api_key=llm.api_key,
        temperature=temperature if temperature is not None else llm.temperature,
        max_tokens=llm.max_tokens,
    )


def create_agent(config: AppConfig, root_dir: str) -> tuple[AgentService, EventBus, list[Chat]]:
    """
    组装完整依赖图。

    Returns:
        (service, event_bus, chats) — chats 列表用于生命周期管理
    """
    total_start = time.time()
    station_name = config.station
    station_dir = os.path.join(root_dir, 'skills', station_name)

    # 发现技能
    t0 = time.time()
    registry = SkillRegistry()
    common_dir = os.path.join(root_dir, 'skills', 'common')
    registry.discover(common_dir, station_dir)
    print(f"[Bootstrap] 已加载 {len(registry.list_skills())} 个技能: {', '.join(registry.list_skills().keys())} ({time.time() - t0:.2f}s)")

    # 加载设备知识
    t0 = time.time()
    knowledge_texts = _load_station_knowledge(station_dir)
    print(f"[Bootstrap] 已加载 {len(knowledge_texts)} 份知识文档 ({time.time() - t0:.2f}s)")

    # 读取模板文件（一次性读入，注入到 PromptBuilder）
    t0 = time.time()
    skills_common = os.path.join(root_dir, 'skills', 'common')
    plan_template = _load_template(os.path.join(skills_common, 'generate_yaml_plan', 'skill.md'))
    report_template = _load_template(os.path.join(skills_common, 'generate_report', 'skill.md'))
    print(f"[Bootstrap] 加载提示词模板 ({time.time() - t0:.2f}s)")

    # 构造 Chat 实例
    t0 = time.time()
    llm = config.llm
    planner_chat = _make_chat(llm)
    reporter_chat = _make_chat(llm, temperature=0.3)
    runner_chat = _make_chat(llm, temperature=0.3)
    diagnostic_chat = Chat(
        base_url=llm.base_url, model=llm.model, api_key=llm.api_key,
        temperature=0.1, max_tokens=min(llm.max_tokens, 2048),
        request_timeout=min(config.diagnostics.llm_timeout, config.diagnostics.max_seconds),
        max_retries=0,
    )
    print(f"[Bootstrap] 初始化 Chat 实例 ({time.time() - t0:.2f}s)")

    # 构造组件
    t0 = time.time()
    event_bus = EventBus()
    prompt_builder = PromptBuilder(
        registry, knowledge_texts,
        plan_template=plan_template,
        report_template=report_template,
    )
    planner = TestPlanner(planner_chat, prompt_builder, skill_registry=registry)
    reporter = TestReporter(reporter_chat, prompt_builder)
    yaml_runner = YamlRunner(registry, event_bus, runner_chat)
    diagnostician = FailureDiagnostician(diagnostic_chat, config.diagnostics, event_bus)

    # 构造 Agent（所有依赖通过构造函数注入）
    agent = TestAgent(
        event_bus=event_bus,
        planner=planner,
        reporter=reporter,
        skill_registry=registry,
        yaml_runner=yaml_runner,
        prompt_builder=prompt_builder,
        diagnostician=diagnostician,
    )

    # 构造 Service
    plan_store = PlanStore(os.path.join(root_dir, config.plans.output_dir))
    service = AgentService(
        agent, config,
        plan_store=plan_store,
        skill_registry=registry,
        yaml_runner=yaml_runner,
        root_dir=root_dir,
        planner_chat=planner_chat,
    )
    print(f"[Bootstrap] 组装完成 ({time.time() - t0:.2f}s)")
    print(f"[Bootstrap] 初始化总耗时: {time.time() - total_start:.2f}s")

    return service, event_bus, [planner_chat, reporter_chat, runner_chat, diagnostic_chat]
