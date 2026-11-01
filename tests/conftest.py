from pathlib import Path
from types import SimpleNamespace
import asyncio
from http.server import ThreadingHTTPServer
import threading

import pytest

from engine.agent import TestAgent as Agent
from engine.agent_service import AgentService
from engine.config import AppConfig, LLMConfig, WorkflowConfig, DiagnosticsConfig
from engine.diagnostician import FailureDiagnostician
from engine.event_bus import EventBus
from engine.intent_converter import IntentConverter
from engine.prompt_builder import PromptBuilder
from engine.plan_store import PlanStore
from engine.skill_registry import SkillRegistry
from engine.yaml_runner import YamlRunner
from shared.skill_base import BaseSkill, SkillMetadata


class CountingSkill(BaseSkill):
    def __init__(self):
        self.calls = 0
        self.result = None

    @property
    def metadata(self):
        return SkillMetadata("probe", "Read a test device", {"required": [], "optional": {}})

    def execute(self, params):
        self.calls += 1
        return self.result if self.result is not None else {"success": True, "reading": 42}


@pytest.fixture
def intent():
    return {"name": "Device test", "modules": [{"name": "Read status", "steps": [
        {"type": "call_skill", "skill": "probe", "save_as": "reading"},
        {"type": "summary", "message": "Reading: ${reading.reading}"},
    ]}]}


@pytest.fixture
def harness(tmp_path, intent):
    services = []

    def build(reporter=None, planner=None, diagnostic_chat=None, diagnostics=None):
        registry = SkillRegistry()
        skill = CountingSkill()
        registry._skills["probe"] = skill
        bus = EventBus()
        events = []
        bus.subscribe(events.append)
        builder = PromptBuilder(registry)
        if planner is None:
            planner = SimpleNamespace(generate_plan=lambda *args, **kwargs: IntentConverter(registry).convert(intent))
        reporter = reporter or SimpleNamespace(generate_report=lambda plan, results: ("unused", "# Test report\n\nPassed."))
        runner = YamlRunner(registry, bus, None)
        diagnostician = FailureDiagnostician(diagnostic_chat, diagnostics or DiagnosticsConfig(), bus)
        agent = Agent(bus, planner, reporter, registry, runner, builder, diagnostician)
        config = AppConfig(LLMConfig("http://localhost:1/v1", "test"),
                           station="test_station", workflow=WorkflowConfig("workflow.sqlite3"))
        service = AgentService(agent, config, skill_registry=registry, yaml_runner=runner,
                               root_dir=str(tmp_path), plan_store=PlanStore(str(tmp_path / "plans")))
        services.append(service)
        return SimpleNamespace(service=service, workflow=service._workflow, skill=skill,
                               agent=agent, registry=registry, runner=runner, events=events,
                               diagnostician=diagnostician,
                               root=tmp_path)

    yield build
    for service in services:
        try:
            service.close()
        except Exception:
            pass


def wait_for_worker(service):
    if service._worker:
        service._worker.join(timeout=10)
        assert not service._worker.is_alive()


@pytest.fixture
def serve_app():
    from websockets.asyncio.server import serve
    from server.http_server import create_handler
    from server.ws_server import WSServer
    applications = []

    def start(h):
        ws = WSServer()
        ready = threading.Event()
        holder = {}

        async def run_ws():
            ws._loop = asyncio.get_running_loop()
            holder["stop"] = asyncio.Event()
            async with serve(ws.handler, "127.0.0.1", 0) as server:
                h.service._config.server.ws_port = server.sockets[0].getsockname()[1]
                ready.set()
                await holder["stop"].wait()

        ws_thread = threading.Thread(target=lambda: asyncio.run(run_ws()), daemon=True)
        ws_thread.start()
        assert ready.wait(timeout=5)
        h.agent.event_bus.subscribe(ws.broadcast_sync)
        root = Path(__file__).resolve().parents[1]
        http = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(h.service, str(root / "web")))
        http_thread = threading.Thread(target=http.serve_forever, daemon=True)
        http_thread.start()
        applications.append((http, http_thread, ws, holder, ws_thread))
        return f"http://127.0.0.1:{http.server_port}"

    yield start
    for http, http_thread, ws, holder, ws_thread in applications:
        http.shutdown()
        http.server_close()
        http_thread.join(timeout=5)
        ws._loop.call_soon_threadsafe(holder["stop"].set)
        ws_thread.join(timeout=5)
