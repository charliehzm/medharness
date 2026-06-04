# INT-5b · §D.1 relay-path E2E runbook (next focused session)

Goal: a real `POST /v1/chat/completions` transits the §D.1 spine (phi→desens→
router→injection → base relay → outbound) to a MOCK upstream, end-to-end.
**Synthetic only — no real provider, no real PHI.** Heavy (new-api Go image
build + ~9 services), so run this with a fresh context budget.

## Pieces (all already built or banked)
- Mock upstream: `tools/mock_upstream/server.py` (branch `feat/mock-upstream`, 8/8) → run on `:18080`, OpenAI/Anthropic compatible, synthetic replies.
- Gate MCP services (real): phi-detector / desensitize / model-router / prompt-injection-scan / outbound-safety + audit-log + ClickHouse + Redis — `deploy/docker-compose.prod.yml`.
- new-api fork: `vendor/new-api` (the §D.1 middleware `MedHarnessCompliance` is mounted on `/v1`).
- Synthetic CH seed: `scripts/dev_seed_audit.py`.

## new-api local config (from Explore; vendor/new-api)
- Run with SQLite: leave `SQL_DSN` unset (auto SQLite at `one-api.db`, `common/database.go:15`); set `SESSION_SECRET` (non-empty), `MEMORY_CACHE_ENABLED=true`, `PORT=3000`. Fresh DB auto-creates **root:123456** (`model/main.go:68`).
- Channel (`model/channel.go`): `type=1` (ChannelTypeOpenAI, `constant/channel.go:4`), `base_url="http://mock-upstream:18080"`, `key="sk-mock"` (dummy ok), `models="gpt-4o"`, `group="default"`, `status=1`. Creating via API auto-populates the **ability** table (`model/ability.go:146` AddAbilities) — Distribute() routes by `(group, model)` ability rows, so the ability row is REQUIRED.
- Token: `POST /api/token` (UserAuth), key via `GET /api/token/{id}/key`; relay header `Authorization: Bearer sk-<key>`; token.group must match channel.group.

## Minimal happy path
1. `POST /api/user/login {username:root,password:123456}` → session cookie.
2. `POST /api/channel {mode:single, channel:{type:1, base_url:"http://mock-upstream:18080", key:"sk-mock", models:"gpt-4o", group:"default", status:1, name:"MockUpstream"}}` (AdminAuth).
3. `POST /api/token {name, remain_quota:999999, group:"default"}` → fetch key.
4. `POST /v1/chat/completions {model:"gpt-4o", messages:[...]}` with `Authorization: Bearer sk-...`.

## §D.1 env the middleware needs (medharness_compliance.go)
PHI_DETECTOR_URL / DESENSITIZE_URL / MODEL_ROUTER_URL / INJECTION_URL /
OUTBOUND_SAFETY_URL (each `http://<svc>:9000`) + `MODEL_ROUTER_TIER_SECRET`.
model-router needs an active MODEL_ALLOWLIST containing `gpt-4o` for agent_role
+ data_level, else the gate denies (fail-closed) — seed a permissive dev allowlist.

## Acceptance
- allow path: a clean request → 200, body is the mock reply, AND an audit row lands in ClickHouse (the §D.1 audit double-write).
- deny path: a request the gate denies → 503 generic, **mock upstream sees 0 connections** (verify via mock-upstream request log / counter).

## Gotchas
- channel `status=1` + ability row + model in `models` CSV + token.group==channel.group.
- the gate is fail-closed: if any MCP service or the allowlist is missing, every relay 503s — bring the gate stack up FIRST and confirm each `/health` before relaying.
- base_url MUST include scheme (`http://...`).
