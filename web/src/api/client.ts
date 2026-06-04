import {
  API_BASE,
  ENDPOINTS,
  buildPath,
  resolveMock,
  assertNoPhi,
  assertNoPatientPhi,
  type AuditExportRequest,
  type ConfigProposeRequest,
  type CostQuery,
  type EndpointKey,
  type EventsQuery,
  type ApiError,
  type GroupsResponse,
  type HttpMethod,
  type MgmtChannel,
  type MgmtChannelCreate,
  type MgmtChannelsResponse,
  type MgmtChannelUpdate,
  type ChannelTestResult,
  type MgmtOk,
  type MgmtToken,
  type MgmtTokenCreate,
  type MgmtTokensResponse,
  type MgmtTokenUpdate,
  type MgmtUserCreate,
  type MgmtUserPassword,
  type MgmtUserRole,
  type MgmtUserStatus,
  type MgmtUserUpdate,
  type MgmtUsersResponse,
  type ResponseByEndpoint,
  type Sanitized,
  type TrafficQuery,
} from "@/api/contract";
import { getToken, saveSession } from "@/api/session";
import mgmtChannelsFixture from "@/api/contract/fixtures/admin_channels.json";
import mgmtTokensFixture from "@/api/contract/fixtures/admin_tokens.json";
import mgmtUsersFixture from "@/api/contract/fixtures/admin_users_mgmt.json";

export type ApiMode = "mock" | "live";

export type ApiClientErrorCode =
  | "api_network_error"
  | "api_http_error"
  | "api_invalid_json"
  | "api_request_error";

// `requestEndpoint` only serves endpoints that have a Sanitized<T> response in
// ResponseByEndpoint (reads + propose/export). The user-management write proxy
// endpoints are NOT here on purpose — they legitimately carry STAFF email and are
// reached via `requestMgmt` (patient-only guard), never through this seam.
export type ReadEndpointKey = keyof ResponseByEndpoint & EndpointKey;

export interface ApiRequestOptions<K extends ReadEndpointKey> {
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

function resolveRequestPath<K extends ReadEndpointKey>(key: K, options: ApiRequestOptions<K>): string {
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
export async function requestEndpoint<K extends ReadEndpointKey>(
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

// ──────────────────────────────────────────────────────────────────────────
// 用户管理写代理 client（B2/B3 · sysadmin only）
//
// 与泛型 requestEndpoint 的关键区别：那条缝强制 assertNoPhi + Sanitized<T>，会把
// 合法的运营人员（**非患者**）邮箱误判为 PHI 而拒绝。管理面用 requestMgmt——它跑
// 患者-only 守卫 assertNoPatientPhi（放行 email，仍拦截身份证 / 手机 / 卡号 / 护照），
// 返回**普通**类型（非 Sanitized<T>）。所有失败仍映射为与 requestEndpoint 完全一致
// 的 generic ApiError（不泄漏后端 body / PHI）。dashboard / relay / audit 路径不变。
// ──────────────────────────────────────────────────────────────────────────

export interface MgmtRequestOptions {
  mode?: ApiMode;
  fetchImpl?: FetchLike;
}

const MGMT_GROUPS: GroupsResponse = { groups: ["default", "clinical", "ops", "research", "secure"] };
const MGMT_WRITE_OK: MgmtOk = { ok: true };

let mockChannels: MgmtChannel[] = cloneContractShape<MgmtChannelsResponse>(mgmtChannelsFixture).channels;
let mockTokens: MgmtToken[] = cloneContractShape<MgmtTokensResponse>(mgmtTokensFixture).tokens;
// Start above the fixture ids (1..N) so a mock-created row never collides.
let mockChannelSeq = 1000;
let mockTokenSeq = 1000;

function decodePathId(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function normalizeModels(value?: string[]): string[] {
  const models = (value ?? []).map((item) => item.trim()).filter(Boolean);
  return models.length ? models : ["model-default"];
}

function createMockChannel(body: unknown): void {
  const input = body as Partial<MgmtChannelCreate>;
  mockChannels = [
    {
      id: mockChannelSeq++,
      name: input.name?.trim() || "未命名渠道",
      type: input.type?.trim() || "openai",
      status: "green",
      weight: Number.isFinite(input.weight) ? Number(input.weight) : 100,
      models: normalizeModels(input.models),
      group: input.group?.trim() || "default",
      region: "境内",
      lane: "normal",
      used_quota: "¥0",
    },
    ...mockChannels,
  ];
}

function updateMockChannel(id: string, body: unknown): void {
  const input = body as MgmtChannelUpdate;
  mockChannels = mockChannels.map((channel) =>
    String(channel.id) === id
      ? {
          ...channel,
          name: input.name?.trim() || channel.name,
          type: input.type?.trim() || channel.type,
          weight: input.weight === undefined ? channel.weight : Number(input.weight),
          models: input.models === undefined ? channel.models : normalizeModels(input.models),
          group: input.group?.trim() || channel.group,
        }
      : channel,
  );
}

function deleteMockChannel(id: string): void {
  mockChannels = mockChannels.filter((channel) => String(channel.id) !== id);
}

function normalizeLevels(value?: MgmtToken["allowed_data_levels"]): MgmtToken["allowed_data_levels"] {
  const levels = (value ?? []).filter((level) => level === "L2" || level === "L3");
  return levels.length ? levels : ["L2"];
}

function createMockToken(body: unknown): void {
  const input = body as Partial<MgmtTokenCreate>;
  const unlimited = Boolean(input.unlimited_quota);
  mockTokens = [
    {
      id: mockTokenSeq++,
      name: input.name?.trim() || "未命名接入应用",
      status: "enabled",
      remain_quota: unlimited ? "不限" : input.remain_quota != null ? String(input.remain_quota) : "0",
      unlimited_quota: unlimited,
      used_quota: "¥0",
      group: input.group?.trim() || "default",
      allowed_data_levels: normalizeLevels(input.allowed_data_levels),
      expired_time: input.expired_time?.trim() || "—",
      accessed_time: "—",
    },
    ...mockTokens,
  ];
}

function updateMockToken(id: string, body: unknown): void {
  const input = body as MgmtTokenUpdate;
  mockTokens = mockTokens.map((token) => {
    if (String(token.id) !== id) return token;
    const unlimited = input.unlimited_quota ?? token.unlimited_quota;
    return {
      ...token,
      name: input.name?.trim() || token.name,
      remain_quota: unlimited ? "不限" : input.remain_quota != null ? String(input.remain_quota) : token.remain_quota,
      unlimited_quota: unlimited,
      group: input.group?.trim() || token.group,
      allowed_data_levels: input.allowed_data_levels
        ? normalizeLevels(input.allowed_data_levels)
        : token.allowed_data_levels,
      expired_time: input.expired_time?.trim() || token.expired_time,
      status: input.status ?? token.status,
    };
  });
}

function deleteMockToken(id: string): void {
  mockTokens = mockTokens.filter((token) => String(token.id) !== id);
}

/** mock 模式下解析一个管理面请求（无后端）。读返回 fixture，写返回 {ok:true}。 */
function resolveMgmtMock<T>(method: HttpMethod, path: string, body?: unknown): T {
  const clean = path.replace(/^\/api\/v1/, "").split("?")[0];
  if (method === "GET" && clean === "/admin/users/manage_list") {
    return cloneContractShape<T>(mgmtUsersFixture);
  }
  if (method === "GET" && clean === "/admin/channels") {
    return cloneContractShape<T>({ channels: mockChannels });
  }
  if (method === "GET" && clean === "/admin/tokens") {
    return cloneContractShape<T>({ tokens: mockTokens });
  }
  if (method === "GET" && clean === "/admin/groups") {
    return cloneContractShape<T>(MGMT_GROUPS);
  }
  if (method === "POST" && clean === "/admin/channels") {
    createMockChannel(body);
    return cloneContractShape<T>(MGMT_WRITE_OK);
  }
  const channelUpdate = clean.match(/^\/admin\/channels\/(.+)\/update$/);
  if (method === "POST" && channelUpdate) {
    updateMockChannel(decodePathId(channelUpdate[1]!), body);
    return cloneContractShape<T>(MGMT_WRITE_OK);
  }
  const channelDelete = clean.match(/^\/admin\/channels\/(.+)\/delete$/);
  if (method === "POST" && channelDelete) {
    deleteMockChannel(decodePathId(channelDelete[1]!));
    return cloneContractShape<T>(MGMT_WRITE_OK);
  }
  if (method === "POST" && /^\/admin\/channels\/(.+)\/test$/.test(clean)) {
    return cloneContractShape<T>({ ok: true, reachable: true, latency_ms: 42 } as unknown as T);
  }
  if (method === "POST" && clean === "/admin/tokens") {
    createMockToken(body);
    return cloneContractShape<T>(MGMT_WRITE_OK);
  }
  const tokenUpdate = clean.match(/^\/admin\/tokens\/(.+)\/update$/);
  if (method === "POST" && tokenUpdate) {
    updateMockToken(decodePathId(tokenUpdate[1]!), body);
    return cloneContractShape<T>(MGMT_WRITE_OK);
  }
  const tokenDelete = clean.match(/^\/admin\/tokens\/(.+)\/delete$/);
  if (method === "POST" && tokenDelete) {
    deleteMockToken(decodePathId(tokenDelete[1]!));
    return cloneContractShape<T>(MGMT_WRITE_OK);
  }
  // 其余用户管理写操作（创建 / 更新 / 密码 / 状态 / 角色 / 删除）统一 {ok:true}
  return cloneContractShape<T>(MGMT_WRITE_OK);
}

/**
 * 管理面统一请求：默认随 DEFAULT_MODE（mock / live）。
 * - mock：本地解析 fixture / {ok:true}，不起 server、不触网。
 * - live：附 `Authorization: Bearer`（复用 getToken），parse JSON，校验 response.ok。
 * 成功响应一律先过 assertNoPatientPhi（**非** assertNoPhi）再交还调用方。
 */
export async function requestMgmt<T>(
  method: HttpMethod,
  path: string,
  body?: unknown,
  options: MgmtRequestOptions = {},
): Promise<T> {
  const mode = options.mode ?? DEFAULT_MODE;
  const where = `${method} ${path}`;

  if (mode === "mock") {
    return assertNoPatientPhi(resolveMgmtMock<T>(method, path, body), where);
  }

  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const init: RequestInit = { method, headers };
  if (body !== undefined) {
    headers.set("Content-Type", "application/json");
    init.body = JSON.stringify(body);
  }

  const fetchImpl = options.fetchImpl ?? fetch;
  let response: Response;
  try {
    response = await fetchImpl(`${API_BASE}${path}`, init);
  } catch {
    throw makeApiError("api_network_error");
  }

  const bodyText = await readBody(response);
  if (!response.ok) {
    throw makeApiError("api_http_error");
  }
  const parsed = tryParseJson<T>(bodyText);
  if (parsed === undefined) {
    throw makeApiError("api_invalid_json");
  }

  return assertNoPatientPhi(parsed, where);
}

const mgmtPath = (id: number, suffix: string): string =>
  buildPath(`/admin/users/{id}/${suffix}`, { id: String(id) });

const mgmtResourcePath = (resource: "channels" | "tokens", id: string, suffix: string): string =>
  buildPath(`/admin/${resource}/{id}/${suffix}`, { id });

/** 拉取用户管理列表（运营人员·含 STAFF email；走患者-only 守卫）。 */
export function fetchMgmtUsers(options?: MgmtRequestOptions): Promise<MgmtUsersResponse> {
  return requestMgmt<MgmtUsersResponse>("GET", "/admin/users/manage_list", undefined, options);
}

/** 拉取分组清单。 */
export function fetchGroups(options?: MgmtRequestOptions): Promise<GroupsResponse> {
  return requestMgmt<GroupsResponse>("GET", "/admin/groups", undefined, options);
}

/** 拉取渠道管理列表。 */
export function fetchMgmtChannels(options?: MgmtRequestOptions): Promise<MgmtChannelsResponse> {
  return requestMgmt<MgmtChannelsResponse>("GET", "/admin/channels", undefined, options);
}

/** 新建渠道。 */
export function createChannel(body: MgmtChannelCreate, options?: MgmtRequestOptions): Promise<MgmtOk> {
  return requestMgmt<MgmtOk>("POST", "/admin/channels", body, options);
}

/** 编辑渠道。 */
export function updateChannel(
  id: string,
  body: MgmtChannelUpdate,
  options?: MgmtRequestOptions,
): Promise<MgmtOk> {
  return requestMgmt<MgmtOk>("POST", mgmtResourcePath("channels", id, "update"), body, options);
}

/** 删除渠道。 */
export function deleteChannel(id: string, options?: MgmtRequestOptions): Promise<MgmtOk> {
  return requestMgmt<MgmtOk>("POST", mgmtResourcePath("channels", id, "delete"), undefined, options);
}

/** 测试渠道。 */
export function testChannel(id: string, options?: MgmtRequestOptions): Promise<ChannelTestResult> {
  return requestMgmt<ChannelTestResult>(
    "POST",
    mgmtResourcePath("channels", id, "test"),
    undefined,
    options,
  );
}

/** 拉取接入应用令牌管理列表。 */
export function fetchMgmtTokens(options?: MgmtRequestOptions): Promise<MgmtTokensResponse> {
  return requestMgmt<MgmtTokensResponse>("GET", "/admin/tokens", undefined, options);
}

/** 新建接入应用令牌。 */
export function createToken(body: MgmtTokenCreate, options?: MgmtRequestOptions): Promise<MgmtOk> {
  return requestMgmt<MgmtOk>("POST", "/admin/tokens", body, options);
}

/** 编辑接入应用令牌（配额 / 数据等级 / 状态）。 */
export function updateToken(
  id: string,
  body: MgmtTokenUpdate,
  options?: MgmtRequestOptions,
): Promise<MgmtOk> {
  return requestMgmt<MgmtOk>("POST", mgmtResourcePath("tokens", id, "update"), body, options);
}

/** 删除接入应用令牌。 */
export function deleteToken(id: string, options?: MgmtRequestOptions): Promise<MgmtOk> {
  return requestMgmt<MgmtOk>("POST", mgmtResourcePath("tokens", id, "delete"), undefined, options);
}

/** 新建用户。 */
export function createUser(body: MgmtUserCreate, options?: MgmtRequestOptions): Promise<MgmtOk> {
  return requestMgmt<MgmtOk>("POST", "/admin/users", body, options);
}

/** 编辑用户（display_name / group / role）。 */
export function updateUser(
  id: number,
  body: MgmtUserUpdate,
  options?: MgmtRequestOptions,
): Promise<MgmtOk> {
  return requestMgmt<MgmtOk>("POST", mgmtPath(id, "update"), body, options);
}

/** 重置密码（运营人员线下交付，不发邮件）。 */
export function setUserPassword(
  id: number,
  body: MgmtUserPassword,
  options?: MgmtRequestOptions,
): Promise<MgmtOk> {
  return requestMgmt<MgmtOk>("POST", mgmtPath(id, "password"), body, options);
}

/** 启用 / 停用。 */
export function setUserStatus(
  id: number,
  body: MgmtUserStatus,
  options?: MgmtRequestOptions,
): Promise<MgmtOk> {
  return requestMgmt<MgmtOk>("POST", mgmtPath(id, "status"), body, options);
}

/** 升级 / 降级。 */
export function setUserRole(
  id: number,
  body: MgmtUserRole,
  options?: MgmtRequestOptions,
): Promise<MgmtOk> {
  return requestMgmt<MgmtOk>("POST", mgmtPath(id, "role"), body, options);
}

/** 删除用户。 */
export function deleteUser(id: number, options?: MgmtRequestOptions): Promise<MgmtOk> {
  return requestMgmt<MgmtOk>("POST", mgmtPath(id, "delete"), undefined, options);
}
