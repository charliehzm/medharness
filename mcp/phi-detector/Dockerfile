# syntax=docker/dockerfile:1.7
# T9.2 · phi-detector image · ADR-08

ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY mcp/phi-detector/requirements.txt /build/requirements.txt

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --target=/wheels -r /build/requirements.txt

FROM python:${PYTHON_VERSION}-slim AS runtime

ARG VERSION=unknown
ARG GIT_COMMIT=unknown

LABEL org.opencontainers.image.title="medharness-phi-detector"
LABEL org.opencontainers.image.description="Medical PHI detector (Presidio + CN recognizers + RegexOnlyNlpEngine)"
LABEL org.opencontainers.image.version=$VERSION
LABEL org.opencontainers.image.revision=$GIT_COMMIT
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/charliehzm/medharness"
LABEL org.opencontainers.image.vendor="MedHarness"

RUN groupadd --gid 9000 medharness \
    && useradd --uid 9000 --gid 9000 --no-create-home --shell /usr/sbin/nologin medharness

WORKDIR /app

COPY --from=builder /wheels /usr/local/lib/python3.11/site-packages
COPY --chown=medharness:medharness mcp/phi-detector/server_v3.py /app/server_v3.py
COPY --chown=medharness:medharness mcp/phi-detector/postprocess.py /app/postprocess.py
COPY --chown=medharness:medharness mcp/phi-detector/fields.yml /app/fields.yml
COPY --chown=medharness:medharness mcp/phi-detector/recognizers/ /app/recognizers/

USER medharness:medharness

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python server_v3.py health || exit 1

ENTRYPOINT ["python", "server_v3.py"]
CMD ["serve", "--stdio"]
