# syntax=docker/dockerfile:1.7
# mcp-outbound-safety image · §D.1 post-call response safety (rules + async NLP
# catch). stdlib-only, so a single slim stage (no wheel build).
ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=unknown
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.title="medharness-outbound-safety"
LABEL org.opencontainers.image.description="Outbound response safety (rules + async NLP catch, 0-PHI)"
LABEL org.opencontainers.image.version=$VERSION
LABEL org.opencontainers.image.revision=$GIT_COMMIT
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/charliehzm/medharness"
LABEL org.opencontainers.image.vendor="MedHarness"

RUN groupadd --gid 9000 medharness \
    && useradd --uid 9000 --gid 9000 --no-create-home --shell /usr/sbin/nologin medharness

WORKDIR /app

COPY --chown=medharness:medharness mcp/outbound-safety/server_v2.py /app/server_v2.py
COPY --chown=medharness:medharness mcp/outbound-safety/classifier.py /app/classifier.py
COPY --chown=medharness:medharness mcp/outbound-safety/async_catch.py /app/async_catch.py

USER medharness:medharness

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python server_v2.py health || exit 1

ENTRYPOINT ["python", "server_v2.py"]
CMD ["serve"]
