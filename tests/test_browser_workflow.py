from pathlib import Path

import pytest
from langgraph.types import Command

from engine.intent_converter import IntentConverter
from test_diagnostics import ScriptedChat, tool, final


@pytest.mark.browser
@pytest.mark.parametrize("viewport", [{"width": 1440, "height": 1000}, {"width": 390, "height": 844}])
def test_review_edit_reload_execute_and_report(harness, serve_app, intent, viewport):
    api = pytest.importorskip("playwright.sync_api")
    h = harness()
    h.workflow.create("test_station", [], IntentConverter(h.registry).convert(intent))
    base = serve_app(h)
    chrome = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, **({"executable_path": str(chrome)} if chrome.is_file() else {}))
        page = browser.new_page(viewport=viewport)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base)
        api.expect(page.locator("#review-status")).to_contain_text("待审核")
        api.expect(page.locator("#btn-start-test")).to_be_disabled()
        page.locator("#review-comment").fill("Checked in browser")
        page.locator("#btn-approve-plan").click()
        api.expect(page.locator("#btn-start-test")).to_be_enabled()
        page.reload()
        api.expect(page.locator("#btn-start-test")).to_be_enabled()
        page.locator('.yaml-edit-btn[data-path="0"]').click()
        page.locator("#edit-name").fill("Reviewed device checks")
        page.locator(".yaml-edit-overlay").get_by_role("button", name="保存", exact=True).click()
        api.expect(page.locator("#btn-start-test")).to_be_disabled()
        page.locator("#btn-approve-plan").click()
        api.expect(page.locator("#review-status")).to_contain_text("版本 2")
        api.expect(page.locator("#btn-start-test")).to_be_enabled()
        screenshot = Path(__file__).resolve().parents[1] / ".local" / f"review-{viewport['width']}.png"
        screenshot.parent.mkdir(exist_ok=True)
        page.screenshot(path=str(screenshot), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#btn-start-test").click()
        api.expect(page.locator("#btn-view-report")).to_have_text("查看报告", timeout=10000)
        page.locator("#btn-view-report").click()
        api.expect(page.locator("#report-content")).to_contain_text("Test report")
        page.reload()
        api.expect(page.locator("#report-content")).to_be_visible()
        assert h.skill.calls == 1
        assert len(h.service.get_state()["reviews"]) == 2
        assert errors == []
        browser.close()


@pytest.mark.browser
def test_upload_generate_and_restore_pending_review(harness, serve_app):
    api = pytest.importorskip("playwright.sync_api")
    h = harness()
    base = serve_app(h)
    chrome = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, **({"executable_path": str(chrome)} if chrome.is_file() else {}))
        page = browser.new_page()
        page.goto(base)
        page.locator("#file-input").set_input_files({"name": "device.md", "mimeType": "text/markdown", "buffer": b"Device knowledge for a test fixture"})
        page.locator("#btn-generate-plan").click()
        api.expect(page.locator("#phase-plan")).to_be_visible()
        api.expect(page.locator("#review-status")).to_contain_text("待审核")
        page.reload()
        api.expect(page.locator("#review-status")).to_contain_text("待审核")
        api.expect(page.locator("#btn-start-test")).to_be_disabled()
        assert h.skill.calls == 0
        browser.close()


@pytest.mark.browser
@pytest.mark.parametrize("viewport", [{"width": 1440, "height": 1000}, {"width": 390, "height": 844}])
def test_failed_test_displays_diagnostic_evidence_and_report(harness, serve_app, intent, viewport):
    api = pytest.importorskip("playwright.sync_api")
    h = harness(diagnostic_chat=ScriptedChat([tool(), final()]))
    h.skill.result = {"success": False, "error": "Device connection failed", "output": "No response from the device"}
    h.workflow.create("test_station", [], IntentConverter(h.registry).convert(intent))
    base = serve_app(h)
    chrome = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, **({"executable_path": str(chrome)} if chrome.is_file() else {}))
        page = browser.new_page(viewport=viewport)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base)
        page.locator("#btn-approve-plan").click()
        api.expect(page.locator("#btn-start-test")).to_be_enabled()
        page.locator("#btn-start-test").click()
        api.expect(page.locator("#btn-view-report")).to_have_text("查看报告", timeout=10000)
        api.expect(page.locator("#diagnosis-panel")).to_be_visible()
        api.expect(page.locator("#diagnosis-status")).to_contain_text("诊断完成")
        api.expect(page.locator("#diagnosis-trace")).to_contain_text("read_execution_log")
        api.expect(page.locator("#diagnosis-evidence")).to_contain_text("check-1")
        api.expect(page.locator("#btn-stop-diagnosis")).to_be_hidden()
        page.locator("#diagnosis-evidence summary").first.click()
        path = Path(__file__).resolve().parents[1] / ".local" / f"diagnosis-{viewport['width']}.png"
        page.screenshot(path=str(path), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#btn-view-report").click()
        api.expect(page.locator("#report-content")).to_contain_text("失败诊断")
        page.reload()
        api.expect(page.locator("#report-content")).to_contain_text("check-1")
        page.locator("#btn-show-diagnosis").click()
        api.expect(page.locator("#diagnosis-panel")).to_be_visible()
        api.expect(page.locator("#diagnosis-summary")).to_contain_text("Device check failed")
        assert h.skill.calls == 1 and errors == []
        browser.close()


@pytest.mark.browser
def test_browser_resumes_interrupted_read_only_diagnosis(harness, serve_app, intent):
    api = pytest.importorskip("playwright.sync_api")
    h = harness(diagnostic_chat=ScriptedChat([tool()]))
    h.skill.result = {"success": False, "error": "Probe failed"}
    task = h.workflow.create("test_station", [], IntentConverter(h.registry).convert(intent))
    h.service.review_plan(task["task_id"], 1, True)
    h.workflow.graph.invoke(Command(resume={"start": True, "revision": 1}),
                            h.workflow._config(task["task_id"]), interrupt_after=["diagnostic_tool"])
    h.service.close()
    restored = harness(diagnostic_chat=ScriptedChat([final()]))
    base = serve_app(restored)
    chrome = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, **({"executable_path": str(chrome)} if chrome.is_file() else {}))
        page = browser.new_page()
        page.goto(base)
        api.expect(page.locator("#btn-resume-diagnosis")).to_be_visible()
        page.locator("#btn-resume-diagnosis").click()
        api.expect(page.locator("#btn-view-report")).to_have_text("查看报告", timeout=10000)
        api.expect(page.locator("#diagnosis-status")).to_contain_text("诊断完成")
        assert restored.skill.calls == 0
        browser.close()
