/**
 * A0 只读聚合 API 契约 · 端点定义（🔒 单 owner: charliehzm）
 *
 * 全部 GET（只读），唯二 POST 为导出与提交审批。
 * Console 不经此改配置——写口只产生「提交审批」动作，实际变更仍走 PR + 审批流 + Hook。
 */
import type { ConfigSection } from "./types";

export { API_BASE } from "./version";

export type HttpMethod = "GET" | "POST";

export interface EndpointDef {
  method: HttpMethod;
  /** 路径模板，{ref} / {section} 为占位 */
  path: string;
  /** true = 只读（GET）；false = 写口（导出 / 提交审批） */
  readonly: boolean;
}

export const ENDPOINTS = {
  posture: { method: "GET", path: "/posture", readonly: true },
  traffic: { method: "GET", path: "/traffic", readonly: true },
  events: { method: "GET", path: "/events", readonly: true },
  audit: { method: "GET", path: "/audit/{ref}", readonly: true },
  upstreams: { method: "GET", path: "/upstreams", readonly: true },
  cost: { method: "GET", path: "/cost", readonly: true },
  channels: { method: "GET", path: "/channels", readonly: true },
  config: { method: "GET", path: "/config/{section}", readonly: true },
  auditExport: { method: "POST", path: "/audit/export", readonly: false },
  configPropose: { method: "POST", path: "/config/{section}/propose", readonly: false },
} as const satisfies Record<string, EndpointDef>;

export type EndpointKey = keyof typeof ENDPOINTS;

/** /config/{section} 的合法 section 全集（与 prototype 配置左导航一一对应） */
export const CONFIG_SECTIONS: readonly ConfigSection[] = [
  "scene",
  "models",
  "fields",
  "thresholds",
  "retention",
  "injection",
  "output",
  "quota",
  "upstream",
  "approval",
] as const;

/** 把路径模板填充为实际路径，如 buildPath("/audit/{ref}", {ref:"routing#a1b2"}) */
export function buildPath(template: string, params: Record<string, string> = {}): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => {
    const v = params[key];
    if (v === undefined) throw new Error(`buildPath: missing param "${key}"`);
    return encodeURIComponent(v);
  });
}
