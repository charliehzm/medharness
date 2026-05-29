/**
 * A0 契约 · framework-agnostic mock 解析器（🔒 单 owner: charliehzm）
 *
 * FE 的 api-client 在 mock 模式下直接调 resolveMock()，无需起 server，
 * 后端 ready 后切真实 fetch。所有 fixture 均为合成数据，0 PHI。
 */
import type {
  ApiError,
  AuditExportResponse,
  AuditLineageResponse,
  ConfigProposeResponse,
  ConfigSnapshot,
  EventsResponse,
  PostureResponse,
  TrafficResponse,
  UpstreamsResponse,
} from "./types";

import posture from "./fixtures/posture.json";
import traffic from "./fixtures/traffic.json";
import events from "./fixtures/events.json";
import audit from "./fixtures/audit.json";
import upstreams from "./fixtures/upstreams.json";
import config from "./fixtures/config.json";
import exportRes from "./fixtures/export.json";
import propose from "./fixtures/propose.json";

export type MockResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; data: ApiError };

const auditMap = audit as Record<string, AuditLineageResponse>;
const configMap = config as Record<string, ConfigSnapshot>;

function ok<T>(data: T): MockResult<T> {
  return { ok: true, status: 200, data };
}
function notFound(): MockResult<never> {
  return { ok: false, status: 404, data: { error: { code: "not_found" } } };
}

/**
 * 解析一个 mock 请求。
 * @param method HTTP 方法
 * @param rawPath 形如 `/api/v1/audit/routing%23a1b2` 或 `/posture`（base 前缀可有可无）
 */
export function resolveMock(method: string, rawPath: string): MockResult<unknown> {
  const m = method.toUpperCase();
  const path = rawPath.replace(/^\/api\/v1/, "").split("?")[0];

  if (m === "GET" && path === "/posture") return ok(posture as PostureResponse);
  if (m === "GET" && path === "/traffic") return ok(traffic as TrafficResponse);
  if (m === "GET" && path === "/events") return ok(events as EventsResponse);
  if (m === "GET" && path === "/upstreams") return ok(upstreams as UpstreamsResponse);

  const auditM = path.match(/^\/audit\/(.+)$/);
  if (m === "GET" && auditM) {
    const rec = auditMap[decodeURIComponent(auditM[1])];
    return rec ? ok(rec) : notFound();
  }

  const cfgM = path.match(/^\/config\/([^/]+)$/);
  if (m === "GET" && cfgM) {
    const rec = configMap[cfgM[1]];
    return rec ? ok(rec) : notFound();
  }

  if (m === "POST" && path === "/audit/export") return ok(exportRes as AuditExportResponse);
  if (m === "POST" && /^\/config\/[^/]+\/propose$/.test(path)) {
    return ok(propose as ConfigProposeResponse);
  }

  return notFound();
}
