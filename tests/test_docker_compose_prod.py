from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy" / "docker-compose.prod.yml"
NGINX_CONF = ROOT / "deploy" / "nginx" / "medharness.conf"
ENV_EXAMPLE = ROOT / "deploy" / ".env.production.example"

ALL_SERVICES = (
    "phi-detector",
    "desensitize",
    "model-router",
    "audit-log",
    "ci-trigger",
    "internal-kb",
    "pm-bridge",
    "vector-db",
    "new-api",
    "clickhouse",
    "redis",
    "nginx",
)

MCP_SERVICES = (
    "phi-detector",
    "desensitize",
    "model-router",
    "audit-log",
    "ci-trigger",
    "internal-kb",
    "pm-bridge",
    "vector-db",
)
PRODUCTION_SERVICES = ("phi-detector", "desensitize", "model-router", "audit-log")
STUB_SERVICES = ("ci-trigger", "internal-kb", "pm-bridge", "vector-db")

LIMITS = {
    "phi-detector": {"memory": "1024M", "cpus": "1.0"},
    "desensitize": {"memory": "512M", "cpus": "0.5"},
    "model-router": {"memory": "512M", "cpus": "0.5"},
    "audit-log": {"memory": "512M", "cpus": "0.5"},
    "ci-trigger": {"memory": "256M", "cpus": "0.25"},
    "internal-kb": {"memory": "256M", "cpus": "0.25"},
    "pm-bridge": {"memory": "256M", "cpus": "0.25"},
    "vector-db": {"memory": "256M", "cpus": "0.25"},
    "new-api": {"memory": "1024M", "cpus": "1.0"},
    "clickhouse": {"memory": "2048M", "cpus": "1.0"},
    "redis": {"memory": "512M", "cpus": "0.5"},
    "nginx": {"memory": "128M", "cpus": "0.25"},
}


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _service(name: str) -> dict:
    return _compose()["services"][name]


def test_compose_file_exists_and_yaml_parseable() -> None:
    assert COMPOSE.exists()
    data = _compose()
    assert "services" in data
    assert "networks" in data


def test_no_version_top_level_field() -> None:
    data = _compose()
    assert "version" not in data


def test_has_phase_a_services() -> None:
    data = _compose()
    assert list(data["services"].keys()) == list(ALL_SERVICES)


def test_only_nginx_publishes_ports() -> None:
    data = _compose()
    for name, service in data["services"].items():
        if name == "nginx":
            assert "ports" in service
        else:
            assert "ports" not in service


def test_medharness_internal_is_internal_only() -> None:
    data = _compose()
    internal = data["networks"]["medharness_internal"]
    assert internal["internal"] is True
    assert internal["name"] == "medharness_internal"


def test_medharness_dmz_is_default_network() -> None:
    data = _compose()
    dmz = data["networks"]["medharness_dmz"]
    assert dmz["driver"] == "bridge"
    assert "internal" not in dmz
    assert dmz["name"] == "medharness_dmz"


def test_all_services_have_resource_limits() -> None:
    data = _compose()
    for name in ALL_SERVICES:
        limits = data["services"][name]["deploy"]["resources"]["limits"]
        assert limits["memory"]
        assert limits["cpus"]


def test_all_services_have_restart_policy() -> None:
    data = _compose()
    for name in ALL_SERVICES:
        assert data["services"][name]["restart"] == "unless-stopped"


def test_all_services_have_healthcheck() -> None:
    data = _compose()
    for name in ALL_SERVICES:
        assert "healthcheck" in data["services"][name]


def test_model_router_depends_on_phi_detector_and_desensitize() -> None:
    depends_on = _service("model-router").get("depends_on", {})
    assert depends_on["phi-detector"]["condition"] == "service_healthy"
    assert depends_on["desensitize"]["condition"] == "service_healthy"


def test_nginx_depends_on_model_router_and_audit_log() -> None:
    depends_on = _service("nginx").get("depends_on", {})
    assert depends_on["model-router"]["condition"] == "service_healthy"
    assert depends_on["audit-log"]["condition"] == "service_healthy"


def test_storage_dependent_services_wait_for_storage_health() -> None:
    audit_depends_on = _service("audit-log").get("depends_on", {})
    desensitize_depends_on = _service("desensitize").get("depends_on", {})
    new_api_depends_on = _service("new-api").get("depends_on", {})

    assert audit_depends_on["clickhouse"]["condition"] == "service_healthy"
    assert desensitize_depends_on["clickhouse"]["condition"] == "service_healthy"
    assert new_api_depends_on["redis"]["condition"] == "service_healthy"


def test_host_volume_paths_under_data_medharness() -> None:
    data = _compose()
    audit_mounts = data["services"]["audit-log"]["volumes"]
    desensitize_mounts = data["services"]["desensitize"]["volumes"]
    assert any("/data/medharness/audit" in str(item) for item in audit_mounts)
    assert any("/data/medharness/keystore" in str(item) for item in desensitize_mounts)
    for name in ("audit-log", "desensitize"):
        for volume in data["services"][name].get("volumes", []):
            assert str(volume).startswith("/data/medharness/")


def test_all_services_use_version_env_var() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    for name in MCP_SERVICES:
        assert f"image: medharness/mcp-{name}:${{VERSION}}" in text
    assert "image: medharness/new-api:${VERSION}" in text
    assert "image: clickhouse/clickhouse-server:24" in text
    assert "image: redis:7-alpine" in text


def test_resource_limits_match_adr_09() -> None:
    data = _compose()
    for name, expected in LIMITS.items():
        limits = data["services"][name]["deploy"]["resources"]["limits"]
        assert limits["memory"] == expected["memory"]
        assert str(limits["cpus"]) == expected["cpus"]


def test_nginx_conf_exists_with_upstream_blocks() -> None:
    text = NGINX_CONF.read_text(encoding="utf-8")
    assert "upstream model_router" in text
    assert "upstream audit_log" in text


def test_env_production_example_has_version_placeholder() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "VERSION=0.5.0-edge" in text
    assert "Copy to .env.production" in text
