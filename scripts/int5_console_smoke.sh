#!/usr/bin/env bash
# INT-5a · Console-live smoke: real ClickHouse + real A0 (synthetic data, 0-PHI).
# Proves the Console BFF path end-to-end against a REAL query backend (vs INT-1's
# in-process FakeClickHouse). Mock-only data; touches no real provider / PHI.
#
#   scripts/int5_console_smoke.sh [--keep]
#
# --keep leaves CH (:18123) + A0 (:19000) running for FE live 连调.
set -uo pipefail

NET=medharness-int5
CH=mh-int5-ch
A0=mh-int5-a0
CH_IMAGE=clickhouse/clickhouse-server:24
A0_IMAGE=medharness/mcp-a0-api:int5
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

cleanup() { [ "$KEEP" = "1" ] || { docker rm -f "$CH" "$A0" >/dev/null 2>&1; docker network rm "$NET" >/dev/null 2>&1; }; }
trap cleanup EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== net =="; docker network create "$NET" >/dev/null 2>&1 || true

echo "== ClickHouse =="
docker rm -f "$CH" >/dev/null 2>&1
docker run -d --name "$CH" --network "$NET" -p 18123:8123 \
  -e CLICKHOUSE_DB=medharness -e CLICKHOUSE_USER=default -e CLICKHOUSE_PASSWORD= \
  -e CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1 "$CH_IMAGE" >/dev/null || fail "ch run"
for i in $(seq 1 60); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' 'http://127.0.0.1:18123/?query=SELECT%201' 2>/dev/null)" = "200" ] && break
  sleep 1
done
[ "$(curl -s 'http://127.0.0.1:18123/?query=SELECT%201' 2>/dev/null)" = "1" ] || fail "ch not ready"
echo "   ClickHouse up"

echo "== seed synthetic audit rows =="
CLICKHOUSE_HOST=127.0.0.1 CLICKHOUSE_HTTP_PORT=18123 CLICKHOUSE_DATABASE=medharness \
  python3 scripts/dev_seed_audit.py --rows 24 --reset || fail "seed"

echo "== A0 (against real CH) =="
docker rm -f "$A0" >/dev/null 2>&1
docker run -d --name "$A0" --network "$NET" -p 19000:9000 \
  -e CLICKHOUSE_HOST="$CH" -e CLICKHOUSE_HTTP_PORT=8123 \
  -e CLICKHOUSE_DATABASE=medharness -e CLICKHOUSE_USER=default -e CLICKHOUSE_PASSWORD= \
  "$A0_IMAGE" >/dev/null || fail "a0 run"
for i in $(seq 1 40); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:19000/health 2>/dev/null)" = "200" ] && break
  sleep 0.5
done
[ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:19000/health 2>/dev/null)" = "200" ] || fail "a0 /health"
echo "   A0 up"

echo "== assert A0 serves REAL data (200 + non-trivial) =="
RC=0
for ep in posture traffic events cost channels upstreams; do
  body="$(curl -s "http://127.0.0.1:19000/api/v1/$ep")"
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:19000/api/v1/$ep")"
  len=${#body}
  if [ "$code" = "200" ] && [ "$len" -gt 20 ]; then
    echo "   OK   /api/v1/$ep -> 200 (${len}b)"
  else
    echo "   BAD  /api/v1/$ep -> $code (${len}b)"; RC=1
  fi
done

# audit detail by a real seeded ref
ref="$(curl -s 'http://127.0.0.1:18123/?query=SELECT%20current_hash%20FROM%20medharness._audit_log%20ORDER%20BY%20row_id%20DESC%20LIMIT%201' 2>/dev/null)"
if [ -n "$ref" ]; then
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:19000/api/v1/audit/$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$ref")")"
  echo "   audit/<real-ref> -> $code"
fi

# 0-PHI spot check: no obvious PHI markers in aggregated payloads
allbody="$(for ep in posture traffic events cost channels upstreams; do curl -s "http://127.0.0.1:19000/api/v1/$ep"; done)"
for bad in '"email"' '"phone"' 'raw_text' '"prompt"'; do
  echo "$allbody" | grep -q "$bad" && { echo "   PHI-LEAK marker $bad present!"; RC=1; }
done
[ "$RC" = "0" ] && echo "   0-PHI spot check clean"

[ "$RC" = "0" ] && echo "INT-5a PASS" || echo "INT-5a FAIL"
[ "$KEEP" = "1" ] && echo "(kept up: CH :18123, A0 :19000 — FE: VITE_API_MODE=live VITE base /api/v1 -> http://127.0.0.1:19000)"
exit $RC
