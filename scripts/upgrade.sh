#!/usr/bin/env bash
# T12.2 · MedHarness upgrade · v0.5.0 stub · v0.6+ implements real migrations
# Usage: bash scripts/upgrade.sh [--from VERSION] [--to VERSION] [--dry-run]
set -euo pipefail

readonly CURRENT_VERSION="$(tr -d '\n' < VERSION 2>/dev/null || echo unknown)"

FROM=""
TO="${CURRENT_VERSION}"
DRY_RUN=""

c_pass() { printf "\033[1;32m✅ %s\033[0m\n" "$*"; }
c_warn() { printf "\033[1;33m⚠️  %s\033[0m\n" "$*"; }
c_fail() { printf "\033[1;31m❌ %s\033[0m\n" "$*" >&2; }

usage() {
  cat <<USAGE
Usage: $0 [--from FROM_VERSION] [--to TO_VERSION] [--dry-run]

Default:
  --to ${CURRENT_VERSION} (current VERSION file)

v0.5.0-edge is the first MedHarness release, so no upgrade path is needed yet.
v0.6+ will implement real migrations (volume schema, ClickHouse table, etc.).

Exit codes:
  0 = no upgrade needed
  1 = unknown or unimplemented upgrade path
  2 = argument error
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      FROM="${2:-}"
      shift 2
      ;;
    --to)
      TO="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    --help | -h)
      usage
      exit 0
      ;;
    *)
      c_fail "unknown argument: $1"
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${TO}" ]]; then
  c_fail "--to requires a non-empty value"
  exit 2
fi

c_warn "Current version: ${CURRENT_VERSION}"
c_warn "Requested upgrade: ${FROM:-<first-install>} -> ${TO}"

if [[ -n "${DRY_RUN}" ]]; then
  c_warn "[DRY RUN] No migration actions will be executed"
fi

if [[ "${CURRENT_VERSION}" == "0.5.0-edge" && ( -z "${FROM}" || "${FROM}" == "${CURRENT_VERSION}" ) && "${TO}" == "${CURRENT_VERSION}" ]]; then
  c_pass "MedHarness v0.5.0-edge is the first release · no upgrade needed"
  c_warn "v0.6+ migration script will be implemented when 0.6 ships"
  exit 0
fi

case "${FROM} -> ${TO}" in
  "0.5.0-edge -> 0.6.0")
    c_fail "v0.5.0 -> v0.6 migration not yet implemented (placeholder)"
    c_warn "Will be implemented in v0.6 ship"
    exit 1
    ;;
  *)
    c_fail "unknown upgrade path: ${FROM:-<first-install>} -> ${TO}"
    exit 1
    ;;
esac
