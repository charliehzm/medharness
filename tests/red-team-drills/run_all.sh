#!/usr/bin/env bash
# tests/red-team-drills/run_all.sh
# 月度红队演练：用合成 PHI 测脱敏 / 路由 / 审计是否阻断
set -euo pipefail

readonly ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
readonly OUT="${ROOT}/tests/red-team-drills/output"
mkdir -p "$OUT"

c_pass() { printf "\033[1;32m✅ %s\033[0m\n" "$*"; }
c_fail() { printf "\033[1;31m❌ %s\033[0m\n" "$*"; }

drill_phi_recall() {
  echo "→ drill 1: PHI detection recall ≥ 92%"
  python "${ROOT}/tests/red-team-drills/drill_phi_recall.py" --out "${OUT}/recall.json"
}

drill_router_bypass() {
  echo "→ drill 2: model-router bypass detection"
  python "${ROOT}/tests/red-team-drills/drill_router_bypass.py" --out "${OUT}/router.json"
}

drill_audit_replay() {
  echo "→ drill 3: AUDIT_BUNDLE replay"
  python "${ROOT}/tests/red-team-drills/drill_audit_replay.py" --out "${OUT}/replay.json"
}

drill_injection() {
  echo "→ drill 4: prompt-injection in RAG corpus"
  python "${ROOT}/tests/red-team-drills/drill_injection.py" --out "${OUT}/injection.json"
}

main() {
  cd "$ROOT"
  drill_phi_recall
  drill_router_bypass
  drill_audit_replay
  drill_injection
  echo
  c_pass "All red-team drills completed → ${OUT}/"
}

main "$@"
