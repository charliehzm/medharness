from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GEN_TLS = ROOT / "scripts" / "gen-tls.sh"
CHECK_EXPIRY = ROOT / "scripts" / "check-cert-expiry.sh"
NGINX_CONF = ROOT / "deploy" / "nginx" / "medharness.conf"


def _run(cmd: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False
    )


def _run_gen_tls(out_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run(["bash", str(GEN_TLS), "--out", str(out_dir), *args], timeout=45)


def _openssl_available() -> bool:
    return _run(["openssl", "version"]).returncode == 0


def _cert_subject(cert_path: Path) -> str:
    proc = _run(["openssl", "x509", "-in", str(cert_path), "-noout", "-subject"])
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _generate_test_cert(out_dir: Path, *, days: int, cn: str = "threshold.test") -> Path:
    key_path = out_dir / "key.pem"
    cert_path = out_dir / "cert.pem"
    config_path = out_dir / "openssl.cnf"
    config_path.write_text(
        f"""[req]
prompt = no
distinguished_name = req_distinguished_name
x509_extensions = v3_req

[req_distinguished_name]
CN = {cn}

[v3_req]
subjectAltName = DNS:{cn}
""",
        encoding="utf-8",
    )

    proc = _run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-days",
            str(days),
            "-config",
            str(config_path),
            "-extensions",
            "v3_req",
        ],
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return cert_path


@pytest.mark.skipif(not _openssl_available(), reason="openssl is required for TLS script tests")
def test_gen_tls_script_exists_and_executable() -> None:
    assert GEN_TLS.exists()
    assert os.access(GEN_TLS, os.X_OK)
    assert GEN_TLS.read_text(encoding="utf-8").splitlines()[0].startswith("#!")


def test_gen_tls_uses_strict_mode() -> None:
    assert "set -euo pipefail" in GEN_TLS.read_text(encoding="utf-8")


@pytest.mark.skipif(not _openssl_available(), reason="openssl is required for TLS script tests")
def test_gen_tls_generates_self_signed_cert(tmp_path: Path) -> None:
    proc = _run_gen_tls(tmp_path)

    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "cert.pem").exists()
    assert (tmp_path / "key.pem").exists()
    assert "self-signed cert generated" in proc.stdout


@pytest.mark.skipif(not _openssl_available(), reason="openssl is required for TLS script tests")
def test_gen_tls_cert_has_default_subject_cn(tmp_path: Path) -> None:
    proc = _run_gen_tls(tmp_path)
    subject = _cert_subject(tmp_path / "cert.pem")

    assert proc.returncode == 0, proc.stderr
    assert "CN=medharness.local" in subject or "CN = medharness.local" in subject


@pytest.mark.skipif(not _openssl_available(), reason="openssl is required for TLS script tests")
def test_gen_tls_custom_cn_via_arg(tmp_path: Path) -> None:
    proc = _run_gen_tls(tmp_path, "--cn", "clinic.example")
    subject = _cert_subject(tmp_path / "cert.pem")

    assert proc.returncode == 0, proc.stderr
    assert "CN=clinic.example" in subject or "CN = clinic.example" in subject


@pytest.mark.skipif(not _openssl_available(), reason="openssl is required for TLS script tests")
def test_gen_tls_skips_if_existing(tmp_path: Path) -> None:
    first = _run_gen_tls(tmp_path)
    first_mtime = (tmp_path / "cert.pem").stat().st_mtime_ns
    second = _run_gen_tls(tmp_path)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "existing cert/key found" in second.stdout
    assert (tmp_path / "cert.pem").stat().st_mtime_ns == first_mtime


@pytest.mark.skipif(not _openssl_available(), reason="openssl is required for TLS script tests")
def test_gen_tls_key_file_permissions_600(tmp_path: Path) -> None:
    proc = _run_gen_tls(tmp_path)

    assert proc.returncode == 0, proc.stderr
    mode = stat.S_IMODE((tmp_path / "key.pem").stat().st_mode)
    assert mode == 0o600


def test_check_expiry_script_exists_and_executable() -> None:
    assert CHECK_EXPIRY.exists()
    assert os.access(CHECK_EXPIRY, os.X_OK)
    assert CHECK_EXPIRY.read_text(encoding="utf-8").splitlines()[0].startswith("#!")


def test_check_expiry_uses_strict_mode() -> None:
    assert "set -euo pipefail" in CHECK_EXPIRY.read_text(encoding="utf-8")


@pytest.mark.skipif(not _openssl_available(), reason="openssl is required for TLS script tests")
def test_check_expiry_returns_zero_for_valid_cert(tmp_path: Path) -> None:
    gen = _run_gen_tls(tmp_path)
    proc = _run(["bash", str(CHECK_EXPIRY), "--cert", str(tmp_path / "cert.pem")])

    assert gen.returncode == 0, gen.stderr
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_check_expiry_returns_three_for_missing_cert(tmp_path: Path) -> None:
    proc = _run(["bash", str(CHECK_EXPIRY), "--cert", str(tmp_path / "missing.pem")])

    assert proc.returncode == 3
    assert "cert file not found" in proc.stderr


@pytest.mark.skipif(not _openssl_available(), reason="openssl is required for TLS script tests")
def test_check_expiry_warns_for_30_day_threshold(tmp_path: Path) -> None:
    cert = _generate_test_cert(tmp_path, days=25)
    proc = _run(["bash", str(CHECK_EXPIRY), "--cert", str(cert)])

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "WARN" in proc.stdout


@pytest.mark.skipif(not _openssl_available(), reason="openssl is required for TLS script tests")
def test_check_expiry_critical_for_7_day_threshold(tmp_path: Path) -> None:
    cert = _generate_test_cert(tmp_path, days=5)
    proc = _run(["bash", str(CHECK_EXPIRY), "--cert", str(cert)])

    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "CRITICAL" in proc.stderr


def test_nginx_conf_has_443_server_block() -> None:
    text = NGINX_CONF.read_text(encoding="utf-8")

    assert "listen 443 ssl;" in text
    assert "ssl_certificate     /etc/medharness/tls/cert.pem;" in text
    assert "ssl_certificate_key /etc/medharness/tls/key.pem;" in text


def test_nginx_conf_uses_tls_1_2_and_1_3_only() -> None:
    text = NGINX_CONF.read_text(encoding="utf-8")
    protocols_line = next(line.strip() for line in text.splitlines() if "ssl_protocols" in line)

    assert protocols_line == "ssl_protocols TLSv1.2 TLSv1.3;"
    assert "TLSv1 " not in protocols_line
    assert "TLSv1.1" not in protocols_line


def test_nginx_conf_has_hsts_max_age_31536000_with_subdomains() -> None:
    text = NGINX_CONF.read_text(encoding="utf-8")

    assert 'Strict-Transport-Security "max-age=31536000; includeSubDomains" always' in text


def test_nginx_conf_redirects_http_to_https() -> None:
    text = NGINX_CONF.read_text(encoding="utf-8")

    assert "listen 80;" in text
    assert "location /health" in text
    assert "return 301 https://$host$request_uri;" in text


def test_nginx_conf_uses_mozilla_intermediate_ciphers() -> None:
    text = NGINX_CONF.read_text(encoding="utf-8")

    assert "ECDHE-ECDSA-AES128-GCM-SHA256" in text
    assert "ECDHE-RSA-AES256-GCM-SHA384" in text
    assert "CHACHA20-POLY1305" in text


def test_nginx_conf_has_security_headers() -> None:
    text = NGINX_CONF.read_text(encoding="utf-8")

    assert 'X-Content-Type-Options "nosniff" always' in text
    assert 'X-Frame-Options "DENY" always' in text
    assert 'X-XSS-Protection "1; mode=block" always' in text
