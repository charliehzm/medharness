#!/usr/bin/env bash
# T4.6 · WORM setup · chattr +a on _audit_log / audit-export / audit-backup
set -euo pipefail

readonly DEFAULT_BASE="/data/medharness/audit"
readonly BASE_DIR="${MEDHARNESS_AUDIT_BASE:-${DEFAULT_BASE}}"
readonly DIRS=(
  "${BASE_DIR}/_audit_log"
  "${BASE_DIR}/audit-export"
  "${BASE_DIR}/audit-backup"
)
readonly OS_NAME="$(uname -s)"

c_pass() { printf "\033[1;32m✅ %s\033[0m\n" "$*"; }
c_warn() { printf "\033[1;33m⚠️  %s\033[0m\n" "$*"; }
c_fail() { printf "\033[1;31m❌ %s\033[0m\n" "$*" >&2; }

detect_os() {
  case "${OS_NAME}" in
    Linux*) echo "linux" ;;
    Darwin*) echo "macos" ;;
    *) echo "unsupported" ;;
  esac
}

apply_chattr_linux() {
  local dir="$1"
  mkdir -p "${dir}"
  if ! command -v chattr >/dev/null 2>&1; then
    c_fail "chattr not found · install e2fsprogs"
    exit 2
  fi
  sudo chattr +a "${dir}" || {
    c_fail "chattr +a failed for ${dir}"
    exit 3
  }
  c_pass "chattr +a applied to ${dir}"
}

verify_lsattr_linux() {
  local dir="$1"
  if ! command -v lsattr >/dev/null 2>&1; then
    c_fail "lsattr not found · cannot verify"
    exit 4
  fi
  local attrs
  attrs="$(lsattr -d "${dir}" 2>/dev/null | awk '{print $1}')"
  if [[ "${attrs}" != *a* ]]; then
    c_fail "${dir} append-only flag NOT set (lsattr: ${attrs})"
    exit 5
  fi
  c_pass "verified append-only on ${dir} (lsattr: ${attrs})"
}

skip_macos() {
  local dir="$1"
  mkdir -p "${dir}"
  if command -v lsattr >/dev/null 2>&1; then
    c_warn "macOS detected · skipping real chattr · lsattr available (informational only)"
  else
    c_warn "macOS detected · skipping real chattr · lsattr unavailable (production deploy must be Linux)"
  fi
  c_pass "macOS skip path · ${dir} prepared"
}

main() {
  local os
  os="$(detect_os)"

  echo "→ setup-worm · base_dir=${BASE_DIR} · os=${os}"

  if [[ "${os}" == "unsupported" ]]; then
    c_fail "unsupported OS: ${OS_NAME} · only Linux + macOS"
    exit 1
  fi

  for dir in "${DIRS[@]}"; do
    if [[ "${os}" == "linux" ]]; then
      apply_chattr_linux "${dir}"
      verify_lsattr_linux "${dir}"
    else
      skip_macos "${dir}"
    fi
  done

  c_pass "WORM setup complete · 3 directories under ${BASE_DIR}"
}

main "$@"
