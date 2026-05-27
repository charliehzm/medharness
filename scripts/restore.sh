#!/usr/bin/env bash
# T12.1 · MedHarness restore · GPG decrypt + tar extract + verify
# Usage: bash scripts/restore.sh --backup PATH [--passphrase-file PATH] [--target-prefix /data/medharness]
set -euo pipefail

readonly DEFAULT_TARGET_PREFIX="/data/medharness"

BACKUP=""
TARGET_PREFIX="${MEDHARNESS_RESTORE_TARGET:-${DEFAULT_TARGET_PREFIX}}"
PASSPHRASE_FILE=""
SKIP_VERIFY=""
PASSPHRASE_ARG=()

c_pass() { printf "\033[1;32m✅ %s\033[0m\n" "$*"; }
c_warn() { printf "\033[1;33m⚠️  %s\033[0m\n" "$*"; }
c_fail() { printf "\033[1;31m❌ %s\033[0m\n" "$*" >&2; }

usage() {
  cat <<USAGE
Usage: $0 --backup PATH [--passphrase-file PATH] [--target-prefix DIR] [--skip-verify]

Env:
  MEDHARNESS_BACKUP_PASSPHRASE  GPG symmetric passphrase
  MEDHARNESS_RESTORE_TARGET     Restore target prefix (default: ${DEFAULT_TARGET_PREFIX})

Restore:
  verifies .sha256 when present, decrypts tar.gz.gpg, extracts audit + keystore,
  and runs scripts/verify-hashchain.sh when audit/audit_log_export.jsonl exists.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup)
      BACKUP="${2:-}"
      shift 2
      ;;
    --target-prefix)
      TARGET_PREFIX="${2:-}"
      shift 2
      ;;
    --passphrase-file)
      PASSPHRASE_FILE="${2:-}"
      shift 2
      ;;
    --skip-verify)
      SKIP_VERIFY="1"
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

if [[ -z "${BACKUP}" ]]; then
  c_fail "--backup required"
  exit 2
fi

if [[ -z "${TARGET_PREFIX}" ]]; then
  c_fail "--target-prefix requires a non-empty value"
  exit 2
fi

if [[ ! -f "${BACKUP}" ]]; then
  c_fail "backup file not found: ${BACKUP}"
  exit 2
fi

if [[ -n "${PASSPHRASE_FILE}" ]]; then
  if [[ ! -f "${PASSPHRASE_FILE}" ]]; then
    c_fail "passphrase file not found: ${PASSPHRASE_FILE}"
    exit 6
  fi
  PASSPHRASE_ARG=(--passphrase-file "${PASSPHRASE_FILE}")
elif [[ -n "${MEDHARNESS_BACKUP_PASSPHRASE:-}" ]]; then
  PASSPHRASE_ARG=(--passphrase "${MEDHARNESS_BACKUP_PASSPHRASE}")
else
  c_fail "passphrase required · use MEDHARNESS_BACKUP_PASSPHRASE env or --passphrase-file"
  exit 6
fi

command -v gpg >/dev/null 2>&1 || {
  c_fail "gpg not installed"
  exit 3
}
command -v tar >/dev/null 2>&1 || {
  c_fail "tar not installed"
  exit 4
}
if ! command -v sha256sum >/dev/null 2>&1 && ! command -v shasum >/dev/null 2>&1; then
  c_fail "sha256sum/shasum not installed"
  exit 5
fi

SHA256_FILE="${BACKUP}.sha256"
if [[ -f "${SHA256_FILE}" ]]; then
  c_warn "Verifying sha256..."
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$(dirname "${BACKUP}")" && sha256sum -c "$(basename "${SHA256_FILE}")") || {
      c_fail "sha256 verify failed"
      exit 5
    }
  else
    EXPECTED="$(cut -d' ' -f1 "${SHA256_FILE}")"
    ACTUAL="$(shasum -a 256 "${BACKUP}" | cut -d' ' -f1)"
    if [[ "${EXPECTED}" != "${ACTUAL}" ]]; then
      c_fail "sha256 mismatch"
      exit 5
    fi
  fi
  c_pass "sha256 OK"
else
  c_warn ".sha256 file missing · skipping checksum"
fi

mkdir -p "${TARGET_PREFIX}"

c_warn "Restoring to: ${TARGET_PREFIX}"

set +e
gpg --batch --yes --pinentry-mode loopback --decrypt \
  "${PASSPHRASE_ARG[@]}" \
  --output - \
  "${BACKUP}" \
  | tar -xzf - -C "${TARGET_PREFIX}"
pipeline_status=("${PIPESTATUS[@]}")
set -e

if ((pipeline_status[0] != 0)); then
  c_fail "gpg decrypt failed"
  exit 3
fi

if ((pipeline_status[1] != 0)); then
  c_fail "tar extract failed"
  exit 4
fi

c_pass "Restore complete"

if [[ -z "${SKIP_VERIFY}" ]]; then
  HASHCHAIN_SCRIPT="$(cd "$(dirname "$0")" && pwd)/verify-hashchain.sh"
  AUDIT_EXPORT="${TARGET_PREFIX}/audit/audit_log_export.jsonl"
  if [[ -f "${HASHCHAIN_SCRIPT}" && -f "${AUDIT_EXPORT}" ]]; then
    c_warn "Verifying restored audit hashchain..."
    bash "${HASHCHAIN_SCRIPT}" "${AUDIT_EXPORT}" || {
      c_fail "hashchain verify failed"
      exit 5
    }
    c_pass "Hashchain verified"
  else
    c_warn "Skipping hashchain verify (export not found · OK for fresh restore)"
  fi
fi

c_pass "Restore done"
