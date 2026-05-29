/**
 * A0 契约 · 运行时 0 PHI 守卫 + branded 类型（🔒 单 owner: charliehzm）
 *
 * finding #1（异构复审 backlog · COMPLIANCE_TAG §8）：把「返回体 0 PHI」
 * 从注释 / spec / drill 约定升级为「类型 + 运行时」双保险。
 *
 *  - 类型层：`Sanitized<T>` 品牌——没过 `assertNoPhi` 就拿不到这个类型；
 *    api-client 把响应交给 React state 前，必须先过守卫拿到 `Sanitized<T>`。
 *  - 运行时层：`assertNoPhi` 深度遍历响应，命中 PHI 形状或 `payload != null` 即抛。
 *
 * PHI 模式与 python red-team drill `tests/red-team-drills/drill_api_phi_exfil.py`
 * 同源同口径：drill 扫 fixtures（落地前），守卫扫运行时响应（mock + 真实）。
 *
 * 守卫自身 0 PHI：命中只报「JSON 路径 + 模式类别」，**绝不**把命中原文放进
 * 错误消息 / 日志（否则 PHI 经异常二次泄露，违反 R1 / R3）。
 */

declare const PHI_CHECKED: unique symbol;

/** 通过 `assertNoPhi` 后的品牌类型——0 PHI 在类型层留痕 */
export type Sanitized<T> = T & { readonly [PHI_CHECKED]: true };

export type PhiKind =
  | "cn_id"
  | "cn_phone"
  | "email"
  | "bank_card"
  | "cn_passport"
  | "payload_not_null";

/** 单条违规——只含路径与类别，不含原文 */
export interface PhiViolation {
  /** JSON 路径，如 `$.alerts[0].summary` */
  path: string;
  kind: PhiKind;
}

/** 守卫命中时抛出——message 已脱敏，细节在 `.violations`（同样不含原文） */
export class PhiLeakError extends Error {
  readonly violations: readonly PhiViolation[];
  constructor(violations: PhiViolation[], where?: string) {
    super(
      `assertNoPhi${where ? `(${where})` : ""}: 命中 ${violations.length} 处疑似 PHI / 越界` +
        `（已脱敏，详见 .violations）`,
    );
    this.name = "PhiLeakError";
    this.violations = violations;
  }
}

// ── PHI 形状（与 drill_api_phi_exfil.py 同口径）──────────────────────
const PHI_PATTERNS: { kind: PhiKind; re: RegExp }[] = [
  { kind: "cn_id", re: /(?<!\d)\d{17}[\dXx](?!\d)/ },
  { kind: "cn_phone", re: /(?<!\d)1[3-9]\d{9}(?!\d)/ },
  { kind: "email", re: /[\w.+-]+@[\w-]+\.[\w.-]+/ },
  { kind: "bank_card", re: /(?<!\d)\d{16,19}(?!\d)/ },
  { kind: "cn_passport", re: /\b[EeGgDdSsPpHh]\d{8}\b/ },
];
/** 纯哈希（hex ≥ 32，如 sha256）不算 PHI */
const HEXISH = /^[0-9a-fA-F]{32,}$/;
/** 占位符形式 `__NAME_a1__` —— 显式 0 PHI */
const PLACEHOLDER = /^__[A-Z]+_[a-z0-9]+__$/;

/** 扫单个字符串，返回命中的类别（不含原文）。逐 token 判，跳过占位符 / 纯哈希。 */
function scanString(value: string): PhiKind[] {
  if (HEXISH.test(value)) return [];
  const tokens = value.split(/\s+/).filter(Boolean);
  const hits: PhiKind[] = [];
  for (const { kind, re } of PHI_PATTERNS) {
    for (const tok of tokens) {
      if (PLACEHOLDER.test(tok)) continue;
      if (re.test(tok)) {
        hits.push(kind);
        break;
      }
    }
  }
  return hits;
}

function walk(node: unknown, path: string, out: PhiViolation[]): void {
  if (typeof node === "string") {
    for (const kind of scanString(node)) out.push({ path, kind });
    return;
  }
  if (Array.isArray(node)) {
    node.forEach((v, i) => walk(v, `${path}[${i}]`, out));
    return;
  }
  if (node !== null && typeof node === "object") {
    const obj = node as Record<string, unknown>;
    // 结构不变式：任何带 payload 的对象（安全事件 / 告警）其 payload 必须恒 null
    if ("payload" in obj && obj.payload !== null) {
      out.push({ path: `${path}.payload`, kind: "payload_not_null" });
    }
    for (const [k, v] of Object.entries(obj)) walk(v, `${path}.${k}`, out);
  }
}

/** 扫描但不抛——返回违规清单（测试 / 非致命场景用）。 */
export function findPhi(value: unknown): PhiViolation[] {
  const out: PhiViolation[] = [];
  walk(value, "$", out);
  return out;
}

/**
 * 运行时 0 PHI 守卫。通过则把 `value` 收窄为 `Sanitized<T>`，否则抛 `PhiLeakError`。
 * api-client 收到任何响应（mock 或真实 fetch）后、写入 state 前必须过此关。
 *
 * @param value 待校验的响应体
 * @param where 端点标签（如 `GET /posture`），仅用于错误定位，不含数据
 */
export function assertNoPhi<T>(value: T, where?: string): Sanitized<T> {
  const violations = findPhi(value);
  if (violations.length > 0) throw new PhiLeakError(violations, where);
  return value as Sanitized<T>;
}
