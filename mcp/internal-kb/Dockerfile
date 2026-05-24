# syntax=docker/dockerfile:1.7
# T9.6 · internal-kb stub image · ADR-08 · M3 placeholder
ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /build
COPY mcp/internal-kb/requirements.txt /build/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --target=/wheels -r /build/requirements.txt || true

FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=unknown
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.title="medharness-internal-kb"
LABEL org.opencontainers.image.description="STUB · v0.5.0-edge placeholder · internal knowledge base · production in M3"
LABEL org.opencontainers.image.version=$VERSION
LABEL org.opencontainers.image.revision=$GIT_COMMIT
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/charliehzm/medharness"
LABEL org.opencontainers.image.vendor="MedHarness"

RUN groupadd --gid 9000 medharness \
    && useradd --uid 9000 --gid 9000 --no-create-home --shell /usr/sbin/nologin medharness

WORKDIR /app

COPY --from=builder /wheels /usr/local/lib/python3.11/site-packages
COPY --chown=medharness:medharness mcp/internal-kb/server.py /app/server.py

USER medharness:medharness

# HEALTHCHECK import smoke · stub does not call placeholder behavior.
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import server" || exit 1

ENTRYPOINT ["python", "server.py"]
CMD ["serve", "--stdio"]
