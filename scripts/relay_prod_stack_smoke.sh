#!/usr/bin/env bash
# §D.1 relay E2E against the RUNNING prod compose stack (deploy/*.yml).
#
# Proves the core invariant on the real wired stack (DMZ -> new-api gate -> MCP
# spine -> upstream):
#   ALLOW (coder + openai -> gpt-4o)            -> HTTP 200 + [mock-upstream] + upstream hit
#   DENY  (reviewer + openai, heterogeneity)    -> generic 503 + ZERO upstream connections
#
# Synthetic only: mock upstream, fake key, no real provider/PHI. Reuses the
# running containers (no separate stack). `--keep` leaves the mock up.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DMZ="${DMZ_BASE:-https://localhost:18443}"
NET="${MEDHARNESS_NET:-medharness_internal}"
MOCK="${MOCK_CONTAINER:-mh-e2e-mock}"
ROUTER="${ROUTER_CONTAINER:-medharness-model-router}"
A0="${A0_CONTAINER:-medharness-a0-api}"
CHANGE_ID="${CHANGE_ID:-e2e-relay}"
ALLOW_ROLE=coder
DENY_ROLE=reviewer
CALLER_VENDOR=openai
ROOT_USER="${ROOT_USER:-admin}"
ROOT_PASS="${ROOT_PASS:-medharness123}"
KEEP=0; [ "${1:-}" = "--keep" ] && KEEP=1

fail() { echo "FAIL: $*" >&2; exit 1; }
cleanup() { [ "$KEEP" = 1 ] || docker rm -f "$MOCK" >/dev/null 2>&1; }
trap cleanup EXIT

mock_count() {
  docker exec "$A0" python -c "import json,urllib.request;print(json.load(urllib.request.urlopen('http://${MOCK}:18080/__count',timeout=3))['count'])"
}

echo "== 1. model-router allowlist (/project/openspec/changes/${CHANGE_ID}) =="
# Allow-list BOTH roles so the DENY is decided by the HETEROGENEITY layer (a
# distinct §D.1 control) rather than the allowlist: coder may call same-family
# (coder same_family_allowed=True), reviewer may NOT (reviewer requires a
# cross-vendor model), so reviewer+openai -> gpt-4o(openai) is a heterogeneity deny.
python3 - "$CHANGE_ID" "$ALLOW_ROLE" "$DENY_ROLE" > /tmp/e2e_allowlist.json <<'PY'
import json, sys
cid, allow_role, deny_role = sys.argv[1], sys.argv[2], sys.argv[3]
print(json.dumps({
    "schema_version": "T3.allowlist.v1",
    "policy_version": cid,
    "models": [{
        "id": "gpt-4o", "vendor_family": "openai", "deployment": "private://gpt-4o",
        "allowed_agent_roles": [allow_role, deny_role],
        "allowed_data_levels": ["L1", "L2", "L3", "L4"],
        "rate_limit_qps": 20,
    }],
}, ensure_ascii=False, indent=2))
PY
docker exec -u 0 "$ROUTER" mkdir -p "/project/openspec/changes/${CHANGE_ID}" || fail "mkdir /project"
docker cp /tmp/e2e_allowlist.json "${ROUTER}:/project/openspec/changes/${CHANGE_ID}/MODEL_ALLOWLIST.json" || fail "cp allowlist"
echo "   allowlist injected"

echo "== 2. mock upstream on ${NET} =="
docker rm -f "$MOCK" >/dev/null 2>&1
docker run -d --name "$MOCK" --network "$NET" \
  -v "${REPO_ROOT}/tools/mock_upstream:/app:ro" \
  python:3.11-slim python /app/server.py --port 18080 >/dev/null || fail "mock run"
for i in $(seq 1 30); do
  docker exec "$A0" python -c "import urllib.request;urllib.request.urlopen('http://${MOCK}:18080/health',timeout=2)" >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$A0" python -c "import urllib.request;urllib.request.urlopen('http://${MOCK}:18080/health',timeout=2)" >/dev/null 2>&1 || fail "mock not healthy"
echo "   mock up"

echo "== 3. new-api channel + token (via ${A0} -> new-api:3000) =="
TOKEN_KEY="$(docker exec -i "$A0" python - "$ROOT_USER" "$ROOT_PASS" "$MOCK" <<'PY'
import http.cookiejar, json, sys, urllib.request
user, pw, mock = sys.argv[1], sys.argv[2], sys.argv[3]
BASE = "http://new-api:3000"
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

def call(path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method or ("POST" if body is not None else "GET"))
    req.add_header("Content-Type", "application/json")
    req.add_header("New-Api-User", "1")
    with op.open(req, timeout=10) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw.strip() else {}

call("/api/user/login", {"username": user, "password": pw})
# Delete stale channels first so gpt-4o routes only to the live mock here
# (other test runs leave dead channels that new-api would load-balance onto).
ch = call("/api/channel/?p=1&size=100"); data = ch.get("data")
for c in (data.get("items") if isinstance(data, dict) else data) or []:
    call("/api/channel/%s" % c["id"], method="DELETE")
call("/api/channel/", {"mode": "single", "channel": {
    "type": 1, "base_url": f"http://{mock}:18080", "key": "sk-mock",
    "models": "gpt-4o", "group": "default", "status": 1, "name": "E2EMock"}})
call("/api/channel/fix", {})
call("/api/token/", {"name": "e2e", "remain_quota": 9999999, "expired_time": -1, "group": "default"})
toks = call("/api/token/?p=1&size=20")
data = toks.get("data")
items = data.get("items") if isinstance(data, dict) else data
tid = next((t["id"] for t in (items or []) if t.get("name") == "e2e"), None)
assert tid is not None, f"token id not found: {toks}"
key = call(f"/api/token/{tid}/key", {})
print(key["data"]["key"])
PY
)" || fail "new-api setup failed"
[ -n "$TOKEN_KEY" ] || fail "empty token key"
case "$TOKEN_KEY" in sk-*) AUTH="Bearer $TOKEN_KEY";; *) AUTH="Bearer sk-$TOKEN_KEY";; esac
echo "   token captured"

relay() {  # role -> writes body to $2, echoes http code
  curl -sk -o "$2" -w '%{http_code}' \
    -H "Authorization: $AUTH" -H 'Content-Type: application/json' \
    -H "X-MedHarness-Agent-Role: $1" \
    -H "X-MedHarness-Change-Id: $CHANGE_ID" \
    -H "X-MedHarness-Caller-Vendor-Family: $CALLER_VENDOR" \
    -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hello e2e"}]}' \
    "$DMZ/v1/chat/completions"
}

echo "== 4. ALLOW path (${ALLOW_ROLE}) =="
C0="$(mock_count)"
A_CODE="$(relay "$ALLOW_ROLE" /tmp/e2e_allow.json)"
[ "$A_CODE" = 200 ] || fail "ALLOW HTTP $A_CODE (want 200): $(head -c 300 /tmp/e2e_allow.json)"
grep -Fq '[mock-upstream]' /tmp/e2e_allow.json || fail "ALLOW missing [mock-upstream]: $(head -c 300 /tmp/e2e_allow.json)"
C1="$(mock_count)"
[ "$C1" -gt "$C0" ] || fail "ALLOW did not reach upstream (counter $C0 -> $C1)"
echo "   ALLOW -> 200 + [mock-upstream] + upstream hit ($C0 -> $C1)"

echo "== 5. DENY path (${DENY_ROLE}, heterogeneity) =="
D_CODE="$(relay "$DENY_ROLE" /tmp/e2e_deny.json)"
[ "$D_CODE" = 503 ] || fail "DENY HTTP $D_CODE (want 503): $(head -c 300 /tmp/e2e_deny.json)"
grep -Fq '[mock-upstream]' /tmp/e2e_deny.json && fail "DENY leaked upstream reply"
C2="$(mock_count)"
[ "$C2" = "$C1" ] || fail "DENY reached upstream (counter $C1 -> $C2, expected 0 connections)"
echo "   DENY -> 503 generic + no marker + ZERO upstream connections ($C1 == $C2)"

echo "RELAY-PROD-STACK E2E PASS"
[ "$KEEP" = 1 ] && echo "(kept mock $MOCK up)"
