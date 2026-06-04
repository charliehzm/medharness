# MedHarness 部署快速开始 (Self-host, v0.5.0-edge)

> 只想在 macOS / 单机上点开看看（含 Console 账号密码登录）？直接跳到 **§9 本地 docker 一键体验**。

## 1. 先决条件

```bash
docker version
docker compose version
```

- 一台 Linux 主机。
- Docker + Docker Compose。
- 可选：自备 TLS 证书；否则可先用自签名证书启动。

## 2. 构建镜像

`scripts/docker-build.sh` 默认从 `VERSION` 文件读取 tag；当前版本应与 `deploy/.env.production` 里的 `VERSION` 保持一致。

```bash
for svc in phi-detector desensitize model-router audit-log \
           outbound-safety prompt-injection-scan a0-api \
           ci-trigger internal-kb pm-bridge vector-db; do
  bash scripts/docker-build.sh "$svc"
done
```

`new-api` 镜像由 prod compose 从 `vendor/new-api` 构建：

```bash
docker compose -f deploy/docker-compose.prod.yml \
  --env-file deploy/.env.production.example build new-api
```

后续 `up` 时如果镜像缺失，compose 也会按同一 build context 构建。

## 3. 配置

```bash
cp deploy/.env.production.example deploy/.env.production
$EDITOR deploy/.env.production
```

至少替换这些占位值：

- `CLICKHOUSE_PASSWORD`
- `REDIS_PASSWORD`
- `NEW_API_CRYPTO_SECRET`
- `MODEL_ROUTER_TIER_SECRET`：§D.1 tier 签名/校验 secret，需与 new-api gate 和 model-router 保持一致，不发给客户端。

生成默认自签名证书：

```bash
sudo bash scripts/gen-tls.sh --cn <host>
```

或挂载 BYO 证书到 `TLS_CERT_DIR`，目录内文件名必须是：

```text
cert.pem
key.pem
```

## 4. 一次性 WORM / Audit Retention

```bash
sudo bash scripts/setup-worm.sh
```

该脚本默认准备 `/data/medharness/audit` 下的 `_audit_log`、`audit-export`、`audit-backup` 三个目录；Linux 上执行 `chattr +a` 并用 `lsattr` 校验 append-only。macOS 只走目录准备/跳过路径，生产部署应在 Linux 上执行。

## 5. 启动

```bash
docker compose -f deploy/docker-compose.prod.yml \
  --env-file deploy/.env.production up -d
```

nginx 位于 DMZ，仅对外暴露 `/v1/*` gated relay、`/api/v1/*` A0 Console API，以及 `/health` liveness；其余路径默认 404。内部 MCP、ClickHouse、Redis 均只在 internal 网络内可达。

## 6. 验证

```bash
curl -k https://<host>/health
docker compose -f deploy/docker-compose.prod.yml \
  --env-file deploy/.env.production ps
```

集成 smoke 使用合成数据，不使用真实 PHI 或真实 provider：

```bash
bash scripts/int5b_relay_smoke.sh
bash scripts/int5_console_smoke.sh
```

- `scripts/int5b_relay_smoke.sh` 复现 §D.1 relay E2E：allow path 到 mock upstream，deny path 返回 generic 503 且 mock upstream 新连接数为 0。
- `scripts/int5_console_smoke.sh` 复现 Console-live 路径：真实 ClickHouse + 真实 A0 API，并做聚合响应的 0-PHI spot check。

## 7. 架构一句话

每次模型调用都经过 §D.1 spine：`phi -> desensitize -> model-router -> injection -> relay -> outbound-safety`；A0 Console 通过字段白名单做到 0-PHI，deny path 保证 0 upstream connection。

## 8. 已知边界

- 真实 LLM provider channel 由 operator 在 new-api admin 中配置。
- `ci-trigger`、`internal-kb`、`pm-bridge`、`vector-db` 是 v0.5.0-edge 的 intentional placeholders。
- 真实 OIDC、多租户、billing 是 post-v1.0 范围。

## 9. 本地 docker 一键体验（macOS / 单机 dev，含 Console 登录）

> prod compose 默认用 `/data/medharness/*` 主机 bind 挂载（Linux 生产盘 + WORM）。在
> dev 机上叠加 `deploy/docker-compose.local.yml` override：把这些 bind 换成 Docker 命名
> 卷、把 nginx 映射到本机高端口（18080/18443），**零主机目录准备**即可起全栈。自建
> Console 也已打进 nginx 镜像（live 模式），同源访问。

```bash
# 1) 配置（本地 throwaway 密钥；TLS 指向仓库内目录，避免 /etc 与 sudo）
cp deploy/.env.production.example deploy/.env.production
#   编辑 deploy/.env.production：CLICKHOUSE_PASSWORD / REDIS_PASSWORD /
#   NEW_API_CRYPTO_SECRET / MODEL_ROUTER_TIER_SECRET 填本地值；
#   并把 TLS_CERT_DIR 改成绝对路径，如 TLS_CERT_DIR=$PWD/deploy/.tls
bash scripts/gen-tls.sh --cn localhost --out deploy/.tls

# 2) 构建 + 起全栈（两个 compose 文件叠加；首跑会 build new-api / a0-api / nginx+Console）
docker compose -f deploy/docker-compose.prod.yml -f deploy/docker-compose.local.yml \
  --env-file deploy/.env.production up -d --build

# 3) 一次性 bootstrap new-api root 账号（/api/setup 经 DMZ 会被 404，故用 exec）
docker compose -f deploy/docker-compose.prod.yml -f deploy/docker-compose.local.yml \
  --env-file deploy/.env.production exec -T new-api \
  wget -qO- --header='Content-Type: application/json' \
  --post-data='{"username":"admin","password":"medharness123","confirmPassword":"medharness123","SelfUseModeEnabled":true,"DemoSiteEnabled":false}' \
  http://localhost:3000/api/setup
```

打开 `https://localhost:18443`（自签证书，浏览器需手动信任），用 **admin / medharness123**
登录 → 落「系统管理员」。验证（curl）：

```bash
curl -sk https://localhost:18443/health                                  # ok
curl -sk -X POST https://localhost:18443/api/v1/auth/login \
  -H 'Content-Type: application/json' -d '{"username":"admin","password":"medharness123"}'
#   -> {"ok":true,"role":"sysadmin","username":"admin","display_name":"Root User"}
curl -sk -o /dev/null -w '%{http_code}\n' https://localhost:18443/api/setup   # 404（控制面在 DMZ 被拒）
```

**登录链路**：Console 表单（账号+密码）→ nginx 同源 → A0 `POST /api/v1/auth/login` →
转发 new-api `/api/user/login` 真校验；new-api `role≥10` 落「系统管理员」，否则「研发负责人」；
失败一律 generic 401（不回显后端文案）。

dev 已知点：

- `ci-trigger / internal-kb / pm-bridge / vector-db` 是 intentional placeholders，会 restart-loop（退出码 0），**不在登录/Console 路径上**，可忽略或 `docker compose ... stop <svc>`。
- Console 数据源是 ClickHouse `_audit_log`；空库时各屏走 degraded。要看「有数据」的 Console，参考 `scripts/int5_console_smoke.sh` 的 `dev_seed_audit.py` 思路灌合成（0-PHI）行。
- 端口/卷可在 `deploy/docker-compose.local.yml` 改；停栈 `docker compose -f ... -f ... down`（加 `-v` 连命名卷一起删）。
