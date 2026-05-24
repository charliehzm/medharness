# syntax=docker/dockerfile:1.7
# T9.5 · audit-log image · ADR-08 · v0.5.0 mock-only

ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /build

COPY mcp/audit-log/requirements.txt /build/requirements.txt

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --target=/wheels -r /build/requirements.txt || true

FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=unknown
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.title="medharness-audit-log"
LABEL org.opencontainers.image.description="Append-only audit log MCP (WORM + hashchain + fallback; v0.5.0 mock-only)"
LABEL org.opencontainers.image.version=$VERSION
LABEL org.opencontainers.image.revision=$GIT_COMMIT
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/charliehzm/medharness"
LABEL org.opencontainers.image.vendor="MedHarness"

RUN groupadd --gid 9000 medharness \
    && useradd --uid 9000 --gid 9000 --no-create-home --shell /usr/sbin/nologin medharness

WORKDIR /app

COPY --from=builder /wheels /usr/local/lib/python3.11/site-packages
COPY --chown=medharness:medharness mcp/audit-log/server_v2.py /app/server_v2.py
COPY --chown=medharness:medharness mcp/audit-log/clickhouse_writer.py /app/clickhouse_writer.py
COPY --chown=medharness:medharness mcp/audit-log/fallback_writer.py /app/fallback_writer.py
COPY --chown=medharness:medharness mcp/audit-log/hashchain.py /app/hashchain.py
COPY --chown=medharness:medharness mcp/audit-log/sql/audit_log.sql /app/sql/audit_log.sql

USER medharness:medharness

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "from server_v2 import AuditLogServerV2" || exit 1

ENTRYPOINT ["python"]
CMD ["-c", "import time; print('audit-log v0.5.0 ready; use AuditLogServerV2 class; v0.6+ adds CLI'); time.sleep(86400)"]
