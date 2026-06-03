# MedHarness DMZ terminator: builds the self-built Console (live mode) and
# serves it as static SPA, then terminates TLS + enforces the ADR-18 §5 egress
# allowlist (only /v1/ relay + /api/v1/ A0 console proxy upstream).
#
# Build context is the repo root (compose: context: ..), so COPY paths are
# repo-relative. vendor/ is excluded via .dockerignore to keep the context lean.

# ── stage 1: build the Console (VITE_API_MODE=live → talks to the real A0 BFF)
FROM oven/bun:1-alpine AS console
WORKDIR /web
COPY web/package.json web/bun.lock ./
RUN bun install
COPY web/ ./
ENV VITE_API_MODE=live
RUN bun run build

# ── stage 2: nginx terminator with the Console baked in
FROM nginx:1.27-alpine
COPY deploy/nginx/medharness.conf /etc/nginx/conf.d/default.conf
COPY --from=console /web/dist /usr/share/nginx/html
EXPOSE 80 443
