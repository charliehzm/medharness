/**
 * A0 只读聚合 API 契约 · 类型定义（🔒 单 owner: charliehzm）
 *
 * 这是前后端唯一的耦合点（缝）。FE 只 import，不改；BE 照此实现端点。
 *
 * 不可让步（ADR-15 / COMPLIANCE_TAG）：
 *  - 返回体只允许三类内容：占位符（`__NAME_a1__`）/ 哈希引用（`routing#a1b2`）/ 聚合数与分类标签
 *  - 安全事件 `payload` 字段恒 null（不回显，防二次传播）
 *  - 永不含原始 PHI / 反向映射表
 *  - 错误体 msg 不得含系统版本 / 栈 / 内部路径
 */

export type Ctx = "dev" | "prod";
export type GateGroup = "compliance" | "security";
export type GateStatus = "green" | "yellow" | "red" | "planned";
export type AlertLevel = "info" | "warn" | "crit";
export type EventStatus = "green" | "yellow" | "red";
export type SecType = "注入" | "滥用" | "输出";
export type DataLevel = "L2" | "L3" | "L4";
export type ApprovalLevel = "单签" | "会签" | "三签";

export type ConfigSection =
  | "scene"
  | "models"
  | "fields"
  | "thresholds"
  | "retention"
  | "injection"
  | "output"
  | "quota"
  | "upstream"
  | "approval";

/** 统一错误体 — msg 不得泄露系统/版本/栈/路径（ADR-17） */
export interface ApiError {
  error: { code: string; msg?: string };
}

/** 通用 k/v 明细（值只允许占位符 / 哈希 / 聚合） */
export interface KV {
  k: string;
  v: string;
}

// ── 1. GET /posture ──────────────────────────────────────────────
export interface Gate {
  id: string;
  group: GateGroup;
  status: GateStatus;
  metric: string;
  desc?: string;
  /** 未建能力 = false → 前端必须渲染 🚧 */
  built?: boolean;
}
export interface PostureAlert {
  cat: GateGroup;
  type: string;
  level: AlertLevel;
  summary: string;
  /** 安全事件不回显 payload，恒 null */
  payload: null;
}
/** 四目标之一的实时评分卡（全部来自 A0 实时聚合，0-100）。 */
export interface PostureGoal {
  key: "security" | "cost" | "compliance" | "stability";
  score: number;
  metric: string;
  submetric: string;
  summary: string;
}
/** 月度小结文本（来自真实审计 / 成本聚合）。 */
export interface PostureSummaries {
  security: string;
  cost: string;
}
export interface PostureResponse {
  composite: number;
  compliance_score: number;
  security_score: number;
  cost_score: number;
  stability_score: number;
  goals: PostureGoal[];
  summaries: PostureSummaries;
  gates: Gate[];
  alerts: PostureAlert[];
}

// ── 2. GET /traffic?window=&ctx= ─────────────────────────────────
export interface TrafficQuery {
  window?: "1h" | "24h" | "7d";
  ctx?: "all" | Ctx;
}
export interface InboundUpstream {
  name: string;
  ctx: Ctx;
  rate: number;
}
export interface InboundGate {
  hit: number;
  blocked: number;
  passed: number;
}
export interface DownstreamNode {
  name: string;
  note?: string;
}
export interface OutboundGate {
  phi_reflow: number;
  harmful: number;
  hallucination: number;
}
export interface TrafficResponse {
  inbound: {
    upstreams: InboundUpstream[];
    gate: InboundGate;
    downstream: DownstreamNode[];
  };
  outbound: {
    /** v0.6 出站能力未建 → false，前端渲染 🚧 */
    built: boolean;
    note?: string;
    gate: OutboundGate;
  };
}

// ── 3. GET /events?cat=&ctx=&limit= ──────────────────────────────
export interface EventsQuery {
  cat?: "all" | "comp" | "sec";
  ctx?: "all" | Ctx;
  limit?: number;
}
interface EventBase {
  ts: string;
  status: EventStatus;
  upstream: string;
  ctx: Ctx;
  action: string;
  ref: string;
}
/** 合规事件：带数据分级 level，无 sec_type / payload */
export interface ComplianceEvent extends EventBase {
  cat: "comp";
  level: DataLevel;
}
/** 安全事件：带 sec_type，payload 恒 null */
export interface SecurityEvent extends EventBase {
  cat: "sec";
  sec_type: SecType;
  payload: null;
}
export type TrafficEvent = ComplianceEvent | SecurityEvent;
export interface EventsResponse {
  events: TrafficEvent[];
}

// ── 4. GET /audit/{ref} ──────────────────────────────────────────
export interface LineageNode {
  ico: string;
  t: string;
  s: string;
}
export interface AuditLineageResponse {
  ref: string;
  title: string;
  nodes: LineageNode[];
  hash: string;
  /** details[].v 只允许占位符 / 哈希 / 聚合；反向映射表与原始 PHI 不出现 */
  details: KV[];
}

// ── 5. GET /upstreams ────────────────────────────────────────────
export interface UpstreamStatus {
  name: string;
  ctx: Ctx;
  protocol: string;
  status: EventStatus;
  traffic_today: number;
  /** 聚合摘要串，如 "命中 312 / 拦 5"（计数，非原文） */
  phi: string;
}
export interface UpstreamsResponse {
  upstreams: UpstreamStatus[];
}

// ── 6. GET /config/{section} ─ 只读策略快照 ──────────────────────
export interface ConfigSnapshot {
  section: ConfigSection;
  title: string;
  /** 字段以 k/v 聚合呈现，供 Console 展示与 diff 预览 */
  fields: KV[];
  /** 未建能力（output / quota）= false → 前端渲染 🚧 */
  built?: boolean;
  note?: string;
}

// ── POST /audit/export ─ 唯一非 GET（导出 AUDIT_BUNDLE） ─────────
export interface AuditExportRequest {
  scope?: "all" | "change";
  change_id?: string;
  window?: string;
}
export interface AuditExportResponse {
  bundle_id: string;
  status: "packing" | "ready";
  sha256: string;
}

// ── POST /config/{section}/propose ─ 配置变更唯一写口（不旁路 Hook）─
export interface ConfigProposeRequest {
  /** 变更前后 diff（聚合 / 占位符，不含 PHI） */
  before: KV[];
  after: KV[];
  reason?: string;
}
export interface ConfigProposeResponse {
  approval_id: string;
  level: ApprovalLevel;
  status: "queued";
}

// ── 7. GET /cost?window= ─ 用量与成本（v0.7.0 · 全聚合·天然 0 PHI） ─
export interface CostKpi {
  month_cost: string;
  saved_vs_direct: string;
  saved_ratio: string;
  cache_hit_ratio: string;
  cache_saved: string;
  cap_day: string;
  cap_used: string;
  cap_left_ratio: string;
  normal_lane_ratio: string;
}
/** 成本构成单元（按通道 / 按模型）；color_token 为设计 token 名，非颜色值 */
export interface CostByDim {
  name: string;
  color_token: string;
  pct: number;
  amount: string;
}
export interface CostTip {
  tip: string;
  saving: string;
}
export interface CostQuery {
  window?: "1h" | "24h" | "7d" | "month";
}
export interface CostResponse {
  window: "1h" | "24h" | "7d" | "month";
  kpi: CostKpi;
  by_lane: CostByDim[];
  by_model: CostByDim[];
  /** 近 N 日成本趋势（聚合数） */
  trend: number[];
  tips: CostTip[];
}

// ── 8. GET /channels ─ 渠道比价择优（v0.7.0 · 聚合·无 PHI） ────────
export interface Channel {
  name: string;
  model: string;
  weight: number;
  unit_price: string;
  p95_ms: number;
  region: string;
  /** 当前择优命中（最优渠道） */
  picked: boolean;
  status: EventStatus;
}
export interface ChannelsResponse {
  channels: Channel[];
}

// ── 9. GET /admin/{users|tokens|channels} ─ 管理面只读代理（v0.7.1 · B5）────
// 红线：接入屏的「读」经此（不直调 new-api，防绕过 Sanitized<T> 守卫）。
// **字段白名单**：只回 id 哈希 / 角色 / 配额 / 数据等级 / 区域；
// **禁** email / phone / display_name / 备注 / 明文密钥（key）/ 社交 id。
export interface AdminUser {
  /** 用户 id 的哈希引用，非原始 id / 用户名 */
  id_hash: string;
  role: string;
  status: string;
  group: string;
  quota: string;
  used_quota: string;
  /** 映射 Console 2 角色；普通用户/服务为 null（仅令牌、不进 Console） */
  console_role?: "研发负责人" | "系统管理员" | null;
}
export interface AdminToken {
  /** new-api 内部令牌 id（非 PHI）；CRUD 句柄 */
  id: number;
  /** 令牌标签（用户自设·非密钥）；后端确保非 PHI */
  name: string;
  status: "enabled" | "disabled" | "throttled";
  remain_quota: string;
  unlimited_quota: boolean;
  used_quota: string;
  group: string;
  allowed_data_levels: DataLevel[];
  expired_time?: string;
  accessed_time: string;
}
export interface AdminChannel {
  /** new-api 内部渠道 id（非 PHI）；CRUD 句柄 */
  id: number;
  name: string;
  type: string;
  status: EventStatus;
  weight: number;
  group: string;
  region: string;
  lane: "normal" | "sensitive";
  models: string[];
  used_quota: string;
}
export interface AdminUsersResponse {
  users: AdminUser[];
}
export interface AdminTokensResponse {
  tokens: AdminToken[];
}
export interface AdminChannelsResponse {
  channels: AdminChannel[];
}

// ── 10. /admin/users/* ─ 用户管理写代理（v0.7.2 · B2/B3 · sysadmin only）─────
// 与只读 AdminUser 不同：这是「系统管理员」管理内部运营人员（operators，**非患者**）
// 身份的明面视图，**合法携带 STAFF email / display_name**。患者 0 PHI 不受影响——
// email 仅指运营人员邮箱，故此响应走 `assertNoPatientPhi`（放行 email），
// **不**经 dashboard 级的 email-included `assertNoPhi`。仅 sysadmin 可读写（A0 401/403）。
export type MgmtRole = "root" | "admin" | "normal";
export type MgmtStatus = "enabled" | "disabled";

/** 用户管理行——运营人员（非患者）的可管理字段。 */
export interface MgmtUser {
  id: number;
  username: string;
  display_name: string;
  /** 运营人员（非患者）邮箱；故走 assertNoPatientPhi。 */
  email: string;
  role: MgmtRole;
  status: MgmtStatus;
  group: string;
  quota: string;
  used_quota: string;
  last_login: string;
}
export interface MgmtUsersResponse {
  users: MgmtUser[];
  total: number;
}
export interface GroupsResponse {
  groups: string[];
}

// ── 10. /admin/{channels|tokens}/* ─ 渠道 / 令牌管理写代理（v0.9.0）─────
// 管理写请求只经 requestMgmt，成功返回 {ok:true}；密钥只允许出现在提交请求体，
// 不得在任何读取响应、fixture 或 UI state 中回显。
export type MgmtChannel = AdminChannel;
export type MgmtToken = AdminToken;
export interface MgmtChannelsResponse {
  channels: MgmtChannel[];
}
export interface MgmtTokensResponse {
  tokens: MgmtToken[];
}

/** POST /admin/channels — 新建渠道。key 为 write-only 凭据。 */
export interface MgmtChannelCreate {
  name: string;
  type: string;
  key: string;
  base_url?: string;
  models: string[];
  group: string;
  weight: number;
}
/** POST /admin/channels/{id}/update — 编辑渠道。key 留空时不提交。 */
export interface MgmtChannelUpdate {
  name?: string;
  type?: string;
  key?: string;
  base_url?: string;
  models?: string[];
  group?: string;
  weight?: number;
}

/** POST /admin/tokens — 新建接入应用令牌。 */
export interface MgmtTokenCreate {
  name: string;
  /** 数值额度（new-api 配额单位整数）；不限额度时省略 */
  remain_quota?: number;
  unlimited_quota?: boolean;
  group: string;
  allowed_data_levels: DataLevel[];
  expired_time?: string;
}
/** POST /admin/tokens/{id}/update — 修改配额 / 数据等级 / 状态。 */
export interface MgmtTokenUpdate {
  name?: string;
  remain_quota?: number;
  unlimited_quota?: boolean;
  group?: string;
  allowed_data_levels?: DataLevel[];
  expired_time?: string;
  status?: MgmtToken["status"];
}

/** POST /admin/users — 新建用户。role 为 new-api int：1=普通 / 10=管理员。 */
export interface MgmtUserCreate {
  username: string;
  password: string;
  display_name?: string;
  role?: number;
  group?: string;
}
/** POST /admin/users/{id}/update — 编辑。role 为 new-api int（1 / 10）。 */
export interface MgmtUserUpdate {
  username?: string;
  display_name?: string;
  group?: string;
  role?: number;
}
/** POST /admin/users/{id}/password — 重置密码（运营人员线下交付，不发邮件）。 */
export interface MgmtUserPassword {
  password: string;
}
/** POST /admin/users/{id}/status — 启用 / 停用。 */
export interface MgmtUserStatus {
  enabled: boolean;
}
/** POST /admin/users/{id}/role — 升级 / 降级。 */
export interface MgmtUserRole {
  action: "promote" | "demote";
}
/** 写代理统一回执（创建 / 更新 / 状态 / 角色 / 删除）。 */
export interface MgmtOk {
  ok: true;
}

/**
 * 渠道连通性探测结果。探测「跑过了」即 ok:true —— reachable 才是上游可达与否的判定，
 * latency_ms 为往返耗时（无法测得时为 null）。绝不回传上游报文（可能含 base_url）。
 */
export interface ChannelTestResult {
  ok: true;
  reachable: boolean;
  latency_ms: number | null;
}

/** 端点 key → 响应类型映射（供 api-client 泛型推导） */
export interface ResponseByEndpoint {
  posture: PostureResponse;
  traffic: TrafficResponse;
  events: EventsResponse;
  audit: AuditLineageResponse;
  upstreams: UpstreamsResponse;
  cost: CostResponse;
  channels: ChannelsResponse;
  config: ConfigSnapshot;
  adminUsers: AdminUsersResponse;
  adminTokens: AdminTokensResponse;
  adminChannels: AdminChannelsResponse;
  auditExport: AuditExportResponse;
  configPropose: ConfigProposeResponse;
}
