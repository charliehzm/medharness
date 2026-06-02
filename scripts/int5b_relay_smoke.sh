#!/usr/bin/env bash
# INT-5b relay-path smoke: real gate MCPs + new-api relay + mock upstream.
#
# Synthetic only. No real provider keys, no real PHI.
#
#   scripts/int5b_relay_smoke.sh [--keep]
#
# --keep leaves the Docker stack and temp allowlist root up for manual debugging.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_FILE="${REPO_ROOT}/deploy/dev/int5b.env"
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a
  . "$ENV_FILE"
  set +a
fi

VERSION="${VERSION:-0.5.0-edge}"
TIER_SECRET="${MODEL_ROUTER_TIER_SECRET:-dev-int5b-secret}"
CHANGE_ID="${INT5B_CHANGE_ID:-int5b-relay}"
ALLOW_AGENT_ROLE="${INT5B_ALLOW_AGENT_ROLE:-coder}"
DENY_AGENT_ROLE="${INT5B_DENY_AGENT_ROLE:-reviewer}"

NET="${INT5B_NET:-medharness-int5b}"
CH="${INT5B_CH_CONTAINER:-mh-int5b-ch}"
REDIS="${INT5B_REDIS_CONTAINER:-mh-int5b-redis}"
PHI="${INT5B_PHI_CONTAINER:-mh-int5b-phi-detector}"
DESENS="${INT5B_DESENS_CONTAINER:-mh-int5b-desensitize}"
ROUTER="${INT5B_ROUTER_CONTAINER:-mh-int5b-model-router}"
INJECTION="${INT5B_INJECTION_CONTAINER:-mh-int5b-prompt-injection-scan}"
OUTBOUND="${INT5B_OUTBOUND_CONTAINER:-mh-int5b-outbound-safety}"
AUDIT="${INT5B_AUDIT_CONTAINER:-mh-int5b-audit-log}"
MOCK="${INT5B_MOCK_CONTAINER:-mh-int5b-mock-upstream}"
NEWAPI="${INT5B_NEWAPI_CONTAINER:-mh-int5b-new-api}"

CH_IMAGE="${CH_IMAGE:-clickhouse/clickhouse-server:24}"
REDIS_IMAGE="${REDIS_IMAGE:-redis:7-alpine}"
MOCK_IMAGE="${MOCK_IMAGE:-python:3.11-slim}"
NEWAPI_IMAGE="${NEWAPI_IMAGE:-medharness/new-api:int5b}"

NEWAPI_URL="http://127.0.0.1:13000"
MOCK_URL="http://127.0.0.1:18080"
MOCK_SERVER="${REPO_ROOT}/tools/mock_upstream/server.py"

CONTAINERS="$NEWAPI $MOCK $AUDIT $OUTBOUND $INJECTION $ROUTER $DESENS $PHI $REDIS $CH"
KEEP=0
TMP_ROOT=""
RC=0

usage() {
  cat <<USAGE
Usage: $0 [--keep]

Runs an INT-5b relay-path E2E smoke:
  ClickHouse :18123, mock upstream :18080, new-api :13000.

Env:
  VERSION                         MCP image tag (default: 0.5.0-edge)
  MODEL_ROUTER_TIER_SECRET        router HMAC secret (default: dev-int5b-secret)
  INT5B_CHANGE_ID                 model-router change id (default: int5b-relay)
USAGE
}

for arg in "$@"; do
  case "$arg" in
    --keep)
      KEEP=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

section() {
  echo
  echo "== $* =="
}

compact_json_file() {
  python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
    print(json.dumps(payload, ensure_ascii=False)[:900])
except Exception:
    print(path.read_text(encoding="utf-8", errors="replace")[:900])
PY
}

show_logs() {
  container="$1"
  echo "-- docker logs ${container} --" >&2
  docker logs --tail 80 "$container" >&2 2>/dev/null || true
}

fail() {
  RC=1
  echo "FAIL: $*" >&2
  echo "INT-5b FAIL" >&2
  exit 1
}

cleanup() {
  status=$?
  if [ "$KEEP" = "1" ]; then
    echo
    echo "== kept stack =="
    echo "network: $NET"
    echo "containers: $CONTAINERS"
    [ -n "${TMP_ROOT:-}" ] && echo "temp root: $TMP_ROOT"
    return "$status"
  fi
  docker rm -f $CONTAINERS >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  [ -n "${TMP_ROOT:-}" ] && rm -rf "$TMP_ROOT"
  return "$status"
}
trap cleanup EXIT

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "missing required command: $1"
}

json_success() {
  python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path

try:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception:
    sys.exit(1)
sys.exit(0 if payload.get("success") is True else 1)
PY
}

json_token_id_by_name() {
  python3 - "$1" "$2" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
target = sys.argv[2]
items = (((payload.get("data") or {}).get("items")) or [])
for item in items:
    if isinstance(item, dict) and item.get("name") == target:
        print(item.get("id", ""))
        sys.exit(0)
sys.exit(1)
PY
}

json_data_key() {
  python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
data = payload.get("data") or {}
print(data.get("key", ""))
PY
}

wait_host_http() {
  name="$1"
  url="$2"
  timeout="$3"
  for _ in $(seq 1 "$timeout"); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
    if [ "$code" = "200" ]; then
      echo "   OK   ${name}"
      return 0
    fi
    sleep 1
  done
  fail "${name} did not return HTTP 200 after ${timeout}s (${url})"
}

wait_clickhouse() {
  for _ in $(seq 1 90); do
    body="$(curl -sS 'http://127.0.0.1:18123/?query=SELECT%201' 2>/dev/null || true)"
    if [ "$body" = "1" ]; then
      echo "   OK   ClickHouse"
      return 0
    fi
    sleep 1
  done
  show_logs "$CH"
  fail "ClickHouse did not answer SELECT 1 on :18123 after 90s"
}

wait_redis() {
  for _ in $(seq 1 60); do
    if [ "$(docker exec "$REDIS" redis-cli ping 2>/dev/null || true)" = "PONG" ]; then
      echo "   OK   Redis"
      return 0
    fi
    sleep 1
  done
  show_logs "$REDIS"
  fail "Redis did not answer PONG after 60s"
}

wait_container_http() {
  name="$1"
  container="$2"
  path="${3:-/health}"
  timeout="${4:-90}"
  url="http://127.0.0.1:9000${path}"
  for _ in $(seq 1 "$timeout"); do
    code="$(
      docker exec "$container" python -c 'import sys, urllib.request; resp = urllib.request.urlopen(sys.argv[1], timeout=2); print(resp.status)' "$url" 2>/dev/null || true
    )"
    if [ "$code" = "200" ]; then
      echo "   OK   ${name} ${path}"
      return 0
    fi
    sleep 1
  done
  show_logs "$container"
  fail "${name} ${path} did not return HTTP 200 after ${timeout}s"
}

wait_audit_log() {
  for _ in $(seq 1 60); do
    if docker exec "$AUDIT" python server_v2.py health >/dev/null 2>&1; then
      echo "   OK   audit-log CLI health"
      return 0
    fi
    sleep 1
  done
  show_logs "$AUDIT"
  fail "audit-log CLI health failed after 60s"
}

ensure_mcp_image() {
  svc="$1"
  image="medharness/mcp-${svc}:${VERSION}"
  if docker image inspect "$image" >/dev/null 2>&1; then
    echo "   image present: $image"
    return 0
  fi

  echo "   image missing: $image"
  echo "   building with scripts/docker-build.sh ${svc}"
  printf '%s\n' "$VERSION" > "${TMP_ROOT}/VERSION"
  VERSION_FILE="${TMP_ROOT}/VERSION" bash "${REPO_ROOT}/scripts/docker-build.sh" "$svc" || \
    fail "image ${image} missing and scripts/docker-build.sh ${svc} failed"
  docker image inspect "$image" >/dev/null 2>&1 || \
    fail "scripts/docker-build.sh ${svc} completed but ${image} is still missing"
}

ensure_newapi_image() {
  if docker image inspect "$NEWAPI_IMAGE" >/dev/null 2>&1; then
    echo "   image present: $NEWAPI_IMAGE"
    return 0
  fi
  [ -f "${REPO_ROOT}/vendor/new-api/Dockerfile" ] || \
    fail "missing vendor/new-api/Dockerfile; cannot build ${NEWAPI_IMAGE}"
  echo "   image missing: $NEWAPI_IMAGE"
  echo "   building new-api from vendor/new-api"
  docker build -t "$NEWAPI_IMAGE" "${REPO_ROOT}/vendor/new-api" || \
    fail "docker build failed for ${NEWAPI_IMAGE}"
}

prepare_allowlist() {
  mkdir -p "${TMP_ROOT}/model-router-project/openspec/changes/${CHANGE_ID}"
  allowlist="${TMP_ROOT}/model-router-project/openspec/changes/${CHANGE_ID}/MODEL_ALLOWLIST.json"
  python3 - "$allowlist" "$CHANGE_ID" "$ALLOW_AGENT_ROLE" <<'PY'
import json
import sys
from pathlib import Path

target = Path(sys.argv[1])
change_id = sys.argv[2]
role = sys.argv[3]
target.write_text(
    json.dumps(
        {
            "schema_version": "T3.allowlist.v1",
            "policy_version": change_id,
            "models": [
                {
                    "id": "gpt-4o",
                    "vendor_family": "openai",
                    "deployment": "private://gpt-4o",
                    "allowed_agent_roles": [role],
                    "allowed_data_levels": ["L1", "L2", "L3", "L4"],
                    "rate_limit_qps": 20,
                }
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY
  echo "   allowlist: ${allowlist}"
}

api_post_json() {
  name="$1"
  url="$2"
  body="$3"
  out="$4"
  code="$(curl -sS -o "$out" -w '%{http_code}' -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
    -H 'Content-Type: application/json' -H "New-Api-User: ${NEWAPI_USER_ID:-1}" -d "$body" "$url" 2>"${TMP_ROOT}/curl.err" || true)"
  if [ "$code" != "200" ]; then
    echo "curl stderr: $(cat "${TMP_ROOT}/curl.err")" >&2
    fail "${name} returned HTTP ${code}; body: $(compact_json_file "$out")"
  fi
  json_success "$out" || fail "${name} returned success=false; body: $(compact_json_file "$out")"
  echo "   OK   ${name}"
}

api_get_json() {
  name="$1"
  url="$2"
  out="$3"
  code="$(curl -sS -o "$out" -w '%{http_code}' -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
    -H "New-Api-User: ${NEWAPI_USER_ID:-1}" "$url" 2>"${TMP_ROOT}/curl.err" || true)"
  if [ "$code" != "200" ]; then
    echo "curl stderr: $(cat "${TMP_ROOT}/curl.err")" >&2
    fail "${name} returned HTTP ${code}; body: $(compact_json_file "$out")"
  fi
  json_success "$out" || fail "${name} returned success=false; body: $(compact_json_file "$out")"
  echo "   OK   ${name}"
}

mock_log_count() {
  docker logs "$MOCK" 2>&1 | python3 -c 'import sys; print(sum(1 for _ in sys.stdin))'
}

read_mock_counter() {
  for path in /__count /__requests/count /requests/count /_debug/count /metrics; do
    body="$(curl -fsS --max-time 2 "${MOCK_URL}${path}" 2>/dev/null || true)"
    [ -n "$body" ] || continue
    value="$(python3 - "$body" <<'PY'
import json
import re
import sys

raw = sys.argv[1]
try:
    payload = json.loads(raw)
except Exception:
    payload = None

if isinstance(payload, dict):
    for key in ("count", "request_count", "requests", "total"):
        value = payload.get(key)
        if isinstance(value, int):
            print(value)
            sys.exit(0)
        if isinstance(value, str) and value.isdigit():
            print(value)
            sys.exit(0)

match = re.search(r"(?:request_count|requests_total|requests)\D+(\d+)", raw)
if match:
    print(match.group(1))
    sys.exit(0)
sys.exit(1)
PY
)"
    [ -n "$value" ] && { echo "$value"; return 0; }
  done
  return 1
}

require_cmd docker
require_cmd curl
require_cmd python3

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/medharness-int5b.XXXXXX")" || fail "mktemp failed"
COOKIE_JAR="${TMP_ROOT}/new-api.cookies"
touch "$COOKIE_JAR" || fail "cannot create cookie jar"

section "preflight"
echo "repo: $REPO_ROOT"
echo "version: $VERSION"
echo "change_id: $CHANGE_ID"
if [ -f "$ENV_FILE" ]; then
  echo "tier secret source: deploy/dev/int5b.env"
else
  echo "tier secret source: env/default"
fi
[ -f "$MOCK_SERVER" ] || \
  fail "mock upstream missing: tools/mock_upstream/server.py (expected on branch feat/mock-upstream)"

section "images"
for svc in phi-detector desensitize model-router prompt-injection-scan outbound-safety audit-log; do
  ensure_mcp_image "$svc"
done
ensure_newapi_image

section "network"
docker rm -f $CONTAINERS >/dev/null 2>&1 || true
docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET" >/dev/null || \
  fail "docker network create ${NET}"
echo "   OK   network ${NET}"

section "ClickHouse"
docker run -d --name "$CH" --network "$NET" -p 18123:8123 \
  -e CLICKHOUSE_DB=medharness \
  -e CLICKHOUSE_USER=default \
  -e CLICKHOUSE_PASSWORD= \
  -e CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1 \
  "$CH_IMAGE" >/dev/null || fail "ClickHouse container run failed"
wait_clickhouse

section "seed synthetic audit rows"
CLICKHOUSE_HOST=127.0.0.1 CLICKHOUSE_HTTP_PORT=18123 CLICKHOUSE_DATABASE=medharness \
  CLICKHOUSE_USER=default CLICKHOUSE_PASSWORD= \
  python3 "${REPO_ROOT}/scripts/dev_seed_audit.py" --rows 24 --reset || \
  fail "scripts/dev_seed_audit.py failed"

section "Redis"
docker run -d --name "$REDIS" --network "$NET" "$REDIS_IMAGE" redis-server --appendonly yes \
  >/dev/null || fail "Redis container run failed"
wait_redis

section "model-router allowlist"
prepare_allowlist

section "gate MCP services"
docker run -d --name "$PHI" --network "$NET" \
  "medharness/mcp-phi-detector:${VERSION}" serve --http --host 0.0.0.0 --port 9000 \
  >/dev/null || fail "phi-detector container run failed"

docker run -d --name "$DESENS" --network "$NET" \
  --tmpfs /tmp/medharness-keystore:rw,noexec,nosuid,size=16m,uid=9000,gid=9000,mode=700 \
  -e MEDHARNESS_KEYSTORE_ROOT=/tmp/medharness-keystore \
  -e CLICKHOUSE_HOST="$CH" \
  -e CLICKHOUSE_HTTP_PORT=8123 \
  -e CLICKHOUSE_DATABASE=medharness \
  -e CLICKHOUSE_USER=default \
  -e CLICKHOUSE_PASSWORD= \
  "medharness/mcp-desensitize:${VERSION}" serve --http --host 0.0.0.0 --port 9000 \
  >/dev/null || fail "desensitize container run failed"

docker run -d --name "$ROUTER" --network "$NET" \
  -v "${TMP_ROOT}/model-router-project:/medharness-int5b:ro" \
  -e CLAUDE_PROJECT_DIR=/medharness-int5b \
  -e MODEL_ROUTER_TIER_SECRET="$TIER_SECRET" \
  "medharness/mcp-model-router:${VERSION}" serve --http --host 0.0.0.0 --port 9000 \
  >/dev/null || fail "model-router container run failed"

docker run -d --name "$INJECTION" --network "$NET" \
  "medharness/mcp-prompt-injection-scan:${VERSION}" serve --http --host 0.0.0.0 --port 9000 \
  >/dev/null || fail "prompt-injection-scan container run failed"

docker run -d --name "$OUTBOUND" --network "$NET" \
  "medharness/mcp-outbound-safety:${VERSION}" serve --http --host 0.0.0.0 --port 9000 \
  >/dev/null || fail "outbound-safety container run failed"

wait_container_http "phi-detector" "$PHI" /health 120
wait_container_http "desensitize" "$DESENS" /health 90
wait_container_http "model-router" "$ROUTER" /health 90
wait_container_http "prompt-injection-scan" "$INJECTION" /health 90
wait_container_http "outbound-safety" "$OUTBOUND" /health 90

section "audit-log"
docker run -d --name "$AUDIT" --network "$NET" \
  -e CLICKHOUSE_HOST="$CH" \
  -e CLICKHOUSE_HTTP_PORT=8123 \
  -e CLICKHOUSE_DATABASE=medharness \
  -e CLICKHOUSE_USER=default \
  -e CLICKHOUSE_PASSWORD= \
  -e MEDHARNESS_AUDIT_FALLBACK_DIR=/tmp/medharness-audit \
  "medharness/mcp-audit-log:${VERSION}" >/dev/null || fail "audit-log container run failed"
wait_audit_log

section "mock upstream"
docker run -d --name "$MOCK" --network "$NET" -p 18080:18080 \
  -v "${REPO_ROOT}/tools/mock_upstream:/app:ro" \
  -w /app \
  "$MOCK_IMAGE" python3 server.py --port 18080 \
  >/dev/null || fail "mock upstream container run failed"
wait_host_http "mock-upstream /health" "${MOCK_URL}/health" 60

section "new-api"
docker run -d --name "$NEWAPI" --network "$NET" -p 13000:3000 \
  -e PORT=3000 \
  -e GIN_MODE=release \
  -e SESSION_SECRET=dev-int5b \
  -e MEMORY_CACHE_ENABLED=true \
  -e GLOBAL_API_RATE_LIMIT_ENABLE=false \
  -e CRITICAL_RATE_LIMIT_ENABLE=false \
  -e MEDHARNESS_DISABLE_RESALE_SURFACE=true \
  -e PHI_DETECTOR_URL="http://${PHI}:9000" \
  -e DESENSITIZE_URL="http://${DESENS}:9000" \
  -e MODEL_ROUTER_URL="http://${ROUTER}:9000" \
  -e INJECTION_URL="http://${INJECTION}:9000" \
  -e OUTBOUND_SAFETY_URL="http://${OUTBOUND}:9000" \
  -e MODEL_ROUTER_TIER_SECRET="$TIER_SECRET" \
  "$NEWAPI_IMAGE" >/dev/null || fail "new-api container run failed"
wait_host_http "new-api /api/status" "${NEWAPI_URL}/api/status" 120

section "configure new-api admin API"
RESP="${TMP_ROOT}/response.json"
# This new-api fork requires explicit system setup (no auto root:123456); the
# setup password must be >= 8 chars. Initialize, then log in with it.
ROOT_PASSWORD="${INT5B_ROOT_PASSWORD:-int5bRoot123}"
api_post_json "setup" "${NEWAPI_URL}/api/setup" \
  "{\"username\":\"root\",\"password\":\"${ROOT_PASSWORD}\",\"confirmPassword\":\"${ROOT_PASSWORD}\",\"SelfUseModeEnabled\":true,\"DemoSiteEnabled\":false}" "$RESP"
api_post_json "login root" "${NEWAPI_URL}/api/user/login" \
  "{\"username\":\"root\",\"password\":\"${ROOT_PASSWORD}\"}" "$RESP"

CHANNEL_BODY="$(
  python3 - "$MOCK" <<'PY'
import json
import sys

mock = sys.argv[1]
print(json.dumps({
    "mode": "single",
    "channel": {
        "type": 1,
        "base_url": f"http://{mock}:18080",
        "key": "sk-mock",
        "models": "gpt-4o",
        "group": "default",
        "status": 1,
        "name": "MockUpstream",
    },
}, separators=(",", ":")))
PY
)"
api_post_json "create MockUpstream channel" "${NEWAPI_URL}/api/channel/" "$CHANNEL_BODY" "$RESP"
api_post_json "refresh channel abilities/cache" "${NEWAPI_URL}/api/channel/fix" '{}' "$RESP"

api_post_json "create int5b token" "${NEWAPI_URL}/api/token/" \
  '{"name":"int5b","remain_quota":9999999,"expired_time":-1,"group":"default"}' "$RESP"
api_get_json "list tokens" "${NEWAPI_URL}/api/token/?p=1&size=20" "$RESP"
TOKEN_ID="$(json_token_id_by_name "$RESP" int5b || true)"
[ -n "$TOKEN_ID" ] || fail "could not find created token id in token list: $(compact_json_file "$RESP")"
echo "   token id: $TOKEN_ID"
api_post_json "fetch token key" "${NEWAPI_URL}/api/token/${TOKEN_ID}/key" '{}' "$RESP"
TOKEN_KEY="$(json_data_key "$RESP")"
[ -n "$TOKEN_KEY" ] || fail "token key response had no data.key: $(compact_json_file "$RESP")"
case "$TOKEN_KEY" in
  sk-*) AUTH_HEADER="Bearer ${TOKEN_KEY}" ;;
  *) AUTH_HEADER="Bearer sk-${TOKEN_KEY}" ;;
esac
echo "   token key captured"

section "ALLOW relay path"
ALLOW_BODY="${TMP_ROOT}/allow.json"
ALLOW_CODE="$(curl -sS -o "$ALLOW_BODY" -w '%{http_code}' \
  -H "Authorization: ${AUTH_HEADER}" \
  -H 'Content-Type: application/json' \
  -H "X-MedHarness-Agent-Role: ${ALLOW_AGENT_ROLE}" \
  -H "X-MedHarness-Change-Id: ${CHANGE_ID}" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hello from int5b"}]}' \
  "${NEWAPI_URL}/v1/chat/completions" 2>"${TMP_ROOT}/curl.err" || true)"
if [ "$ALLOW_CODE" != "200" ]; then
  echo "curl stderr: $(cat "${TMP_ROOT}/curl.err")" >&2
  fail "ALLOW relay returned HTTP ${ALLOW_CODE}; body: $(compact_json_file "$ALLOW_BODY")"
fi
if ! grep -Fq '[mock-upstream]' "$ALLOW_BODY"; then
  fail "ALLOW relay body did not contain [mock-upstream]; body: $(compact_json_file "$ALLOW_BODY")"
fi
echo "   OK   allow -> HTTP 200 + mock marker"

section "DENY relay path"
COUNTER_BEFORE="$(read_mock_counter || true)"
if [ -n "$COUNTER_BEFORE" ]; then
  echo "   mock counter before deny: $COUNTER_BEFORE"
  LOG_BEFORE=""
else
  LOG_BEFORE="$(mock_log_count)"
  echo "   mock log lines before deny: $LOG_BEFORE"
fi
DENY_SINCE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DENY_BODY="${TMP_ROOT}/deny.json"
DENY_CODE="$(curl -sS -o "$DENY_BODY" -w '%{http_code}' \
  -H "Authorization: ${AUTH_HEADER}" \
  -H 'Content-Type: application/json' \
  -H "X-MedHarness-Agent-Role: ${DENY_AGENT_ROLE}" \
  -H "X-MedHarness-Change-Id: ${CHANGE_ID}" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hello from denied int5b"}]}' \
  "${NEWAPI_URL}/v1/chat/completions" 2>"${TMP_ROOT}/curl.err" || true)"
if [ "$DENY_CODE" != "503" ]; then
  echo "curl stderr: $(cat "${TMP_ROOT}/curl.err")" >&2
  fail "DENY relay returned HTTP ${DENY_CODE}, want 503; body: $(compact_json_file "$DENY_BODY")"
fi
if [ -n "$COUNTER_BEFORE" ]; then
  COUNTER_AFTER="$(read_mock_counter || true)"
  [ -n "$COUNTER_AFTER" ] || fail "mock counter was available before deny but not after deny"
  echo "   mock counter after deny: $COUNTER_AFTER"
  [ "$COUNTER_AFTER" = "$COUNTER_BEFORE" ] || \
    fail "mock upstream counter changed during DENY path: before=${COUNTER_BEFORE} after=${COUNTER_AFTER}"
else
  sleep 1
  LOG_AFTER="$(mock_log_count)"
  echo "   mock log lines after deny: $LOG_AFTER"
  if [ "$LOG_AFTER" != "$LOG_BEFORE" ]; then
    RECENT="$(docker logs --since "$DENY_SINCE" "$MOCK" 2>&1 || true)"
    fail "mock upstream logs grew during DENY path: before=${LOG_BEFORE} after=${LOG_AFTER}; recent=${RECENT}"
  fi
fi
echo "   OK   deny -> HTTP 503 + zero new mock upstream requests"

echo
echo "INT-5b PASS"
exit "$RC"
