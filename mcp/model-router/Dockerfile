# syntax=docker/dockerfile:1.7
# T9.4 · model-router image · ADR-08

ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /build

COPY mcp/model-router/requirements.txt /build/requirements.txt

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --target=/wheels -r /build/requirements.txt

FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=unknown
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.title="medharness-model-router"
LABEL org.opencontainers.image.description="LLM routing gate (allowlist + heterogeneity + circuit breaker)"
LABEL org.opencontainers.image.version=$VERSION
LABEL org.opencontainers.image.revision=$GIT_COMMIT
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/charliehzm/medharness"
LABEL org.opencontainers.image.vendor="MedHarness"

RUN groupadd --gid 9000 medharness \
    && useradd --uid 9000 --gid 9000 --no-create-home --shell /usr/sbin/nologin medharness

WORKDIR /app

COPY --from=builder /wheels /usr/local/lib/python3.11/site-packages
COPY --chown=medharness:medharness mcp/model-router/server_v2.py /app/server_v2.py
COPY --chown=medharness:medharness mcp/model-router/allowlist.py /app/allowlist.py
COPY --chown=medharness:medharness mcp/model-router/heterogeneity.py /app/heterogeneity.py
COPY --chown=medharness:medharness mcp/model-router/limits.py /app/limits.py
COPY --chown=medharness:medharness mcp/model-router/policy.py /app/policy.py
COPY --chown=medharness:medharness mcp/model-router/vendor_families.py /app/vendor_families.py
COPY --chown=medharness:medharness mcp/model-router/vendor_families.yml /app/vendor_families.yml

USER medharness:medharness

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python server_v2.py health || exit 1

ENTRYPOINT ["python", "server_v2.py"]
CMD ["serve", "--stdio"]
