#!/usr/bin/env bash
# One-command full-coverage E2E orchestrator for the running prod compose stack.
#
#   bash scripts/e2e_full.sh            # assume the stack is up; run all layers
#   bash scripts/e2e_full.sh --up       # `up -d` the stack first if the DMZ is down
#   bash scripts/e2e_full.sh --fresh    # down -v + fresh up --build (production-deploy sim)
#   bash scripts/e2e_full.sh --no-ui    # skip the Playwright (Layer 1) UI suite
#
# Layers: offline units (mock simulator + Go gate pure-funcs) · 2 gate matrix
# (incl. embeddings/streaming fixes) · 3 data integrity · 4 closed-loop + personas
# (live) · fail-closed (isolated) · golden relay smoke · 1 Playwright UI.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
BASE="${MEDHARNESS_LIVE_BASE:-https://localhost:18443}"
PY="${PY:-.venv/bin/python}"
A0="${MEDHARNESS_A0_CONTAINER:-medharness-a0-api}"
COMPOSE=(-f deploy/docker-compose.prod.yml -f deploy/docker-compose.local.yml --env-file deploy/.env.production)
UP=0; FRESH=0; UI=1
for a in "$@"; do case "$a" in --up) UP=1;; --fresh) FRESH=1; UP=1;; --no-ui) UI=0;; esac; done

# macOS ships bash 3.2 (no `declare -A`), so track results in scalar vars.
R_OFF="?"; R_L24="?"; R_FC="?"; R_SMOKE="?"; R_L1="?"
record() {
  case "$1" in
    OFF)   R_OFF="$2";;
    L2-4)  R_L24="$2";;
    FC)    R_FC="$2";;
    SMOKE) R_SMOKE="$2";;
    L1)    R_L1="$2";;
  esac
}
hr() { printf -- '------------------------------------------------------------\n'; }
dmz_code() { curl -sk -o /dev/null -w '%{http_code}' "$BASE/health" 2>/dev/null; }
seed_scenarios() {  # seed the deterministic 15-scenario _audit_log; capture the manifest
  docker cp scripts/seed_scenarios.py "${A0}:/tmp/seed_scenarios.py" >/dev/null 2>&1
  docker exec "$A0" python /tmp/seed_scenarios.py --reset --emit-manifest > /tmp/e2e_seed_manifest.json 2>/dev/null
}
provision_admin_token() {  # root access_token for A0 user-management writes — generated
  # at RUNTIME from new-api (never committed). Skips if already set (normal run);
  # recreates a0-api with it on a fresh stack so the user-management e2e works OOTB.
  [ -n "$(docker exec "$A0" printenv NEW_API_ADMIN_TOKEN 2>/dev/null)" ] && return 0
  local tok
  tok=$(docker exec -i "$A0" python - <<'PY' 2>/dev/null
import http.cookiejar, json, urllib.request
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def call(p, b=None):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request("http://new-api:3000" + p, data=d, method="POST" if b is not None else "GET")
    r.add_header("Content-Type", "application/json"); r.add_header("New-Api-User", "1")
    return json.loads(op.open(r, timeout=10).read().decode() or "{}")
call("/api/user/login", {"username": "admin", "password": "medharness123"})
print(call("/api/user/token").get("data") or "")
PY
)
  [ -n "$tok" ] || { echo "  WARN: could not provision admin token (user-mgmt e2e may skip)"; return 0; }
  NEW_API_ADMIN_TOKEN="$tok" NEW_API_ADMIN_USER_ID=1 docker compose "${COMPOSE[@]}" up -d a0-api >/dev/null 2>&1
  for _ in $(seq 1 30); do [ "$(docker inspect -f '{{.State.Health.Status}}' "$A0" 2>/dev/null)" = healthy ] && break; sleep 2; done
}

hr; echo "[1/7] stack"
if [ "$FRESH" = 1 ]; then
  echo "  fresh: down -v + up --build (production-deploy simulation)"
  docker compose "${COMPOSE[@]}" down -v >/dev/null 2>&1
  docker compose "${COMPOSE[@]}" up -d --build 2>&1 | tail -2
elif [ "$UP" = 1 ] && [ "$(dmz_code)" != 200 ]; then
  docker compose "${COMPOSE[@]}" up -d 2>&1 | tail -2
fi
for _ in $(seq 1 90); do [ "$(dmz_code)" = 200 ] && break; sleep 2; done
[ "$(dmz_code)" = 200 ] || { echo "  ERROR: DMZ not healthy at $BASE"; exit 1; }
echo "  DMZ $BASE healthy"
provision_admin_token

hr; echo "[2/7] seed deterministic 15-scenario 0-PHI audit rows"
seed_scenarios && sed 's/.*"total": *\([0-9]*\).*/  seeded \1 scenario rows + manifest/' /tmp/e2e_seed_manifest.json | head -1

hr; echo "[3/7] offline units — mock simulator + medical presets + Go gate pure-funcs"
OFF_OK=1
$PY -m pytest tools/mock_upstream/test_mock_upstream.py tests/test_medical_presets.py -q || OFF_OK=0
( cd vendor/new-api && go test ./middleware/ -count=1 ) || OFF_OK=0
[ "$OFF_OK" = 1 ] && record OFF PASS || record OFF FAIL

hr; echo "[4a/7] Layers 2/3/4 — gate matrix + data integrity + closed-loop/personas + Access mgmt (live)"
L24_OK=1
ACCESS_MGMT_LIVE=(
  tests/e2e_live/test_admin_channels_mgmt_live.py
  tests/e2e_live/test_admin_tokens_mgmt_live.py
  tests/e2e_live/test_admin_users_mgmt_live.py
  tests/e2e_live/test_access_closedloop_e2e_live.py
)
echo "  · Access mgmt write-proxies (channels/tokens/users) + Console-token closed loop"
MEDHARNESS_LIVE_BASE="$BASE" $PY -m pytest "${ACCESS_MGMT_LIVE[@]}" -q || L24_OK=0
echo "  · gate matrix + data integrity + closed-loop/personas"
MEDHARNESS_LIVE_BASE="$BASE" $PY -m pytest tests/e2e_live tests/sim \
  --ignore=tests/e2e_live/test_relay_failclosed_live.py \
  "${ACCESS_MGMT_LIVE[@]/#/--ignore=}" -q || L24_OK=0
[ "$L24_OK" = 1 ] && record "L2-4" PASS || record "L2-4" FAIL

hr; echo "[4b/7] fail-closed (isolated — pauses/stops an MCP, restores after)"
MEDHARNESS_LIVE_BASE="$BASE" $PY -m pytest tests/e2e_live/test_relay_failclosed_live.py -q \
  && record FC PASS || record FC FAIL

hr; echo "[5/7] relay smoke (1xALLOW / 1xDENY golden)"
if bash scripts/relay_prod_stack_smoke.sh >/tmp/e2e_smoke.log 2>&1; then
  record SMOKE PASS; grep -m1 "RELAY-PROD-STACK E2E PASS" /tmp/e2e_smoke.log | sed 's/^/  /'
else
  record SMOKE FAIL; tail -5 /tmp/e2e_smoke.log
fi

if [ "$UI" = 1 ]; then
  hr; echo "[6/7] re-seed + Layer 1 Playwright UI (real browser)"
  seed_scenarios  # deterministic Console data for the UI layer
  if ( cd web && MEDHARNESS_LIVE_BASE="$BASE" bun run e2e ); then record L1 PASS; else record L1 FAIL; fi
else
  record L1 SKIP
fi

hr; echo "[7/7] SUMMARY"
printf '  %-7s %s\n' OFFLINE "$R_OFF"
printf '  %-7s %s\n' L2-4    "$R_L24"
printf '  %-7s %s\n' FAILCLO "$R_FC"
printf '  %-7s %s\n' SMOKE   "$R_SMOKE"
printf '  %-7s %s\n' L1      "$R_L1"
for v in "$R_OFF" "$R_L24" "$R_FC" "$R_SMOKE" "$R_L1"; do
  [ "$v" = FAIL ] && { echo "RESULT: FAILURES PRESENT"; exit 1; }
done
echo "RESULT: ALL LAYERS PASS"
