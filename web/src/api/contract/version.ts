/**
 * A0 只读聚合 API 契约 · 版本标记（🔒 单 owner: charliehzm）
 *
 * 契约冻结 = 此版本号 + 通过 `api-phi-exfil` red-team drill。
 * 任何 schema 变更必须 bump 此号并通知两个 lane（BE 实现端点 / FE 用 mock）。
 * git tag `contract-v<x>` 在合并入 main 后由 maintainer 打。
 */
// 0.7.1 (additive · 非破坏)：加管理面只读代理 GET /admin/{users|tokens|channels}
//        （AdminUser/Token/Channel · 字段白名单），堵 B5 管理面 0-PHI 绕口——
//        Console 接入屏经此读，不直调 new-api。禁 email/phone/display_name/明文密钥。
// 0.7.0 (additive · 非破坏)：加成本端点 GET /cost + GET /channels
//        （CostResponse / ChannelsResponse），服务四目标「划算」屏。
//        全聚合数·天然 0 PHI。现有 8 端点与类型不变。
// 0.6.1 (additive · 非破坏)：加运行时 0 PHI 守卫 assertNoPhi + Sanitized<T> 品牌
//        （finding #1 · COMPLIANCE_TAG §8）。mock 的 ok 响应改返回 Sanitized<T>，
//        对读取方仍可赋给原类型，无破坏。
export const CONTRACT_VERSION = "0.7.1" as const;

/** 契约 base path（所有端点的前缀） */
export const API_BASE = "/api/v1" as const;
