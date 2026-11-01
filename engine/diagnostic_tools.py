"""Read-only diagnostics. No device skills, arbitrary paths, or shell commands."""
import ipaddress
import json
import re
import socket
import time
from typing import Annotated, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field
from serial.tools.list_ports import comports


_SECRET_KEY = re.compile(r"password|passwd|secret|token|api[_-]?key|authorization|密码|账号", re.I)
_SECRET_VALUE = re.compile(r"(?i)((?:password|passwd|secret|token|api[_-]?key|authorization|密码|账号)\s*[:=：]\s*)[^\s,;]+")
_IP = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")


def redact(value):
    if isinstance(value, dict):
        return {str(key): "[已脱敏]" if _SECRET_KEY.search(str(key)) else redact(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)(authorization\s*[:=：]\s*)(?:Bearer|Basic)\s+[^\s,;]+", r"\1[已脱敏]", value)
        value = _SECRET_VALUE.sub(r"\1[已脱敏]", value)
        value = re.sub(r"(?i)(https?|rtsp|ssh)://[^\s]+", r"\1://[已脱敏]", value)
        return _IP.sub("[已脱敏]", value)
    return value


def bounded(value, limit):
    text = json.dumps(redact(value), ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "\n[输出已截断]"


def failure_records(results):
    records = results.get("results", []) if isinstance(results, dict) else results or []
    failed = [record for record in records if record.get("success") is False or record.get("passed") is False]
    leaves = [record for record in failed if record.get("action") not in ("group", "repeat", "while", "for_each", "if")]
    return leaves or failed


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FailureArgs(ToolArgs):
    failure_id: Annotated[int, Field(ge=1)]


class LogArgs(ToolArgs):
    tail_lines: Annotated[int, Field(ge=1, le=80)] = 30


class TcpArgs(ToolArgs):
    target: Literal["ip", "device_ip", "target_ip", "host"]
    port: Annotated[int, Field(ge=1, le=65535)]


class EmptyArgs(ToolArgs):
    pass


class DiagnosticTools:
    def __init__(self, plan, results, config, remaining_seconds=None):
        self.plan = plan
        self.results = results
        self.config = config
        self.remaining_seconds = remaining_seconds
        self.tools = {}
        for name, schema, function, description in (
            ("read_failure_details", FailureArgs, self.read_failure_details, "Read one recorded failure by its 1-based failure_id."),
            ("read_execution_log", LogArgs, self.read_execution_log, "Read the bounded tail of captured test messages and script stdout/stderr, not arbitrary files."),
            ("check_tcp_port", TcpArgs, self.check_tcp_port, "Connect without sending payload to an approved plan IP variable and an allowed port."),
            ("list_serial_ports", EmptyArgs, self.list_serial_ports, "Enumerate local serial ports without opening or writing to them."),
        ):
            self.tools[name] = StructuredTool.from_function(
                name=name, description=description, func=function, args_schema=schema,
            )

    def summary(self):
        return [{"name": tool.name, "description": tool.description,
                 "parameters": tool.args_schema.model_json_schema()} for tool in self.tools.values()]

    def invoke(self, name, arguments):
        if name not in self.tools:
            raise ValueError("tool is not in the read-only diagnostic whitelist")
        return self.tools[name].invoke(arguments)

    def read_failure_details(self, failure_id: int):
        failures = failure_records(self.results)
        if failure_id > len(failures):
            raise ValueError("failure_id does not exist")
        return {"success": True, "failure_id": failure_id,
                "details": bounded(failures[failure_id - 1], self.config.output_chars)}

    def read_execution_log(self, tail_lines: int = 30):
        lines = []
        records = self.results.get("results", [])
        for record in records[-200:]:
            for key in ("message", "error", "output"):
                if record.get(key):
                    # Bound individual outputs before splitting to avoid copying huge logs.
                    text = str(record[key])[-self.config.output_chars:]
                    lines.extend(f"{record.get('name', '')}: {line}" for line in text.splitlines())
        return {"success": True, "log": bounded(lines[-tail_lines:], self.config.output_chars)}

    def check_tcp_port(self, target: str, port: int):
        if port not in self.config.allowed_ports:
            raise ValueError("port is not in diagnostics.allowed_ports")
        # The model chooses a variable name, never an address of its own.
        value = self.plan.get("variables", {}).get(target)
        if not isinstance(value, str):
            raise ValueError("target must be an IP variable in the approved plan")
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            raise ValueError("approved target is not a literal IPv4/IPv6 address") from None
        if address.is_multicast or address.is_unspecified:
            raise ValueError("multicast and unspecified targets are not allowed")
        remaining = self.remaining_seconds() if self.remaining_seconds else self.config.tool_timeout
        if remaining <= 0:
            raise TimeoutError("diagnostic time budget exhausted")
        timeout = min(self.config.tool_timeout, remaining)
        started = time.monotonic()
        try:
            with socket.create_connection((str(address), port), timeout=timeout):
                return {"success": True, "target": target, "port": port, "reachable": True,
                        "elapsed_ms": round((time.monotonic() - started) * 1000)}
        except OSError as error:
            return {"success": True, "target": target, "port": port, "reachable": False,
                    "error_type": type(error).__name__}

    def list_serial_ports(self):
        ports = [{"device": port.device, "description": port.description} for port in list(comports())[:20]]
        return {"success": True, "ports": ports}
