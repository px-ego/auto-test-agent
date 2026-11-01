"""Typed intent contracts and validation shared by generated and edited plans."""
from copy import deepcopy
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator


Name = Annotated[str, Field(min_length=1)]
Variable = Annotated[str, Field(pattern=r"^[A-Za-z_]\w*$")]
Expression = Annotated[str, Field(pattern=r"^\$\{.+\}$")]
Count = Union[Annotated[int, Field(strict=True, ge=1, le=10000)], Expression]
Seconds = Union[Annotated[float, Field(ge=0, le=86400, allow_inf_nan=False)], Expression]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)


class Step(Contract):
    name: str = ""


class CallSkill(Step):
    type: Literal["call_skill"]
    skill: Name
    params: dict[str, Any] = Field(default_factory=dict)
    save_as: Variable | None = None
    on_fail: Literal["continue", "abort"] = "abort"
    fail_message: str | None = None
    on_fail_steps: list["IntentStep"] = Field(default_factory=list)


class Wait(Step):
    type: Literal["wait"]
    seconds: Seconds | None = None
    seconds_min: Seconds | None = None
    seconds_max: Seconds | None = None

    @model_validator(mode="after")
    def check_range(self):
        if self.seconds is None and self.seconds_min is None:
            raise ValueError("wait requires seconds or seconds_min")
        if self.seconds is not None and (self.seconds_min is not None or self.seconds_max is not None):
            raise ValueError("use either seconds or a seconds_min/seconds_max range")
        if isinstance(self.seconds_min, (int, float)) and isinstance(self.seconds_max, (int, float)):
            if self.seconds_min > self.seconds_max:
                raise ValueError("seconds_min must not exceed seconds_max")
        return self


class Repeat(Step):
    type: Literal["repeat"]
    count: Count
    steps: list["IntentStep"] = Field(min_length=1)


class While(Step):
    type: Literal["while_loop"]
    condition: Name
    max_iterations: Annotated[int, Field(strict=True, ge=1, le=10000)] = 1000
    steps: list["IntentStep"] = Field(min_length=1)


class ForEach(Step):
    type: Literal["for_each"]
    items: list[Any] | Expression
    item_var: Variable = "_item"
    steps: list["IntentStep"] = Field(min_length=1)


class Condition(Step):
    type: Literal["condition"]
    condition: Name
    steps: list["IntentStep"] = Field(min_length=1)
    else_steps: list["IntentStep"] = Field(default_factory=list)


class SetVariable(Step):
    type: Literal["set_var"]
    variable: Variable
    value: Any


class TimerStart(Step):
    type: Literal["timer_start"]
    timer: Variable


class TimerStop(Step):
    type: Literal["timer_stop"]
    timer: Variable
    accumulate: bool = False


class Message(Step):
    type: Literal["log", "summary"]
    message: str


IntentStep = Annotated[
    Union[CallSkill, Wait, Repeat, While, ForEach, Condition, SetVariable,
          TimerStart, TimerStop, Message],
    Field(discriminator="type"),
]
for _model in (CallSkill, Repeat, While, ForEach, Condition):
    _model.model_rebuild()


class Module(Contract):
    name: Name
    steps: list[IntentStep] = Field(min_length=1)


class TestIntent(Contract):
    version: str = "1.0"
    name: Name
    description: str = ""
    modules: list[Module] = Field(min_length=1)


class ExecutablePlan(Contract):
    version: str = "1.0"
    name: Name
    description: str = ""
    variables: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(min_length=1)


class AssertStep(Step):
    type: Literal["assert"]
    condition: Name
    message: str = ""
    on_fail: Literal["continue", "abort"] = "abort"
    on_fail_steps: list[dict[str, Any]] = Field(default_factory=list)


class AnalyzeStep(Step):
    type: Literal["llm_analyze"]
    prompt: Name
    save_as: Variable | None = None


class PlanCallSkill(CallSkill):
    on_fail_steps: list[dict[str, Any]] = Field(default_factory=list)


class PlanRepeat(Repeat):
    steps: list[dict[str, Any]] = Field(min_length=1)


class PlanWhile(While):
    steps: list[dict[str, Any]] = Field(min_length=1)


class PlanForEach(ForEach):
    steps: list[dict[str, Any]] = Field(min_length=1)


class PlanCondition(Condition):
    steps: list[dict[str, Any]] = Field(min_length=1)
    else_steps: list[dict[str, Any]] = Field(default_factory=list)


class PlanGroup(Contract):
    action: Literal["group"]
    name: str = ""
    steps: list[dict[str, Any]] = Field(min_length=1)


PLAN_STEP_ADAPTER = TypeAdapter(Annotated[
    Union[PlanCallSkill, Wait, PlanRepeat, PlanWhile, PlanForEach, PlanCondition,
          SetVariable, TimerStart, TimerStop, Message, AssertStep, AnalyzeStep],
    Field(discriminator="type"),
])


def _walk(steps, depth=0, budget=None):
    if not isinstance(steps, list) or depth > 20:
        raise ValueError("steps must be a list with nesting depth at most 20")
    budget = budget if budget is not None else [5000]
    for step in steps:
        budget[0] -= 1
        if budget[0] < 0 or not isinstance(step, dict):
            raise ValueError("plan must contain at most 5000 object steps")
        yield step
        for key in ("steps", "else_steps", "on_fail_steps"):
            if key in step:
                yield from _walk(step[key], depth + 1, budget)


def validate_intent(intent: dict) -> dict:
    if isinstance(intent, dict):
        list(_walk(intent.get("modules", [])))
    return TestIntent.model_validate(intent).model_dump(exclude_unset=True)


def validate_plan(plan: dict, registry) -> dict:
    """Validate the DSL at every entry point, including manual edits and imports."""
    validated = ExecutablePlan.model_validate(plan).model_dump(exclude_unset=True)
    aliases = {"skill": "call_skill", "while": "while_loop", "if": "condition",
               "set_variable": "set_var"}
    for step in _walk(validated["steps"]):
        if step.get("action") == "group":
            PlanGroup.model_validate(step)
            continue
        canonical = deepcopy(step)
        action = canonical.pop("action", "")
        if action not in {"skill", "wait", "repeat", "while", "for_each", "if", "set_variable",
                          "timer_start", "timer_stop", "log", "summary", "assert", "llm_analyze"}:
            raise ValueError(f"unsupported DSL action: {action}")
        canonical["type"] = aliases.get(action, action)
        if "save_result_as" in canonical:
            canonical["save_as"] = canonical.pop("save_result_as")
        if action in ("log", "summary"):
            params = canonical.pop("params", {})
            if not isinstance(params, dict) or set(params) - {"message"}:
                raise ValueError("log/summary params may only contain message")
            canonical["message"] = params.get("message", "")
        PLAN_STEP_ADAPTER.validate_python(canonical)
        if action == "skill" and (not registry or not registry.get(step["skill"])):
            raise ValueError(f"skill is not registered: {step['skill']}")
    return deepcopy(validated)
