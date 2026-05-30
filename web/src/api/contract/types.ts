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
export interface PostureResponse {
  composite: number;
  compliance_score: number;
  security_score: number;
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
  auditExport: AuditExportResponse;
  configPropose: ConfigProposeResponse;
}
