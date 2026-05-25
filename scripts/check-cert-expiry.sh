#!/usr/bin/env bash
# T11 · MedHarness TLS cert expiry checker
# Usage: bash scripts/check-cert-expiry.sh [--cert /path/to/cert.pem]
# Exit codes: 0=OK · 1=warn (<=30d) · 2=critical (<=7d/expired) · 3=missing/invalid
set -euo pipefail

readonly DEFAULT_CERT="${MEDHARNESS_TLS_CERT:-/etc/medharness/tls/cert.pem}"

CERT="${DEFAULT_CERT}"

c_ok() { printf "\033[1;32m✅ %s\033[0m\n" "$*"; }
c_warn() { printf "\033[1;33m⚠️  %s\033[0m\n" "$*"; }
c_fail() { printf "\033[1;31m❌ %s\033[0m\n" "$*" >&2; }

usage() {
  cat <<USAGE
Usage: $0 [--cert PATH]

Default cert:
  ${DEFAULT_CERT}
USAGE
}

parse_expiry_epoch() {
  local expiry="$1"

  date -j -f "%b %e %T %Y %Z" "${expiry}" +%s 2>/dev/null \
    || date -j -f "%b %d %T %Y %Z" "${expiry}" +%s 2>/dev/null \
    || date -d "${expiry}" +%s 2>/dev/null
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cert)
      CERT="${2:-}"
      shift 2
      ;;
    --help | -h)
      usage
      exit 0
      ;;
    *)
      c_fail "unknown argument: $1"
      usage >&2
      exit 3
      ;;
  esac
done

if [[ -z "${CERT}" ]]; then
  c_fail "--cert requires a non-empty path"
  exit 3
fi

if ! command -v openssl >/dev/null 2>&1; then
  c_fail "openssl not found · install openssl"
  exit 3
fi

if [[ ! -f "${CERT}" ]]; then
  c_fail "cert file not found: ${CERT}"
  exit 3
fi

EXPIRY="$(openssl x509 -in "${CERT}" -noout -enddate 2>/dev/null | cut -d= -f2)"
if [[ -z "${EXPIRY}" ]]; then
  c_fail "failed to parse cert expiry"
  exit 3
fi

EXPIRY_EPOCH="$(parse_expiry_epoch "${EXPIRY}")"
if [[ -z "${EXPIRY_EPOCH}" ]]; then
  c_fail "failed to convert cert expiry date: ${EXPIRY}"
  exit 3
fi

NOW_EPOCH="$(date +%s)"
DAYS_LEFT=$(((EXPIRY_EPOCH - NOW_EPOCH) / 86400))

echo "Cert: ${CERT}"
echo "Expires: ${EXPIRY}"
echo "Days left: ${DAYS_LEFT}"

if ((DAYS_LEFT <= 0)); then
  c_fail "CRITICAL · cert expired ${DAYS_LEFT#-} days ago"
  exit 2
elif ((DAYS_LEFT <= 7)); then
  c_fail "CRITICAL · cert expires in ${DAYS_LEFT} days · immediate renewal required"
  exit 2
elif ((DAYS_LEFT <= 30)); then
  c_warn "WARN · cert expires in ${DAYS_LEFT} days · renewal recommended (ADR-06 30-day threshold)"
  exit 1
else
  c_ok "OK · cert valid for ${DAYS_LEFT} more days"
  exit 0
fi
