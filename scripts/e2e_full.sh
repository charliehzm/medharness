#!/usr/bin/env bash
# One-command full-coverage E2E orchestrator for the running prod compose stack.
#
#   bash scripts/e2e_full.sh            # assume the stack is up; run all layers
#   bash scripts/e2e_full.sh --up       # `up -d` the stack first if the DMZ is down
#   bash scripts/e2e_full.sh --fresh    # down -v + fresh up --build (production-deploy sim)
#   bash scripts/e2e_full.sh --no-ui    # skip the Playwright (Layer 1) UI suite
#
# Layers: 5 (mock unit, offline) · 2 gate matrix · 3 data integrity · 4 personas
# (live, via MEDHARNESS_LIVE_BASE) · the golden relay smoke · 1 Playwright UI.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
BASE="${MEDHARNESS_LIVE_BASE:-https://localhost:18443}"
PY="${PY:-.venv/bin/python}"
COMPOSE=(-f deploy/docker-compose.prod.yml -f deploy/docker-compose.local.yml --env-file deploy/.env.production)
UP=0; FRESH=0; UI=1
for a in "$@"; do case "$a" in --up) UP=1;; --fresh) FRESH=1; UP=1;; --no-ui) UI=0;; esac; done

# macOS ships bash 3.2 (no `declare -A`), so track results in scalar vars.
R_L5="?"; R_L24="?"; R_SMOKE="?"; R_L1="?"
record() {
  case "$1" in
    L5)    R_L5="$2";;
    L2-4)  R_L24="$2";;
    SMOKE) R_SMOKE="$2";;
    L1)    R_L1="$2";;
  esac
}
hr() { printf -- '------------------------------------------------------------\n'; }
dmz_code() { curl -sk -o /dev/null -w '%{http_code}' "$BASE/health" 2>/dev/null; }

hr; echo "[1/6] stack"
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

hr; echo "[2/6] seed synthetic 0-PHI audit rows"
docker cp scripts/dev_seed_audit.py medharness-a0-api:/tmp/dev_seed_audit.py >/dev/null 2>&1
docker exec medharness-a0-api python /tmp/dev_seed_audit.py --rows 40 --reset 2>&1 | tail -1

hr; echo "[3/6] Layer 5 — mock simulator unit (offline)"
$PY -m pytest tools/mock_upstream/test_mock_upstream.py -q && record L5 PASS || record L5 FAIL

hr; echo "[4/6] Layers 2/3/4 — gate matrix + data integrity + personas (live)"
MEDHARNESS_LIVE_BASE="$BASE" $PY -m pytest tests/e2e_live tests/sim -q && record "L2-4" PASS || record "L2-4" FAIL

hr; echo "[5/6] relay smoke (1xALLOW / 1xDENY golden)"
if bash scripts/relay_prod_stack_smoke.sh >/tmp/e2e_smoke.log 2>&1; then
  record SMOKE PASS; grep -m1 "RELAY-PROD-STACK E2E PASS" /tmp/e2e_smoke.log | sed 's/^/  /'
else
  record SMOKE FAIL; tail -5 /tmp/e2e_smoke.log
fi

if [ "$UI" = 1 ]; then
  hr; echo "[6/6] Layer 1 — Playwright UI (real browser)"
  if ( cd web && MEDHARNESS_LIVE_BASE="$BASE" bun run e2e ); then record L1 PASS; else record L1 FAIL; fi
else
  record L1 SKIP
fi

hr; echo "SUMMARY"
printf '  %-7s %s\n' L5    "$R_L5"
printf '  %-7s %s\n' L2-4  "$R_L24"
printf '  %-7s %s\n' SMOKE "$R_SMOKE"
printf '  %-7s %s\n' L1    "$R_L1"
for v in "$R_L5" "$R_L24" "$R_SMOKE" "$R_L1"; do
  [ "$v" = FAIL ] && { echo "RESULT: FAILURES PRESENT"; exit 1; }
done
echo "RESULT: ALL LAYERS PASS"
