from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from engine.intent_converter import IntentConverter
from engine.intent_schema import validate_intent, validate_plan
from engine.planner import TestPlanner as Planner


@pytest.mark.parametrize("bad_step", [
    {"type": "shell", "command": "whoami"},
    {"type": "repeat", "count": -1, "steps": [{"type": "log", "message": "x"}]},
    {"type": "repeat", "count": True, "steps": [{"type": "log", "message": "x"}]},
    {"type": "wait", "seconds": -2},
    {"type": "wait", "seconds_min": 5, "seconds_max": 1},
    {"type": "call_skill", "skill": "probe", "on_fail": "ignore"},
    {"type": "set_var", "variable": "x"},
    {"type": "condition", "steps": [{"type": "log", "message": "x"}]},
])
def test_rejects_malformed_intent(intent, bad_step):
    intent["modules"][0]["steps"] = [bad_step]
    with pytest.raises(ValueError):
        validate_intent(intent)


@pytest.mark.parametrize("payload", [{}, {"name": "empty", "modules": []},
                                      {"name": "empty", "modules": [{"name": "m", "steps": []}]}])
def test_rejects_empty_plans(payload):
    with pytest.raises(ValueError):
        validate_intent(payload)


def test_valid_nested_intent_and_manual_plan(harness, intent):
    h = harness()
    intent["modules"][0]["steps"].insert(0, {"type": "repeat", "count": 2,
        "steps": [{"type": "wait", "seconds": 0}, {"type": "call_skill", "skill": "probe"}]})
    plan = IntentConverter(h.registry).convert(intent)
    assert plan["steps"][0]["steps"][0]["action"] == "repeat"
    assert validate_plan(plan, h.registry) == plan
    broken = deepcopy(plan)
    broken["steps"][0]["steps"][0]["steps"][1]["skill"] = "missing"
    with pytest.raises(ValueError, match="registered"):
        validate_plan(broken, h.registry)


def test_manual_plan_cannot_bypass_schema(harness):
    h = harness()
    for action in ("exec", "agent_loop", "shell", "call_skill", "condition", "set_var", "while_loop"):
        with pytest.raises(ValueError):
            validate_plan({"name": "bad", "steps": [{"action": action}]}, h.registry)


def test_planner_repairs_invalid_intent(harness, intent):
    h = harness()
    answers = iter([json.dumps({"name": "bad", "modules": []}), json.dumps(intent)])
    retries = []
    chat = SimpleNamespace(set_system_prompt=lambda prompt: None,
                           ask=lambda *args, **kwargs: next(answers))
    planner = Planner(chat, h.agent.prompt_builder, h.registry)
    plan = planner.generate_plan(on_retry=lambda *args: retries.append(args))
    assert plan["name"] == "Device test"
    assert len(retries) == 1
