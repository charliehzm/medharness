# syntax=docker/dockerfile:1.7
# mcp-prompt-injection-scan image · §D.1 prompt-injection scan. stdlib-only, so a
# single slim stage (no wheel build).
ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=unknown
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.title="medharness-prompt-injection-scan"
LABEL org.opencontainers.image.description="Prompt-injection scan (rules, quarantine, 0-PHI)"
LABEL org.opencontainers.image.version=$VERSION
LABEL org.opencontainers.image.revision=$GIT_COMMIT
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/charliehzm/medharness"
LABEL org.opencontainers.image.vendor="MedHarness"

RUN groupadd --gid 9000 medharness \
    && useradd --uid 9000 --gid 9000 --no-create-home --shell /usr/sbin/nologin medharness

WORKDIR /app

COPY --chown=medharness:medharness mcp/prompt-injection-scan/detector.py /app/detector.py

USER medharness:medharness

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python detector.py health || exit 1

ENTRYPOINT ["python", "detector.py"]
CMD ["serve"]
