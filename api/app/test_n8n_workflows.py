"""WF-05: static guard that every API-calling n8n node carries the tenant key (make check-n8n)."""
import copy
import json
import re
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "n8n" / "workflows").is_dir())
WF_DIR = ROOT / "n8n" / "workflows"
EXPECTED = {"inbound-message", "followup-scheduler", "escalation-alert", "outreach-flow", "error-handler",
            "quote-request", "review-reply", "capacity-check", "daily-brief", "intake-event"}
UNTENANTED = {"outreach-flow", "error-handler"}
HTTP, CODE, SCHED = "n8n-nodes-base.httpRequest", "n8n-nodes-base.code", "n8n-nodes-base.scheduleTrigger"
API_MARKERS = ("$env.API_URL", "api:8000", "localhost:8000")
CODE_BYPASS = ("helpers.httpRequest", "fetch(", "$http", "api:8000")


def _headers(node: dict) -> dict[str, str]:
    p = node["parameters"]
    if not p.get("sendHeaders"):
        return {}
    return {h["name"].lower(): str(h.get("value", "")) for h in p.get("headerParameters", {}).get("parameters", [])}


def check_workflow(name: str, data: dict, raw: str) -> list[str]:
    v: list[str] = []
    if "rd_live_" in raw:
        v.append("rd_live_ string committed")
    if data.get("id") != name:
        v.append(f"id {data.get('id')!r} != basename")
    tenanted = name not in UNTENANTED
    if name != "error-handler" and data.get("settings", {}).get("errorWorkflow") != "error-handler":
        v.append("errorWorkflow is not error-handler")
    nodes = data["nodes"]
    if tenanted and any(n["type"] == SCHED for n in nodes) and data.get("settings", {}).get("saveDataSuccessExecution") != "none":
        v.append("scheduled workflow must set saveDataSuccessExecution none")  # tenant-aware only: outreach-flow is out of scope
    for n in nodes:
        p, nm = n["parameters"], n["name"]
        if n["type"] == CODE:
            src = p.get("jsCode", "")
            v += [f"{nm}: code node calls HTTP ({b})" for b in CODE_BYPASS if b in src]
            if "TENANT_API_KEYS" in src and re.search(r"\bkey\s*:|\bapi_?key\b", src, re.I):
                v.append(f"{nm}: code node puts a tenant key into item JSON")
        if n["type"] != HTTP:
            continue
        url = str(p.get("url", "")).lstrip("=").strip()
        h = _headers(n)
        if "x-tenant-id" in h:
            v.append(f"{nm}: sends X-Tenant-Id")
        if p.get("authentication", "none") != "none" or p.get("genericAuthType"):
            v.append(f"{nm}: uses n8n credentials auth")
        if not any(m in url for m in API_MARKERS):
            if "x-api-key" in h:
                v.append(f"{nm}: non-API url carries X-API-Key")
            continue
        admin = h.get("x-admin-key")
        if admin is not None and "$env.ADMIN_API_KEY" not in admin:
            v.append(f"{nm}: literal X-Admin-Key")
        if not h:
            v.append(f"{nm}: API node without headers")
        elif tenanted:
            key = h.get("x-api-key")
            tenant_list = p.get("method", "GET") == "GET" and url.split("?")[0].endswith("/admin/tenants")
            if tenant_list:
                if admin is None:
                    v.append(f"{nm}: tenant list needs X-Admin-Key")
            else:
                if admin is not None:
                    v.append(f"{nm}: X-Admin-Key outside the /admin/tenants exception")
                if not (key and key.startswith("=") and "JSON.parse($env.TENANT_API_KEYS)" in key):
                    v.append(f"{nm}: missing or non-env X-API-Key")
        elif admin is None:
            v.append(f"{nm}: untenanted API node without X-Admin-Key")
    if tenanted and "ADMIN_API_KEY" in raw:
        for n in nodes:
            if "ADMIN_API_KEY" in json.dumps(n) and not (n["type"] == HTTP and str(n["parameters"].get("url", "")).split("?")[0].endswith("/admin/tenants")):
                v.append(f"{n['name']}: references ADMIN_API_KEY outside /admin/tenants")
    if name == "error-handler" and any(n["type"] == HTTP and any(m in str(n["parameters"].get("url", "")) for m in API_MARKERS) for n in nodes):
        v.append("error-handler must not call the API")
    return v


def _load(name: str) -> tuple[dict, str]:
    raw = (WF_DIR / f"{name}.json").read_text()
    return json.loads(raw), raw


FILES = sorted(p.stem for p in WF_DIR.glob("*.json"))


@pytest.mark.parametrize("name", FILES)
def test_real_workflow_is_clean(name):
    data, raw = _load(name)
    assert check_workflow(name, data, raw) == []


def test_catalog():
    assert set(FILES) == EXPECTED
    assert not (WF_DIR / "daily-report.json").exists()
    assert UNTENANTED <= set(FILES)


def test_compose_and_env_example():
    compose, env = Path("/srv/docker-compose.yml"), Path("/srv/.env.example")
    assert compose.is_file() and env.is_file(), "compose and .env.example must be mounted into the api container"
    assert re.search(r'N8N_BLOCK_ENV_ACCESS_IN_NODE:\s*"false"', compose.read_text())
    assert "rd_live_" not in env.read_text()


# ---- mutants: the checker must bite ----
def _mutant(mutate, wf="followup-scheduler"):
    data, _ = _load(wf)
    data = copy.deepcopy(data)
    mutate(data)
    return check_workflow(wf, data, json.dumps(data))


def _tenant_node(d, name="Tenant me"):
    return next(n for n in d["nodes"] if n["name"] == name)


def _hdr(d, name="Tenant me"):
    return _tenant_node(d, name)["parameters"]["headerParameters"]["parameters"][0]


def _add_code(d, src):
    d["nodes"].append({"name": "Evil", "type": CODE, "parameters": {"jsCode": src}})


MUTANTS = {
    "header removed": lambda d: _tenant_node(d)["parameters"].update(sendHeaders=False),
    "no headers at all": lambda d: _tenant_node(d)["parameters"].pop("headerParameters"),
    "header renamed": lambda d: _hdr(d).update(name="X-Key"),
    "literal key": lambda d: _hdr(d).update(value="=abc123"),
    "literal key no =": lambda d: _hdr(d).update(value="plain"),
    "admin key on tenant node": lambda d: _hdr(d).update(name="X-Admin-Key", value="={{ $env.ADMIN_API_KEY }}"),
    "tenant id header": lambda d: _tenant_node(d)["parameters"]["headerParameters"]["parameters"].append({"name": "X-Tenant-Id", "value": "x"}),
    "code http helper": lambda d: _add_code(d, "return this.helpers.httpRequest({url:'x'})"),
    "code fetch": lambda d: _add_code(d, "await fetch('http://api:8000/x')"),
    "code $http": lambda d: _add_code(d, "$http.get('x')"),
    "code key into item": lambda d: _add_code(d, "const k=JSON.parse($env.TENANT_API_KEYS); return [{json:{key:k[1]}}]"),
    "schedule without save none": lambda d: d["settings"].pop("saveDataSuccessExecution"),
    "rd_live_ literal": lambda d: d.update(note="rd_live_" + "x" * 8),
    "id mismatch": lambda d: d.update(id="other"),
    "no errorWorkflow": lambda d: d["settings"].pop("errorWorkflow"),
}


@pytest.mark.parametrize("label", MUTANTS)
def test_mutant_is_caught(label):
    assert _mutant(MUTANTS[label]), f"checker missed mutant: {label}"


def test_mutant_untenanted_admin_key_removed():
    assert _mutant(lambda d: _hdr(d, "Start Google Maps scrape").update(name="X-Nope"), wf="outreach-flow")


def test_mutant_error_handler_calls_api():
    def m(d):
        d["nodes"].append({"name": "x", "type": HTTP, "parameters": {"url": "={{ $env.API_URL }}/x", "sendHeaders": True,
                           "headerParameters": {"parameters": [{"name": "X-Admin-Key", "value": "={{ $env.ADMIN_API_KEY }}"}]}}})
    assert _mutant(m, wf="error-handler")


def test_mutant_admin_key_on_tenants_list_is_allowed_only_there():
    data, raw = _load("followup-scheduler")
    assert check_workflow("followup-scheduler", data, raw) == []  # the pinned exception itself is clean


def test_mutant_non_api_url_with_api_key():
    assert _mutant(lambda d: d["nodes"].append({"name": "m", "type": HTTP, "parameters": {
        "url": "http://mailpit:8025/x", "sendHeaders": True, "headerParameters": {"parameters": [{"name": "X-API-Key", "value": "=a"}]}}}))
