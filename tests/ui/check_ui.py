"""Exercise real Norwegian HA dialogs on fresh install and upgrade from 0.1.12."""

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import requests
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "ui-artifacts"
ARTIFACTS.mkdir(exist_ok=True)
BASE = "http://127.0.0.1:8123"


def start_server(config_dir, source, name):
    onboarded = (config_dir / ".storage" / "onboarding").exists()
    log = (ARTIFACTS / f"{name}-server.log").open("w")
    process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("serve.py")), str(config_dir), str(source)], stdout=log, stderr=subprocess.STDOUT)
    for _ in range(180):
        if process.poll() is not None:
            raise RuntimeError(f"Home Assistant exited; see {name}-server.log")
        try:
            if requests.get(BASE + ("/" if onboarded else "/api/onboarding"), timeout=3).status_code == 200:
                return process, log
        except requests.RequestException:
            pass
        time.sleep(2)
    process.terminate()
    process.wait(timeout=60)
    log.close()
    raise TimeoutError("Home Assistant startup timed out")


def stop_server(server):
    process, log = server
    process.terminate()
    try:
        process.wait(timeout=60)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    log.close()


def onboard():
    result = requests.post(BASE + "/api/onboarding/users", json={
        "name": "HydAPI Test", "username": "hydapi", "password": "local-test-only",
        "client_id": BASE + "/", "language": "nb",
    }, timeout=60)
    result.raise_for_status()
    result = requests.post(BASE + "/auth/token", data={"grant_type": "authorization_code",
        "code": result.json()["auth_code"], "client_id": BASE + "/"}, timeout=30)
    result.raise_for_status()
    tokens = result.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    for step, data in (("core_config", {}), ("analytics", {}), ("integration", {"client_id": BASE + "/", "redirect_uri": BASE + "/"})):
        response = requests.post(BASE + "/api/onboarding/" + step, headers=headers, json=data, timeout=120)
        response.raise_for_status()
    return tokens, headers


def add_integration(headers):
    endpoint = BASE + "/api/config/config_entries/flow"
    response = requests.post(endpoint, headers=headers, json={"handler": "nve_hydapi", "show_advanced_options": False}, timeout=60)
    response.raise_for_status()
    flow = response.json()
    for values in ({"api_key": "ui-test-key", "scan_interval": 15}, {"station_id": "139.15.0"}, {"series": ["139.15.0|1001|0|1"], "add_another": False}):
        response = requests.post(endpoint + "/" + flow["flow_id"], headers=headers, json=values, timeout=60)
        response.raise_for_status()
        flow = response.json()
        assert not flow.get("errors"), flow
    assert flow["type"] == "create_entry", flow
    for _ in range(60):
        states = requests.get(BASE + "/api/states", headers=headers, timeout=10).json()
        if any(s["attributes"].get("station_id") == "139.15.0" for s in states):
            return flow["result"]["entry_id"]
        time.sleep(1)
    raise AssertionError("Integration never loaded")


def check_dialogs(browser, name):
    context = browser.new_context(locale="nb-NO", viewport={"width": 1280, "height": 960})
    context.add_init_script("localStorage.setItem('selectedLanguage', 'nb');")
    page = context.new_page()
    try:
        page.goto(BASE + "/config/integrations/integration/nve_hydapi")
        page.locator('input[name="username"]').fill("hydapi", timeout=60000)
        page.locator('input[name="password"]').fill("local-test-only")
        page.get_by_role("button", name="Logg Inn", exact=True).click()
        page.wait_for_selector("home-assistant", timeout=60000)
        gear = page.get_by_role("button", name=re.compile("alternativer|konfigurer|options|configure", re.I))
        gear.first.click(timeout=60000)
        expect(page.get_by_text("N\u00e5v\u00e6rende oppsett:", exact=False)).to_be_visible(timeout=30000)
        expect(page.get_by_text("Anbefalt intervall er 15 minutter", exact=False)).to_be_visible()
        expect(page.get_by_text("Behold valgte m\u00e5leserier", exact=False).first).to_be_visible()
        page.screenshot(path=str(ARTIFACTS / f"{name}-options-desktop.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(ARTIFACTS / f"{name}-options-mobile.png"))
        page.set_viewport_size({"width": 1280, "height": 960})
        page.get_by_text("Behold valgte m\u00e5leserier", exact=False).first.click()
        page.get_by_text("Legg til m\u00e5leserier", exact=True).click()
        page.get_by_role("button", name="Send inn", exact=True).click()
        station_input = page.get_by_role("combobox").first
        station_input.fill("Bj\u00f8rn")
        # HA's editable selector keeps the selected full label, not the raw ID.
        page.get_by_text("Bj\u00f8rnstad [139.15.0] - Namsskogan", exact=True).last.click()
        expect(station_input).to_have_value("Bj\u00f8rnstad [139.15.0] - Namsskogan")
        page.screenshot(path=str(ARTIFACTS / f"{name}-station.png"))
        page.get_by_role("button", name="Send inn", exact=True).click()
        page.get_by_role("combobox").first.click()
        expect(page.get_by_text(re.compile("D\u00f8gn"))).to_be_visible()
        page.screenshot(path=str(ARTIFACTS / f"{name}-series.png"))
        return page.evaluate("document.querySelector('home-assistant').hass.callApi('GET', 'config/config_entries/entry')")
    except Exception:
        page.screenshot(path=str(ARTIFACTS / f"{name}-failure.png"))
        elements = page.locator("button,ha-button,ha-icon-button,input,ha-select").evaluate_all("els => els.map(e => ({tag:e.tagName,text:e.textContent,label:e.getAttribute('aria-label'),title:e.getAttribute('title'),name:e.getAttribute('name'),type:e.getAttribute('type'),autocomplete:e.getAttribute('autocomplete')}))")
        (ARTIFACTS / f"{name}-elements.json").write_text(json.dumps(elements, indent=2), encoding="utf-8")
        raise
    finally:
        context.close()


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    try:
        for name in ("fresh", "upgrade"):
            with tempfile.TemporaryDirectory() as directory:
                source = ROOT if name == "fresh" else ROOT / ".ui-legacy"
                server = start_server(Path(directory), source, name + "-initial")
                try:
                    tokens, headers = onboard()
                    entry_id = add_integration(headers)
                finally:
                    stop_server(server)
                # A full restart also verifies persisted entries, not just in-memory forms.
                server = start_server(Path(directory), ROOT, name + "-candidate")
                try:
                    entries = check_dialogs(browser, name)
                    assert any(e["entry_id"] == entry_id for e in entries)
                finally:
                    stop_server(server)
    finally:
        browser.close()
