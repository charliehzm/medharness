#!/usr/bin/env bash
# T11 · MedHarness self-signed TLS cert generator
# Usage: bash scripts/gen-tls.sh [--cn medharness.local] [--days 365] [--out /etc/medharness/tls]
set -euo pipefail

readonly DEFAULT_CN="${MEDHARNESS_TLS_CN:-medharness.local}"
readonly DEFAULT_DAYS=365
readonly DEFAULT_OUT="${MEDHARNESS_TLS_OUT:-/etc/medharness/tls}"

CN="${DEFAULT_CN}"
DAYS="${DEFAULT_DAYS}"
OUT_DIR="${DEFAULT_OUT}"

c_pass() { printf "\033[1;32m✅ %s\033[0m\n" "$*"; }
c_warn() { printf "\033[1;33m⚠️  %s\033[0m\n" "$*"; }
c_fail() { printf "\033[1;31m❌ %s\033[0m\n" "$*" >&2; }

usage() {
  cat <<USAGE
Usage: $0 [--cn CN] [--days N] [--out DIR]

Defaults:
  CN:   ${DEFAULT_CN}
  days: ${DEFAULT_DAYS}
  out:  ${DEFAULT_OUT}
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cn)
      CN="${2:-}"
      shift 2
      ;;
    --days)
      DAYS="${2:-}"
      shift 2
      ;;
    --out)
      OUT_DIR="${2:-}"
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

if [[ -z "${CN}" || -z "${DAYS}" || -z "${OUT_DIR}" ]]; then
  c_fail "--cn, --days, and --out require non-empty values"
  exit 2
fi

if ! [[ "${DAYS}" =~ ^[0-9]+$ ]] || ((DAYS <= 0)); then
  c_fail "--days must be a positive integer"
  exit 2
fi

c_warn "Generating self-signed cert · DEMO ONLY · production must BYO cert (ADR-06)"

if ! command -v openssl >/dev/null 2>&1; then
  c_fail "openssl not found · install openssl"
  exit 3
fi

mkdir -p "${OUT_DIR}"
chmod 700 "${OUT_DIR}"

CERT_PATH="${OUT_DIR}/cert.pem"
KEY_PATH="${OUT_DIR}/key.pem"
OPENSSL_CONFIG="$(mktemp)"
trap 'rm -f "${OPENSSL_CONFIG}"' EXIT

if [[ -f "${CERT_PATH}" || -f "${KEY_PATH}" ]]; then
  c_warn "existing cert/key found at ${OUT_DIR} · skipping (delete manually to regenerate)"
  exit 0
fi

cat >"${OPENSSL_CONFIG}" <<EOF
[req]
prompt = no
distinguished_name = req_distinguished_name
x509_extensions = v3_req

[req_distinguished_name]
CN = ${CN}
O = MedHarness Self-Signed
C = CN

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${CN}
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF

openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout "${KEY_PATH}" \
  -out "${CERT_PATH}" \
  -days "${DAYS}" \
  -config "${OPENSSL_CONFIG}" \
  -extensions v3_req \
  2>/dev/null || {
    c_fail "openssl req failed"
    exit 4
  }

chmod 644 "${CERT_PATH}"
chmod 600 "${KEY_PATH}"

c_pass "self-signed cert generated"
c_pass "  cert: ${CERT_PATH}"
c_pass "  key:  ${KEY_PATH}"
c_pass "  CN:   ${CN}"
c_pass "  expires: $(openssl x509 -in "${CERT_PATH}" -noout -enddate | cut -d= -f2)"
c_warn "Production deployment: replace with BYO CA-signed cert (ADR-06)"
