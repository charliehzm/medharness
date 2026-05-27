#!/usr/bin/env bash
# T12.1 · MedHarness backup · tar.gz + GPG symmetric
# Usage: bash scripts/backup.sh [--out /var/medharness/backups] [--passphrase-file PATH]
set -euo pipefail

readonly DEFAULT_OUT="/var/medharness/backups"
readonly DEFAULT_AUDIT_DIR="/data/medharness/audit"
readonly DEFAULT_KEYSTORE_DIR="/data/medharness/keystore"

OUT_DIR="${MEDHARNESS_BACKUP_OUT:-${DEFAULT_OUT}}"
AUDIT_DIR="${MEDHARNESS_AUDIT_DIR:-${DEFAULT_AUDIT_DIR}}"
KEYSTORE_DIR="${MEDHARNESS_KEYSTORE_DIR:-${DEFAULT_KEYSTORE_DIR}}"
PASSPHRASE_FILE=""
PASSPHRASE_ARG=()

c_pass() { printf "\033[1;32m✅ %s\033[0m\n" "$*"; }
c_warn() { printf "\033[1;33m⚠️  %s\033[0m\n" "$*"; }
c_fail() { printf "\033[1;31m❌ %s\033[0m\n" "$*" >&2; }

usage() {
  cat <<USAGE
Usage: $0 [--out DIR] [--passphrase-file PATH] [--audit-dir DIR] [--keystore-dir DIR]

Env:
  MEDHARNESS_BACKUP_PASSPHRASE  GPG symmetric passphrase
  MEDHARNESS_BACKUP_OUT         Backup output directory (default: ${DEFAULT_OUT})
  MEDHARNESS_AUDIT_DIR          Audit volume path (default: ${DEFAULT_AUDIT_DIR})
  MEDHARNESS_KEYSTORE_DIR       Keystore volume path (default: ${DEFAULT_KEYSTORE_DIR})

Backup contents:
  audit volume + keystore volume only.
  v0.5.0 performs full backups only.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT_DIR="${2:-}"
      shift 2
      ;;
    --passphrase-file)
      PASSPHRASE_FILE="${2:-}"
      shift 2
      ;;
    --audit-dir)
      AUDIT_DIR="${2:-}"
      shift 2
      ;;
    --keystore-dir)
      KEYSTORE_DIR="${2:-}"
      shift 2
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

if [[ -z "${OUT_DIR}" || -z "${AUDIT_DIR}" || -z "${KEYSTORE_DIR}" ]]; then
  c_fail "--out, --audit-dir, and --keystore-dir require non-empty values"
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
  c_fail "passphrase not provided · use MEDHARNESS_BACKUP_PASSPHRASE env or --passphrase-file"
  exit 6
fi

if [[ ! -d "${AUDIT_DIR}" ]]; then
  c_fail "audit dir missing: ${AUDIT_DIR}"
  exit 2
fi

if [[ ! -d "${KEYSTORE_DIR}" ]]; then
  c_fail "keystore dir missing: ${KEYSTORE_DIR}"
  exit 2
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
  exit 4
fi

mkdir -p "${OUT_DIR}"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_BASE="${OUT_DIR}/medharness-backup-${TIMESTAMP}.tar.gz.gpg"
SHA256_FILE="${BACKUP_BASE}.sha256"

c_warn "Backup contents: ${AUDIT_DIR} + ${KEYSTORE_DIR}"
c_warn "Excluded: ClickHouse data, TLS certs, Docker images, TLS_CERT_DIR"
c_warn "Output: ${BACKUP_BASE}"

set +e
tar -czf - \
  -C "$(dirname "${AUDIT_DIR}")" "$(basename "${AUDIT_DIR}")" \
  -C "$(dirname "${KEYSTORE_DIR}")" "$(basename "${KEYSTORE_DIR}")" \
  2>/dev/null \
  | gpg --batch --yes --pinentry-mode loopback --symmetric --cipher-algo AES256 \
  "${PASSPHRASE_ARG[@]}" \
  --output "${BACKUP_BASE}"
pipeline_status=("${PIPESTATUS[@]}")
set -e

if ((pipeline_status[0] != 0)); then
  rm -f "${BACKUP_BASE}"
  c_fail "tar archive failed"
  exit 4
fi

if ((pipeline_status[1] != 0)); then
  rm -f "${BACKUP_BASE}"
  c_fail "gpg encrypt failed"
  exit 3
fi

if command -v sha256sum >/dev/null 2>&1; then
  (cd "${OUT_DIR}" && sha256sum "$(basename "${BACKUP_BASE}")" >"$(basename "${SHA256_FILE}")")
else
  (cd "${OUT_DIR}" && shasum -a 256 "$(basename "${BACKUP_BASE}")" >"$(basename "${SHA256_FILE}")")
fi

SIZE="$(du -h "${BACKUP_BASE}" | cut -f1)"
c_pass "Backup complete: ${BACKUP_BASE} (${SIZE})"
c_pass "Checksum: ${SHA256_FILE}"
