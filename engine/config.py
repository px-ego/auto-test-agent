"""
AppConfig - 类型化配置，替代原始 dict 传递
"""
from dataclasses import dataclass, field
from typing import Optional

import yaml


@dataclass
class LLMConfig:
    base_url: str
    model: str
    api_key: str = "EMPTY"
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class ServerConfig:
    host: str = "0.0.0.0"
    http_port: int = 8080
    ws_port: int = 8081


@dataclass
class ReportsConfig:
    output_dir: str = "reports"
    format: str = "markdown"


@dataclass
class PlansConfig:
    output_dir: str = "plans"


@dataclass
class WorkflowConfig:
    database_path: str = "data/workflow.sqlite3"


@dataclass
class DiagnosticsConfig:
    enabled: bool = True
    max_rounds: int = 4
    max_tool_calls: int = 3
    max_seconds: float = 90
    llm_timeout: float = 20
    tool_timeout: float = 2
    output_chars: int = 5000
    allowed_ports: list[int] = field(default_factory=lambda: [22, 80, 443])

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("diagnostics.enabled must be boolean")
        for name, low, high in (("max_rounds", 1, 8), ("max_tool_calls", 0, 8), ("output_chars", 1000, 12000)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"diagnostics.{name} must be between {low} and {high}")
        for name, low, high in (("max_seconds", 1, 300), ("llm_timeout", 0.1, 60), ("tool_timeout", 0.1, 5)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
                raise ValueError(f"diagnostics.{name} must be between {low} and {high}")
        if not isinstance(self.allowed_ports, list) or any(type(port) is not int or not 1 <= port <= 65535 for port in self.allowed_ports):
            raise ValueError("diagnostics.allowed_ports must contain valid port numbers")


@dataclass
class AppConfig:
    llm: LLMConfig
    station: str = "virtual_device"
    server: ServerConfig = field(default_factory=ServerConfig)
    reports: ReportsConfig = field(default_factory=ReportsConfig)
    plans: PlansConfig = field(default_factory=PlansConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    diagnostics: DiagnosticsConfig = field(default_factory=DiagnosticsConfig)

    @classmethod
    def from_yaml(cls, path: str) -> "AppConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        llm = LLMConfig(**raw.get("llm", {}))
        server = ServerConfig(**raw.get("server", {}))
        reports = ReportsConfig(**raw.get("reports", {}))
        plans = PlansConfig(**raw.get("plans", {}))
        workflow = WorkflowConfig(**raw.get("workflow", {}))
        diagnostics = DiagnosticsConfig(**raw.get("diagnostics", {}))

        return cls(
            llm=llm,
            station=raw.get("station", "virtual_device"),
            server=server,
            reports=reports,
            plans=plans,
            workflow=workflow,
            diagnostics=diagnostics,
        )
