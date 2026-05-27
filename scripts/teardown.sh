#!/usr/bin/env bash
# T12.2 · MedHarness teardown · docker compose down + optional data purge
# Usage: bash scripts/teardown.sh [--force] [--dry-run] [--purge-data]
set -euo pipefail

readonly COMPOSE_FILE="deploy/docker-compose.prod.yml"
readonly DATA_DIRS=(
  "/data/medharness/audit"
  "/data/medharness/keystore"
  "/data/medharness/clickhouse"
  "/var/medharness/backups"
)
readonly MCP_IMAGES=(
  "phi-detector"
  "desensitize"
  "model-router"
  "audit-log"
  "ci-trigger"
  "internal-kb"
  "pm-bridge"
  "vector-db"
)

FORCE=""
DRY_RUN=""
PURGE_DATA=""

c_pass() { printf "\033[1;32m✅ %s\033[0m\n" "$*"; }
c_warn() { printf "\033[1;33m⚠️  %s\033[0m\n" "$*"; }
c_fail() { printf "\033[1;31m❌ %s\033[0m\n" "$*" >&2; }

usage() {
  cat <<USAGE
Usage: $0 [--force] [--dry-run] [--purge-data]

Default:
  docker compose down --volumes --remove-orphans, remove MedHarness MCP images,
  remove MedHarness networks, and preserve /data/medharness/* data.

Options:
  --force       Skip interactive confirmation prompts
  --dry-run     Print planned actions only
  --purge-data  Delete /data/medharness/* + /var/medharness/backups (dangerous)

Exit codes:
  0 = OK
  1 = user cancelled
  2 = docker failure
  3 = compose file missing
  4 = argument error
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE="1"
      shift
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    --purge-data)
      PURGE_DATA="1"
      shift
      ;;
    --help | -h)
      usage
      exit 0
      ;;
    *)
      c_fail "unknown argument: $1"
      usage >&2
      exit 4
      ;;
  esac
done

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  c_fail "compose file not found: ${COMPOSE_FILE}"
  exit 3
fi

print_plan() {
  c_warn "Teardown plan:"
  echo "  1. docker compose -f ${COMPOSE_FILE} down --volumes --remove-orphans"
  echo "  2. remove MedHarness MCP images:"
  for mcp in "${MCP_IMAGES[@]}"; do
    echo "     - medharness/mcp-${mcp}"
    echo "     - medharness/mcp-${mcp}:*"
  done
  echo "  3. remove MedHarness networks:"
  echo "     - medharness_internal"
  echo "     - medharness_dmz"
  if [[ -n "${PURGE_DATA}" ]]; then
    c_warn "  4. PURGE DATA (permanent; may include audit data, keystore, and backups):"
    for dir in "${DATA_DIRS[@]}"; do
      echo "     - ${dir}"
    done
  else
    c_warn "  4. Data preserved in /data/medharness/* and /var/medharness/backups"
  fi
}

confirm_or_exit() {
  if [[ -n "${FORCE}" ]]; then
    return
  fi

  local reply1
  read -r -p "Confirm teardown? [yes/N] " reply1
  if [[ ! "${reply1}" =~ ^[Yy]es$ ]]; then
    c_warn "Teardown cancelled (first prompt)"
    exit 1
  fi

  if [[ -n "${PURGE_DATA}" ]]; then
    local reply2
    c_fail "PURGE DATA will permanently delete MedHarness data directories."
    read -r -p "Type 'PURGE' to confirm: " reply2
    if [[ "${reply2}" != "PURGE" ]]; then
      c_warn "Teardown cancelled (purge-data prompt)"
      exit 1
    fi
  fi
}

remove_images() {
  local mcp
  for mcp in "${MCP_IMAGES[@]}"; do
    docker rmi "medharness/mcp-${mcp}" 2>/dev/null || true
    docker images --format '{{.Repository}}:{{.Tag}}' "medharness/mcp-${mcp}" \
      | while IFS= read -r image_tag; do
        if [[ -n "${image_tag}" && "${image_tag}" != *":<none>" ]]; then
          docker rmi "${image_tag}" 2>/dev/null || true
        fi
      done
  done
}

purge_data() {
  local dir
  for dir in "${DATA_DIRS[@]}"; do
    if [[ -d "${dir}" ]]; then
      sudo rm -rf "${dir}" 2>/dev/null || rm -rf "${dir}" 2>/dev/null || c_warn "Failed to remove ${dir} (may need sudo)"
    fi
  done
}

print_plan

if [[ -n "${DRY_RUN}" ]]; then
  c_warn "[DRY RUN] No actual changes made"
  exit 0
fi

confirm_or_exit

if ! command -v docker >/dev/null 2>&1; then
  c_fail "docker not found"
  exit 2
fi

c_warn "Starting teardown..."

docker compose -f "${COMPOSE_FILE}" down --volumes --remove-orphans || {
  c_fail "docker compose down failed"
  exit 2
}

remove_images
docker network rm medharness_internal medharness_dmz 2>/dev/null || true

if [[ -n "${PURGE_DATA}" ]]; then
  purge_data
else
  c_warn "Data preserved in /data/medharness/* · use --purge-data to remove"
fi

c_pass "Teardown complete"
