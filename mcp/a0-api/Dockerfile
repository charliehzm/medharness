# syntax=docker/dockerfile:1.7
# A0 read-only aggregation API (Console BFF) image · ADR-18 control-plane.
# Serves the FROZEN /api/v1/* contract behind the nginx egress allowlist
# (/api/v1/ -> a0-api:9000). Field-whitelist + assert_no_phi => 0-PHI by design.

ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY mcp/a0-api/requirements.txt /build/requirements.txt

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --target=/wheels -r /build/requirements.txt

FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=unknown
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.title="medharness-a0-api"
LABEL org.opencontainers.image.description="A0 read-only aggregation API (Console BFF, field-whitelist 0-PHI)"
LABEL org.opencontainers.image.version=$VERSION
LABEL org.opencontainers.image.revision=$GIT_COMMIT
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/charliehzm/medharness"
LABEL org.opencontainers.image.vendor="MedHarness"

RUN groupadd --gid 9000 medharness \
    && useradd --uid 9000 --gid 9000 --no-create-home --shell /usr/sbin/nologin medharness

WORKDIR /app

COPY --from=builder /wheels /usr/local/lib/python3.11/site-packages
COPY --chown=medharness:medharness mcp/a0-api/app.py /app/app.py
COPY --chown=medharness:medharness mcp/a0-api/serializers.py /app/serializers.py

USER medharness:medharness

EXPOSE 9000

# Health on /health (not under /api/v1); the egress allowlist exposes only
# /api/v1/* externally, so /health stays internal for the container probe.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9000/health', timeout=5).status==200 else 1)" || exit 1

# Run on 9000 to match the nginx a0-api:9000 upstream (overrides A0's 8010 default).
ENTRYPOINT ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
