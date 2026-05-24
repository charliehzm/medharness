#!/usr/bin/env bash
# T4.7 · daily verify hashchain · exit 0 if chain intact · exit 1 if tampered or error
set -euo pipefail

readonly DEFAULT_BASE="/data/medharness/audit"
readonly BASE_DIR="${MEDHARNESS_AUDIT_BASE:-${DEFAULT_BASE}}"
readonly SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly LOGIC="${SCRIPT_DIR}/verify_hashchain_logic.py"
readonly DEFAULT_INPUT="${BASE_DIR}/audit_log_export.jsonl"
readonly INPUT="${1:-${VERIFY_HASHCHAIN_INPUT:-${DEFAULT_INPUT}}}"

detect_python() {
  if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    echo "${REPO_ROOT}/.venv/bin/python"
    return
  fi
  for cand in python3.12 python3.11 python3.10 python3; do
    if command -v "${cand}" >/dev/null 2>&1; then
      echo "${cand}"
      return
    fi
  done
  echo ""
}

PY="$(detect_python)"
if [[ -z "${PY}" ]]; then
  echo "❌ Python 3.10+ not found" >&2
  exit 4
fi

c_pass() { printf "\033[1;32m✅ %s\033[0m\n" "$*"; }
c_fail() { printf "\033[1;31m❌ %s\033[0m\n" "$*" >&2; }

echo "→ verify-hashchain · input=${INPUT}"

if [[ ! -f "${INPUT}" ]]; then
  c_fail "input file not found: ${INPUT}"
  exit 2
fi

if "${PY}" "${LOGIC}" --input "${INPUT}"; then
  c_pass "hashchain verify PASSED · input=${INPUT}"
  exit 0
else
  c_fail "hashchain verify FAILED · input=${INPUT} · SEV-1 alert"
  exit 1
fi
