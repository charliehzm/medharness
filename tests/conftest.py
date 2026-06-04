"""Shared LIVE relay harness for the §D.1 gate-matrix (Layer 2) and the business
persona simulation (Layer 4).

Everything here is SKIP-GATED on MEDHARNESS_LIVE_BASE + a running docker stack, so
the offline suite (the 380+ unit tests) never instantiates it. The fixtures shell
out to the same docker primitives the bash smoke uses (scripts/relay_prod_stack_smoke.sh):
run the mock upstream on the internal net, mint a new-api channel+token via
`docker exec`, inject a per-change MODEL_ALLOWLIST.json into the model-router
/project volume, and drive /v1/chat/completions through the nginx DMZ.

Container names / net are env-overridable (default to the prod-compose names).
"""

from __future__ import annotations

import http.client
import json
import os
import re
import ssl
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_BASE = os.environ.get("MEDHARNESS_LIVE_BASE", "").rstrip("/")

A0 = os.environ.get("MEDHARNESS_A0_CONTAINER", "medharness-a0-api")
ROUTER = os.environ.get("MEDHARNESS_ROUTER_CONTAINER", "medharness-model-router")
NET = os.environ.get("MEDHARNESS_NET", "medharness_internal")
MOCK = os.environ.get("MEDHARNESS_MATRIX_MOCK", "mh-e2e-matrix-mock")
ECHO_MOCK = os.environ.get("MEDHARNESS_ECHO_MOCK", "mh-e2e-echo-mock")
SPLIT_MOCK = os.environ.get("MEDHARNESS_SPLIT_MOCK", "mh-e2e-split-mock")
ROOT_USER = os.environ.get("MEDHARNESS_LIVE_USER", "admin")
ROOT_PASS = os.environ.get("MEDHARNESS_LIVE_PASS", "medharness123")
CHANNEL_MODELS = "gpt-4o,qwen-max-2026,claude-sonnet-4.6"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_PHI_PATTERNS = [
    re.compile(r"[1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]"),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
]


class LiveResp:
    def __init__(self, status: int, text: str) -> None:
        self.status = status
        self.text = text

    def json(self) -> Any:
        return json.loads(self.text)


def dmz_request(method: str, path: str, body: Any = None, headers: dict[str, str] | None = None) -> LiveResp:
    hdrs = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(f"{LIVE_BASE}{path}", data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=30, context=_CTX) as resp:
            return LiveResp(resp.status, _read_tolerant(resp))
    except urllib.error.HTTPError as exc:
        return LiveResp(exc.code, _read_tolerant(exc))


def _read_tolerant(resp: Any) -> str:
    # A malformed Content-Length (e.g. a stale length on a deny-after-buffered-relay)
    # raises IncompleteRead; keep the partial body so the real status/payload is visible.
    try:
        return resp.read().decode("utf-8", "replace")
    except http.client.IncompleteRead as exc:
        return exc.partial.decode("utf-8", "replace")


def assert_no_phi(text: str, where: str) -> None:
    for pat in _PHI_PATTERNS:
        m = pat.search(text)
        assert m is None, f"PHI-like marker in {where}: {m.group()[:6]}…"  # type: ignore[union-attr]


def _docker(*args: str, stdin: str | None = None, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], input=stdin, capture_output=True, text=True, timeout=timeout
    )


def model_entry(
    model_id: str = "gpt-4o",
    vendor_family: str = "openai",
    roles: tuple[str, ...] = ("coder",),
    levels: tuple[str, ...] = ("L1", "L2", "L3", "L4"),
) -> dict[str, Any]:
    return {
        "id": model_id,
        "vendor_family": vendor_family,
        "deployment": f"private://{model_id}",
        "allowed_agent_roles": list(roles),
        "allowed_data_levels": list(levels),
        "rate_limit_qps": 20,
    }


# new-api admin bootstrap (cookiejar login → clean channels → channel → token → key), run inside A0.
_NEWAPI_SETUP = """
import http.cookiejar, json, sys, urllib.request
user, pw, mock, echo_mock, split_mock, models = sys.argv[1:7]
BASE = "http://new-api:3000"
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def call(path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method or ("POST" if body is not None else "GET"))
    req.add_header("Content-Type", "application/json"); req.add_header("New-Api-User", "1")
    with op.open(req, timeout=10) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw.strip() else {}
call("/api/user/login", {"username": user, "password": pw})
# Delete ALL existing channels first: repeated test runs otherwise accumulate
# dead channels (pointing at torn-down mocks), and new-api load-balances gpt-4o
# onto them, randomly failing ALLOW cases. Leave exactly one live channel.
ch = call("/api/channel/?p=1&size=100"); data = ch.get("data")
for c in (data.get("items") if isinstance(data, dict) else data) or []:
    call(f"/api/channel/{c['id']}", method="DELETE")
call("/api/channel/", {"mode": "single", "channel": {
    "type": 1, "base_url": f"http://{mock}:18080", "key": "sk-mock",
    "models": models, "group": "default", "status": 1, "name": "E2EMatrixMock"}})
# Second channel -> the echo-mock, serving only "echo-model", for the D9
# outbound-safety (post-call) block case.
call("/api/channel/", {"mode": "single", "channel": {
    "type": 1, "base_url": f"http://{echo_mock}:18080", "key": "sk-mock",
    "models": "echo-model", "group": "default", "status": 1, "name": "E2EEchoMock"}})
# Third channel -> the split-mock, serving only "split-model", for the streaming
# chunk-split outbound-evasion case (ST3).
call("/api/channel/", {"mode": "single", "channel": {
    "type": 1, "base_url": f"http://{split_mock}:18080", "key": "sk-mock",
    "models": "split-model", "group": "default", "status": 1, "name": "E2ESplitMock"}})
call("/api/channel/fix", {})
call("/api/token/", {"name": "e2e-matrix", "remain_quota": 9999999, "expired_time": -1, "group": "default"})
toks = call("/api/token/?p=1&size=20"); data = toks.get("data")
items = data.get("items") if isinstance(data, dict) else data
tid = next((t["id"] for t in (items or []) if t.get("name") == "e2e-matrix"), None)
assert tid is not None, f"token id not found: {toks}"
print(call(f"/api/token/{tid}/key", {})["data"]["key"])
"""


@pytest.fixture(scope="session")
def _relay_stack() -> bool:
    if not LIVE_BASE:
        pytest.skip("set MEDHARNESS_LIVE_BASE to run the live relay/persona suites")
    ps = _docker("ps", "--format", "{{.Names}}")
    if ps.returncode != 0:
        pytest.skip("docker unavailable")
    names = set(ps.stdout.split())
    for container in (A0, ROUTER):
        if container not in names:
            pytest.skip(f"required container not running: {container}")
    return True


class _Mock:
    def __init__(self, name: str) -> None:
        self.name = name
        self.host = name

    def count(self) -> int:
        out = _docker(
            "exec", A0, "python", "-c",
            f"import json,urllib.request;print(json.load(urllib.request.urlopen('http://{self.name}:18080/__count',timeout=3))['count'])",
        )
        return int(out.stdout.strip() or "0")

    def reset(self) -> None:
        _docker(
            "exec", A0, "python", "-c",
            f"import urllib.request;urllib.request.urlopen("
            f"urllib.request.Request('http://{self.name}:18080/__reset',method='POST'),timeout=3)",
        )

    def last_prompt(self) -> str:
        out = _docker(
            "exec", A0, "python", "-c",
            f"import json,urllib.request;print(json.load(urllib.request.urlopen('http://{self.name}:18080/__last',timeout=3))['prompt'])",
        )
        return out.stdout


def _start_mock(name: str, extra_env: tuple[str, ...] = ()) -> _Mock:
    import time as _t

    _docker("rm", "-f", name)
    env_args: list[str] = []
    for env in extra_env:
        env_args += ["-e", env]
    run = _docker(
        "run", "-d", "--name", name, "--network", NET, *env_args,
        "-v", f"{REPO_ROOT}/tools/mock_upstream:/app:ro",
        "python:3.11-slim", "python", "/app/server.py", "--port", "18080",
    )
    if run.returncode != 0:
        pytest.skip(f"mock run failed ({name}): {run.stderr.strip()}")
    for _ in range(30):
        h = _docker(
            "exec", A0, "python", "-c",
            f"import urllib.request;urllib.request.urlopen('http://{name}:18080/health',timeout=2)",
        )
        if h.returncode == 0:
            return _Mock(name)
        _t.sleep(1)
    _docker("rm", "-f", name)
    pytest.skip(f"mock {name} did not become healthy")


@pytest.fixture(scope="session")
def mock_upstream(_relay_stack: bool):
    mock = _start_mock(MOCK)
    yield mock
    _docker("rm", "-f", MOCK)


@pytest.fixture(scope="session")
def echo_mock(_relay_stack: bool):
    # always echoes a harmful trigger (env-driven, since new-api doesn't forward
    # client X-Mock-* headers to the upstream) so outbound-safety blocks (D9).
    mock = _start_mock(ECHO_MOCK, extra_env=("MOCK_ECHO_UNSAFE=1",))
    yield mock
    _docker("rm", "-f", ECHO_MOCK)


@pytest.fixture(scope="session")
def split_mock(_relay_stack: bool):
    # streams the synthetic harmful trigger SPLIT across SSE chunk boundaries
    # (env-driven, since new-api doesn't forward client X-Mock-* headers) so a naive
    # per-frame outbound scan evades it — the ST3 streaming-evasion case.
    mock = _start_mock(SPLIT_MOCK, extra_env=("MOCK_STREAM_SPLIT=1",))
    yield mock
    _docker("rm", "-f", SPLIT_MOCK)


@pytest.fixture(scope="session")
def relay_token(_relay_stack: bool, mock_upstream, echo_mock, split_mock) -> str:
    out = _docker(
        "exec", "-i", A0, "python", "-",
        ROOT_USER, ROOT_PASS, MOCK, ECHO_MOCK, SPLIT_MOCK, CHANNEL_MODELS, stdin=_NEWAPI_SETUP,
    )
    if out.returncode != 0 or not out.stdout.strip():
        pytest.skip(f"new-api channel/token setup failed: {out.stderr.strip()[:300]}")
    key = out.stdout.strip().splitlines()[-1].strip()
    return f"Bearer {key}" if key.startswith("sk-") else f"Bearer sk-{key}"


@pytest.fixture(scope="session")
def inject_allowlist(_relay_stack: bool):
    import tempfile

    def _inject(change_id: str, models: list[dict[str, Any]]) -> None:
        doc = {"schema_version": "T3.allowlist.v1", "policy_version": change_id, "models": models}
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        # mkstemp is 0600; docker cp preserves that as root-owned, so the non-root
        # model-router (uid 9000) can't READ the allowlist -> "permission denied" ->
        # it denies every model. Make it world-readable before the copy.
        os.chmod(path, 0o644)
        try:
            _docker("exec", "-u", "0", ROUTER, "mkdir", "-p", f"/project/openspec/changes/{change_id}")
            cp = _docker("cp", path, f"{ROUTER}:/project/openspec/changes/{change_id}/MODEL_ALLOWLIST.json")
            assert cp.returncode == 0, f"docker cp allowlist failed: {cp.stderr.strip()}"
        finally:
            os.unlink(path)

    return _inject


@pytest.fixture
def ch_query(_relay_stack: bool):
    """Run a ClickHouse query against the live (internal-only) CH via the a0 container,
    returning parsed JSONEachRow rows."""

    def _query(sql: str) -> list[dict[str, Any]]:
        script = (
            "import json,os,urllib.parse,urllib.request\n"
            f"sql={sql!r}\n"
            "if ' FORMAT ' not in (' '+sql.upper()+' '): sql+=' FORMAT JSONEachRow'\n"
            "db=os.environ.get('CLICKHOUSE_DATABASE','medharness')\n"
            "url='http://clickhouse:8123/?'+urllib.parse.urlencode({'database':db})\n"
            "req=urllib.request.Request(url,data=sql.encode(),method='POST',headers={"
            "'X-ClickHouse-User':os.environ.get('CLICKHOUSE_USER','medharness'),"
            "'X-ClickHouse-Key':os.environ.get('CLICKHOUSE_PASSWORD','')})\n"
            "out=urllib.request.urlopen(req,timeout=10).read().decode()\n"
            "print(json.dumps([json.loads(x) for x in out.splitlines() if x.strip()]))\n"
        )
        out = _docker("exec", A0, "python", "-c", script)
        if out.returncode != 0:
            pytest.skip(f"clickhouse query failed: {out.stderr.strip()[:200]}")
        return json.loads(out.stdout or "[]")

    return _query


@pytest.fixture
def mcp_post(_relay_stack: bool):
    """POST JSON to an internal MCP service (port 9000) via the a0 container."""

    def _post(host: str, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        script = (
            "import json,urllib.request,urllib.error\n"
            f"body={json.dumps(body)!r}\n"
            f"req=urllib.request.Request('http://{host}:9000{path}',data=body.encode(),"
            "method='POST',headers={'Content-Type':'application/json'})\n"
            "try:\n"
            "  r=urllib.request.urlopen(req,timeout=10); print(json.dumps([r.status,json.loads(r.read().decode())]))\n"
            "except urllib.error.HTTPError as e:\n"
            "  print(json.dumps([e.code,json.loads(e.read().decode() or '{}')]))\n"
        )
        out = _docker("exec", A0, "python", "-c", script)
        if out.returncode != 0:
            pytest.skip(f"mcp post failed: {out.stderr.strip()[:200]}")
        status, payload = json.loads(out.stdout)
        return status, payload

    return _post


@pytest.fixture
def scenario_seed(_relay_stack: bool):
    """Seed the deterministic 15-scenario _audit_log (scripts/seed_scenarios.py) inside
    the a0 container and return the JSON manifest, so a test reads EXPECTED counts/refs
    instead of hard-coding them. Each call resets the table first."""

    def _seed() -> dict[str, Any]:
        src = REPO_ROOT / "scripts" / "seed_scenarios.py"
        cp = _docker("cp", str(src), f"{A0}:/tmp/seed_scenarios.py")
        if cp.returncode != 0:
            pytest.skip(f"cannot copy seeder into {A0}: {cp.stderr.strip()[:200]}")
        out = _docker("exec", A0, "python", "/tmp/seed_scenarios.py", "--reset", "--emit-manifest")
        if out.returncode != 0 or not out.stdout.strip():
            pytest.skip(f"scenario seeder failed: {out.stderr.strip()[:200]}")
        return json.loads(out.stdout.strip().splitlines()[-1])

    return _seed


@pytest.fixture
def dmz(_relay_stack: bool):
    """The DMZ request helper as a fixture, so tests under tests/sim/ (which don't see
    the e2e_live `http` fixture) can read A0 Console endpoints through nginx."""
    return dmz_request


@pytest.fixture
def no_phi():
    """The 0-PHI deep-scan assertion, injected (avoids cross-dir conftest import collisions)."""
    return assert_no_phi


@pytest.fixture
def make_model():
    """Factory for a MODEL_ALLOWLIST.json model entry."""
    return model_entry


@pytest.fixture
def relay(relay_token: str):
    def _relay(
        role: str,
        vendor_family: str,
        change_id: str,
        content: str = "hello from the e2e matrix",
        model: str = "gpt-4o",
        stream: bool = False,
        extra_headers: dict[str, str] | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> LiveResp:
        # `messages` overrides the default single-user-message body, so a caller can
        # scatter PHI across several messages (MM1) or use a structured content array
        # (MM2) to exercise extractPromptText/rewriteDesensitizedBody recursion.
        body: dict[str, Any] = {
            "model": model,
            "messages": messages if messages is not None else [{"role": "user", "content": content}],
        }
        if stream:
            body["stream"] = True
        headers = {
            "Authorization": relay_token,
            "X-MedHarness-Agent-Role": role,
            "X-MedHarness-Change-Id": change_id,
            "X-MedHarness-Caller-Vendor-Family": vendor_family,
        }
        if extra_headers:
            headers.update(extra_headers)
        return dmz_request("POST", "/v1/chat/completions", body=body, headers=headers)

    return _relay


@pytest.fixture
def relay_embeddings(relay_token: str):
    """POST /v1/embeddings through the DMZ. The body carries the text in `input`
    (string OR array), NOT `messages` — the path that exposed the embeddings PHI
    bypass. The channel serving `model` also serves /v1/embeddings (the mock does)."""

    def _relay(
        role: str,
        vendor_family: str,
        change_id: str,
        input_value: Any,
        model: str = "gpt-4o",
        extra_headers: dict[str, str] | None = None,
    ) -> LiveResp:
        body: dict[str, Any] = {"model": model, "input": input_value}
        headers = {
            "Authorization": relay_token,
            "X-MedHarness-Agent-Role": role,
            "X-MedHarness-Change-Id": change_id,
            "X-MedHarness-Caller-Vendor-Family": vendor_family,
        }
        if extra_headers:
            headers.update(extra_headers)
        return dmz_request("POST", "/v1/embeddings", body=body, headers=headers)

    return _relay
