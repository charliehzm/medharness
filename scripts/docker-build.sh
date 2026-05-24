#!/usr/bin/env bash
# T9.7 · build single MCP image + non-root + size check
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
readonly DEFAULT_REGISTRY="medharness"
readonly REGISTRY="${MEDHARNESS_DOCKER_REGISTRY:-${DEFAULT_REGISTRY}}"
readonly VERSION_FILE="${VERSION_FILE:-${REPO_ROOT}/VERSION}"
readonly REPORT_DIR="${MEDHARNESS_BUILD_REPORT_DIR:-/tmp/medharness-build}"
readonly AVAILABLE_MCPS="phi-detector desensitize model-router audit-log ci-trigger internal-kb pm-bridge vector-db"

c_pass() { printf "\033[1;32m✅ %s\033[0m\n" "$*"; }
c_warn() { printf "\033[1;33m⚠️  %s\033[0m\n" "$*"; }
c_fail() { printf "\033[1;31m❌ %s\033[0m\n" "$*" >&2; }

usage() {
  cat <<USAGE
Usage: $0 <mcp_name> [--push]
Available MCPs: ${AVAILABLE_MCPS}
Env:
  MEDHARNESS_DOCKER_REGISTRY (default: medharness)
  VERSION_FILE (default: ${REPO_ROOT}/VERSION)
  MEDHARNESS_BUILD_REPORT_DIR (default: /tmp/medharness-build)
USAGE
  exit 2
}

mcp_size_target_mb() {
  case "$1" in
    phi-detector|desensitize|model-router|audit-log)
      echo 500
      ;;
    ci-trigger|internal-kb|pm-bridge|vector-db)
      echo 200
      ;;
    *)
      return 1
      ;;
  esac
}

main() {
  if [[ $# -lt 1 || $# -gt 2 ]]; then
    usage
  fi

  local mcp="$1"
  local push_flag="${2:-}"

  case "${mcp}" in
    phi-detector|desensitize|model-router|audit-log|ci-trigger|internal-kb|pm-bridge|vector-db)
      ;;
    *)
      c_fail "unknown MCP: ${mcp}"
      usage
      ;;
  esac

  if [[ -n "${push_flag}" && "${push_flag}" != "--push" ]]; then
    c_fail "unknown flag: ${push_flag}"
    usage
  fi

  local dockerfile_path="${REPO_ROOT}/mcp/${mcp}/Dockerfile"
  if [[ ! -f "${dockerfile_path}" ]]; then
    c_fail "missing Dockerfile: ${dockerfile_path}"
    exit 3
  fi

  if [[ ! -f "${VERSION_FILE}" ]]; then
    c_fail "missing VERSION file: ${VERSION_FILE}"
    exit 3
  fi

  local version
  version="$(tr -d '\n' < "${VERSION_FILE}")"
  if [[ -z "${version}" ]]; then
    c_fail "empty VERSION file: ${VERSION_FILE}"
    exit 3
  fi

  local git_commit
  git_commit="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo unknown)"

  local TARGET_MB
  TARGET_MB="$(mcp_size_target_mb "${mcp}")" || {
    c_fail "unknown size target for ${mcp}"
    exit 3
  }

  local image_tag="${REGISTRY}/mcp-${mcp}:${version}"
  echo "→ build ${image_tag} (target < ${TARGET_MB}MB)"

  docker build \
    --file "${dockerfile_path}" \
    --tag "${image_tag}" \
    --build-arg "VERSION=${version}" \
    --build-arg "GIT_COMMIT=${git_commit}" \
    "${REPO_ROOT}" || {
      c_fail "docker build failed for ${mcp}"
      exit 4
    }

  local SIZE_BYTES SIZE_MB
  SIZE_BYTES="$(docker image inspect "${image_tag}" --format '{{.Size}}')"
  SIZE_MB=$((SIZE_BYTES / 1024 / 1024))
  echo "→ image size: ${SIZE_MB}MB (target < ${TARGET_MB}MB)"
  if (( SIZE_MB > TARGET_MB )); then
    c_fail "size check failed: ${SIZE_MB}MB > ${TARGET_MB}MB"
    exit 5
  fi

  local uid_output
  uid_output="$(docker run --rm --entrypoint id "${image_tag}" -u 2>/dev/null || echo fail)"
  if [[ "${uid_output}" != "9000" ]]; then
    c_fail "non-root smoke failed: expected UID 9000, got '${uid_output}'"
    exit 6
  fi

  mkdir -p "${REPORT_DIR}"
  cat > "${REPORT_DIR}/${mcp}.json" <<JSON
{
  "mcp": "${mcp}",
  "image": "${image_tag}",
  "size_mb": ${SIZE_MB},
  "size_target_mb": ${TARGET_MB},
  "version": "${version}",
  "git_commit": "${git_commit}",
  "uid": "${uid_output}"
}
JSON

  if [[ "${push_flag}" == "--push" ]]; then
    echo "→ docker push ${image_tag}"
    docker push "${image_tag}" || {
      c_fail "docker push failed"
      exit 7
    }
  fi

  c_pass "${mcp} · ${SIZE_MB}MB · non-root UID 9000"
  c_pass "${mcp} build complete · report: ${REPORT_DIR}/${mcp}.json"
}

main "$@"
