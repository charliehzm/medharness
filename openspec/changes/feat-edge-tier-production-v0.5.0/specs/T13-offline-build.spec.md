# Spec · T13 · build-offline.sh 离线包构建

> 任务 T13 完整规格。codex 实现前**必读**。

---

## Purpose

把整个 MedHarness 系统打成单个 `medharness-offline-v0.5.0-edge-<arch>.tar.gz`，
让客户在**无外网**机器上 5 分钟跑起来。

---

## 产物结构

```
medharness-offline-v0.5.0-edge-linux-amd64.tar.gz   (≤ 6 GB)
└── medharness-offline-v0.5.0-edge/
    ├── VERSION                          # "v0.5.0-edge"
    ├── BUILD_INFO                       # build commit / build time / build host
    ├── install.sh
    ├── verify.sh
    ├── teardown.sh
    ├── upgrade.sh                       # 从 < v0.5 升级
    ├── docker-compose.yml               # production 编排
    ├── images/                          # 14 个 docker image tar
    │   ├── medharness-mcp-phi-detector_v0.5.0.tar
    │   ├── medharness-mcp-desensitize_v0.5.0.tar
    │   ├── medharness-mcp-model-router_v0.5.0.tar
    │   ├── medharness-mcp-audit-log_v0.5.0.tar
    │   ├── medharness-mcp-internal-kb_v0.5.0.tar
    │   ├── medharness-mcp-vector-db_v0.5.0.tar
    │   ├── medharness-mcp-ci-trigger_v0.5.0.tar
    │   ├── medharness-mcp-pm-bridge_v0.5.0.tar
    │   ├── clickhouse_24.tar
    │   ├── qdrant_1.x.tar
    │   ├── nginx_1.27.tar
    │   ├── busybox.tar                  # init / health-check
    │   └── medharness-bootstrap_v0.5.0.tar  # 跑 customize.py + 初始化
    ├── wheels/                          # 离线 pip
    │   └── *.whl                        # presidio / spacy / cryptography 等
    ├── models/
    │   ├── spacy_zh_core_web_sm/        # ~85 MB
    │   └── presidio_default/
    ├── configs/
    │   ├── docker-compose.env.example
    │   ├── nginx/
    │   │   └── medharness.conf
    │   ├── clickhouse/
    │   │   ├── config.xml
    │   │   ├── users.xml
    │   │   └── init.sql                 # _audit_log schema
    │   └── qdrant/
    │       └── config.yaml
    ├── data-seed/
    │   ├── synthetic-corpus.jsonl       # 红队 fixture（合成）
    │   └── example-change/              # 患者匹配最小可行版完整 copy
    ├── docs-offline/                    # mkdocs static build
    │   ├── index.html
    │   └── ...
    ├── runbooks/                        # 10 个运维 runbook（T17 产出 copy）
    ├── LICENSE
    ├── LICENSE-CC-BY-SA-4.0
    ├── CHANGELOG.md
    ├── README-offline.md                # 离线包专属 README
    └── checksum/
        ├── SHA256SUMS                   # 所有文件 sha256
        └── SHA256SUMS.asc               # GPG 签名（charliehzm public key）
```

---

## build-offline.sh 流程

```bash
# 1. 前置检查
# - docker buildx 已装
# - cosign 已装（签名用）
# - gpg key 已配（tarball 签名）
# - 磁盘 ≥ 30GB free

# 2. 选目标架构
ARCH="${1:-linux/amd64}"  # 或 linux/arm64

# 3. 构建 docker images（buildx · multi-arch）
for service in phi-detector desensitize model-router audit-log internal-kb vector-db ci-trigger pm-bridge; do
    docker buildx build \
        --platform "$ARCH" \
        --tag "medharness/$service:v0.5.0-edge" \
        --load \
        "./mcp/$service"
done

# 4. cosign 签名（每个 image）
for img in $(docker images medharness/* -q); do
    cosign sign --key cosign.key "$img"
done

# 5. 导出 image 到 tar
mkdir -p dist/medharness-offline-v0.5.0-edge/images/
for service in phi-detector desensitize ...; do
    docker save "medharness/$service:v0.5.0-edge" \
        -o "dist/.../images/medharness-mcp-$service_v0.5.0.tar"
done

# 6. 拉外部 image（一次性）+ 导出
docker pull clickhouse/clickhouse-server:24
docker save clickhouse/clickhouse-server:24 -o dist/.../images/clickhouse_24.tar
# ... qdrant / nginx / busybox

# 7. 离线 pip wheels
pip download --no-binary :none: \
    -r requirements.txt \
    -d dist/.../wheels/

# 8. spaCy 中文模型
python -m spacy download zh_core_web_sm
cp -r .venv/lib/python*/site-packages/zh_core_web_sm \
    dist/.../models/spacy_zh_core_web_sm/

# 9. 文档 build
mkdocs build -d dist/.../docs-offline/

# 10. 复制配置 + 脚本 + 示例
cp -r deploy/* dist/.../
cp -r docs/runbooks dist/.../
cp -r examples/示例-患者匹配最小可行版 dist/.../data-seed/example-change/

# 11. 生成 checksum
cd dist/medharness-offline-v0.5.0-edge/
find . -type f ! -name 'SHA256SUMS*' -exec sha256sum {} + > checksum/SHA256SUMS

# 12. GPG 签名
gpg --detach-sign --armor checksum/SHA256SUMS  # → SHA256SUMS.asc

# 13. 打包
cd dist/
tar -czf medharness-offline-v0.5.0-edge-${ARCH//\//-}.tar.gz \
    medharness-offline-v0.5.0-edge/

# 14. 输出
ls -lh dist/*.tar.gz
sha256sum dist/*.tar.gz
```

---

## 可重复构建

同一 commit → 同一 tarball SHA256：

- buildx 用 `--build-arg SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)`
- pip wheels 用 `--no-cache-dir`
- 不依赖 build 时本地时间戳
- 不依赖 build 主机用户名 / hostname

CI 验证：CI runner 跑一次 build → SHA256 应稳定。

---

## 平台支持

| 平台 | 构建 | 安装 | 状态 |
|---|---|---|---|
| macOS （Apple Silicon） | ✅ buildx | — | dev only |
| macOS （Intel） | ✅ buildx | — | dev only |
| Linux x86_64 | ✅ | ✅ | production |
| Linux arm64 | ✅ | ✅ | demo |
| Windows | ❌ | ❌ | 不支持 |

---

## 体积控制

| 子目录 | 预算 | 实际目标 |
|---|---|---|
| images/ | ≤ 4.5 GB | < 4 GB |
| wheels/ | ≤ 500 MB | ~200 MB |
| models/ | ≤ 200 MB | ~85 MB（spaCy 小模型） |
| data-seed/ | ≤ 50 MB | <10 MB |
| docs-offline/ | ≤ 100 MB | ~20 MB |
| configs/ | ≤ 5 MB | <1 MB |
| runbooks/ | ≤ 10 MB | <2 MB |
| **总和（解压后）** | ≤ 5.5 GB | |
| **tarball（gzip）** | ≤ 6 GB | |

超预算 → fail build。

### 体积优化策略

1. **共享 base layer**：8 MCP image 都用同一 `python:3.11-slim` + presidio base → buildx 自动 dedup
2. **multi-stage build**：build stage 不留 dev deps
3. **删除测试 + 文档** in images（仅 runtime）
4. **wheels 用 `--no-binary :none:` 控制源**

---

## CI integration

### release.yml workflow

```yaml
on:
  push:
    tags: ["v*.*.*-edge"]

jobs:
  build-offline:
    strategy:
      matrix:
        arch: [linux/amd64, linux/arm64]
    steps:
      - uses: actions/checkout@v6
      - uses: docker/setup-buildx-action@v3
      - uses: sigstore/cosign-installer@v3
      - name: Build offline
        run: bash scripts/build-offline.sh ${{ matrix.arch }}
      - name: Upload artifact
        uses: actions/upload-artifact@v7
        with:
          name: medharness-offline-${{ matrix.arch }}
          path: dist/*.tar.gz
      - name: Attach to release
        uses: softprops/action-gh-release@v3
        with:
          files: dist/*.tar.gz
```

---

## Acceptance criteria

- AC1 · tarball < 6 GB
- AC2 · build 在 macOS + Ubuntu CI 都能跑通
- AC3 · 可重复构建：同 commit 两次 build → SHA256 相同
- AC4 · cosign verify 每个 image 通过
- AC5 · gpg verify SHA256SUMS.asc 通过
- AC6 · 解压到无网 Ubuntu 22.04 → `install.sh` 跑通（T14 配合）

---

## Risks

| 风险 | 对冲 |
|---|---|
| 体积超 6GB | 体积 budget 卡死 + 分层 image 复用 |
| 可重复构建失败 | SOURCE_DATE_EPOCH + 严格固化时间戳 |
| arm64 上某些 image 不存在（clickhouse / qdrant 都支持） | 早期 build 一次验证 |
| GPG key 管理 | maintainer 持私钥 + 文档说明验签 |

---

## 安全考虑

- 不打包：真实 PHI / 客户配置 / .env 真值 / 私钥
- 打包：合成数据 / 配置模板 / 公钥
- README-offline.md 明示："请勿在本目录内放置真实 PHI"
