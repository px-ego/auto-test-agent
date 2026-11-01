import json
import socket
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from conftest import wait_for_worker
from engine.intent_converter import IntentConverter


def request(base, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(base + path, data=body, headers={"Content-Type": "application/json"})
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())


def test_http_review_execution_and_invalid_plan(harness, serve_app, intent):
    h = harness()
    task = h.workflow.create("test_station", [], IntentConverter(h.registry).convert(intent))
    base = serve_app(h)
    start = {"task_id": task["task_id"], "revision": 1}
    assert request(base, "/api/start-test", start)[0] == 409
    review = {**start, "approved": "true"}
    assert request(base, "/api/review-plan", review)[0] == 400
    bad_plan = {"name": "unsafe", "steps": [{"action": "exec", "command": "echo"}]}
    assert request(base, "/api/update-plan", {**start, "plan": bad_plan})[0] == 400
    review["approved"] = True
    code, approved = request(base, "/api/review-plan", review)
    assert code == 200
    assert approved["task"]["state"] == "approved"
    assert request(base, "/api/start-test", {**start, "variables": {"changed": 7}})[0] == 409
    assert request(base, "/api/start-test", start)[0] == 200
    wait_for_worker(h.service)
    code, state = request(base, "/api/state")
    assert code == 200 and state["state"] == "done"
    assert request(base, "/api/start-test", start)[0] == 409
    assert request(base, "/api/tasks/missing")[0] == 404
    assert h.skill.calls == 1


def test_saved_plan_load_requires_fresh_review(harness, serve_app, intent):
    h = harness()
    plan_id = h.service.save_plan(IntentConverter(h.registry).convert(intent))
    base = serve_app(h)
    code, loaded = request(base, "/api/load-plan", {"plan_id": plan_id})
    assert code == 200
    assert loaded["task"]["state"] == "awaiting_review"
    assert loaded["task"]["approval"] is None
    assert request(base, "/api/start-test", {"task_id": loaded["task"]["task_id"], "revision": 1})[0] == 409


def test_idle_browser_connection_does_not_block_state_restore(harness, serve_app):
    base = serve_app(harness())
    target = urlparse(base)
    with socket.create_connection((target.hostname, target.port), timeout=2):
        assert request(base, "/api/state")[0] == 200
