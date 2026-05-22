# Provider Handoff · v0.5 → v1.0+

## 现状（v0.5.0 edge tier）
- FileKeyProvider 是唯一真实实现。FileKeyProvider is the only real implementation.
- VaultProvider / AliyunKMSProvider / AWSKMSProvider 都是 `.skel` 骨架。
- 当前运行时只走 raw-byte `get_key` 契约，实际可用的是本地 file keystore 路径。

## v1.0 必做：接口重设计
云 KMS 三家都不导出 raw key bytes。v1.0 需要引入：
- `encrypt(plaintext, key_id, context) -> ciphertext + metadata`
- `decrypt(ciphertext, key_id, metadata, context) -> plaintext`

FileKeyProvider 可继续用本地 AESGCM 实现这个接口。
Vault / Aliyun / AWS 需要改成各自的 encrypt/decrypt 代理模式，直接调用云 KMS API。
`server_v2` 也要从 `provider.get_key` 切到 `provider.encrypt/decrypt`。

## v0.5 → v1.0 兼容
- 老 FileKeyProvider envelope 数据在 v1.0 仍可解，因为 envelope 内含 key_id + generation。
- 新 envelope 由新接口生产，metadata 区分 backend 和版本。

## 接 `.skel` 的工程师 todo
1. 先读 `T2-desensitize-kms/AUDIT_BUNDLE.summary.md`。
2. 用对应云 SDK 替换 `.skel` 文件里的 `NotImplementedError`。
3. 加 retry / circuit breaker / 限流。
4. 集成测试要 mock 云 KMS，或起本地 mock 容器。
5. 网络隔离审计要确保所有 egress 都经客户审批的 private network。

## 不做的事
- 不接 boto3。
- 不写真集成测试。
- 不在 v0.5 里定义新的 encrypt/decrypt RFC。
