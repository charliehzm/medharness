import {
  API_BASE,
  ENDPOINTS,
  buildPath,
  resolveMock,
  assertNoPhi,
  type AuditExportRequest,
  type ConfigProposeRequest,
  type CostQuery,
  type EndpointKey,
  type EventsQuery,
  type ApiError,
  type ResponseByEndpoint,
  type Sanitized,
  type TrafficQuery,
} from "@/api/contract";
import { getToken, saveSession } from "@/api/session";

export type ApiMode = "mock" | "live";

export type ApiClientErrorCode =
  | "api_network_error"
  | "api_http_error"
  | "api_invalid_json"
  | "api_request_error";

export interface ApiRequestOptions<K extends EndpointKey> {
  path?: Record<string, string>;
  query?: K extends "traffic"
    ? TrafficQuery
    : K extends "events"
      ? EventsQuery
      : K extends "cost"
        ? CostQuery
        : never;
  body?: K extends "auditExport"
    ? AuditExportRequest
    : K extends "configPropose"
      ? ConfigProposeRequest
      : never;
  mode?: ApiMode;
  fetchImpl?: FetchLike;
  headers?: HeadersInit;
}

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const DEFAULT_MODE = readDefaultMode();
const GENERIC_MSG = "请求失败";

function readDefaultMode(): ApiMode {
  const raw = (import.meta as ImportMeta & {
    env?: { VITE_API_MODE?: string };
  }).env?.VITE_API_MODE;
  return raw === "live" ? "live" : "mock";
}

function makeApiError(code: ApiClientErrorCode): ApiError {
  return { error: { code, msg: GENERIC_MSG } };
}

function buildQuery(query?: Record<string, unknown>): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, String(item));
    } else {
      params.set(key, String(value));
    }
  }
  const serialized = params.toString();
  return serialized ? `?${serialized}` : "";
}

function resolveRequestPath<K extends EndpointKey>(key: K, options: ApiRequestOptions<K>): string {
  const def = ENDPOINTS[key];
  try {
    const path = buildPath(def.path, options.path ?? {});
    return `${path}${buildQuery(options.query as Record<string, unknown> | undefined)}`;
  } catch {
    throw makeApiError("api_request_error");
  }
}

function cloneContractShape<T>(value: unknown): T {
  return JSON.parse(JSON.stringify(value));
}

function tryParseJson<T>(text: string): T | undefined {
  if (!text.trim()) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

async function readBody(response: Response): Promise<string> {
  try {
    return await response.text();
  } catch {
    throw makeApiError("api_http_error");
  }
}

/**
 * FE 统一 api-client：默认 mock，真模式走 fetch → assertNoPhi → Sanitized<T>。
 * 所有成功响应在进入 React state 前都必须先经过这条缝。
 */
export async function requestEndpoint<K extends EndpointKey>(
  key: K,
  options: ApiRequestOptions<K> = {},
): Promise<Sanitized<ResponseByEndpoint[K]>> {
  const def = ENDPOINTS[key];
  const mode = options.mode ?? DEFAULT_MODE;
  const where = `${def.method} ${def.path}`;
  const path = resolveRequestPath(key, options);

  if (mode === "mock") {
    const result = resolveMock(def.method, `${API_BASE}${path}`);
    if (!result.ok) throw makeApiError("api_http_error");
    return assertNoPhi(cloneContractShape<ResponseByEndpoint[K]>(result.data), where);
  }

  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const init: RequestInit = { method: def.method, headers };
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    init.body = JSON.stringify(options.body);
  }

  const fetchImpl = options.fetchImpl ?? fetch;
  let response: Response;
  try {
    response = await fetchImpl(`${API_BASE}${path}`, init);
  } catch {
    throw makeApiError("api_network_error");
  }

  const bodyText = await readBody(response);
  const parsed = tryParseJson<ResponseByEndpoint[K]>(bodyText);

  if (!response.ok) {
    throw makeApiError("api_http_error");
  }
  if (parsed === undefined) {
    throw makeApiError("api_invalid_json");
  }

  return assertNoPhi(parsed, where);
}

export type ConsoleRole = "rdlead" | "sysadmin";

export interface LoginResult {
  ok: true;
  role: ConsoleRole;
  username: string;
  displayName: string;
  token: string;
}

export interface LoginOptions {
  mode?: ApiMode;
  fetchImpl?: FetchLike;
}

/**
 * Console 登录：live 模式把 {username,password} POST 到 A0 /auth/login，A0 再转发
 * new-api 校验。mock 模式无后端，任意非空凭据作为演示 gate 放行（含 "admin" 落 sysadmin）。
 * 任何失败一律抛 generic ApiError —— 不区分原因、不泄漏后端文案。
 */
export async function login(
  username: string,
  password: string,
  options: LoginOptions = {},
): Promise<LoginResult> {
  const mode = options.mode ?? DEFAULT_MODE;
  const user = username.trim();

  if (mode === "mock") {
    if (!user || !password) throw makeApiError("api_request_error");
    const role: ConsoleRole = user.toLowerCase().includes("admin") ? "sysadmin" : "rdlead";
    const token = `mock.${role}`;
    saveSession({ token, role, username: user });
    return { ok: true, role, username: user, displayName: user, token };
  }

  const fetchImpl = options.fetchImpl ?? fetch;
  let response: Response;
  try {
    response = await fetchImpl(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: user, password }),
    });
  } catch {
    throw makeApiError("api_network_error");
  }

  const bodyText = await readBody(response);
  if (!response.ok) throw makeApiError("api_http_error");

  const parsed = tryParseJson<{
    ok?: boolean;
    role?: string;
    username?: string;
    display_name?: string;
    token?: string;
  }>(bodyText);
  if (!parsed || parsed.ok !== true) throw makeApiError("api_invalid_json");

  const role: ConsoleRole = parsed.role === "sysadmin" ? "sysadmin" : "rdlead";
  const resolvedUser = parsed.username ?? user;
  const token = typeof parsed.token === "string" ? parsed.token : "";
  // Persist so a refresh restores the session and admin-write calls carry the token.
  if (token) saveSession({ token, role, username: resolvedUser });
  return { ok: true, role, username: resolvedUser, displayName: parsed.display_name ?? "", token };
}
