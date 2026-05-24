# syntax=docker/dockerfile:1.7
# T9.3 · desensitize image · ADR-08

ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY mcp/desensitize/requirements.txt /build/requirements.txt

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --target=/wheels -r /build/requirements.txt

FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=unknown
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.title="medharness-desensitize"
LABEL org.opencontainers.image.description="PHI desensitize MCP (AES-256-GCM + FileKeyProvider)"
LABEL org.opencontainers.image.version=$VERSION
LABEL org.opencontainers.image.revision=$GIT_COMMIT
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/charliehzm/medharness"
LABEL org.opencontainers.image.vendor="MedHarness"

RUN groupadd --gid 9000 medharness \
    && useradd --uid 9000 --gid 9000 --no-create-home --shell /usr/sbin/nologin medharness

WORKDIR /app

COPY --from=builder /wheels /usr/local/lib/python3.11/site-packages
COPY --chown=medharness:medharness mcp/desensitize/server_v2.py /app/server_v2.py
COPY --chown=medharness:medharness mcp/desensitize/server.py /app/server.py
COPY --chown=medharness:medharness mcp/desensitize/crypto_envelope.py /app/crypto_envelope.py
COPY --chown=medharness:medharness mcp/desensitize/key_provider/__init__.py /app/key_provider/__init__.py
COPY --chown=medharness:medharness mcp/desensitize/key_provider/interface.py /app/key_provider/interface.py
COPY --chown=medharness:medharness mcp/desensitize/key_provider/file_provider.py /app/key_provider/file_provider.py
COPY --chown=medharness:medharness mcp/desensitize/sql/phi_lookup.sql /app/sql/phi_lookup.sql

USER medharness:medharness

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python server_v2.py health || exit 1

ENTRYPOINT ["python", "server_v2.py"]
CMD ["serve", "--stdio"]
