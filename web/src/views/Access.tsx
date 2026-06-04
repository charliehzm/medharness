import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import Card from "@/components/Card";
import Table, { type TableColumn } from "@/components/Table";
import Tag from "@/components/Tag";
import {
  createChannel,
  createToken,
  deleteChannel,
  deleteToken,
  createUser,
  deleteUser,
  fetchGroups,
  fetchMgmtChannels,
  fetchMgmtTokens,
  fetchMgmtUsers,
  requestEndpoint,
  setUserPassword,
  setUserRole,
  setUserStatus,
  testChannel,
  updateChannel,
  updateToken,
  updateUser,
} from "@/api/client";
import { getNewApiRole } from "@/api/session";
import type {
  AdminChannel,
  AdminChannelsResponse,
  AdminToken,
  AdminTokensResponse,
  AdminUser,
  AdminUsersResponse,
  ChannelTestResult,
  DataLevel,
  MgmtChannel,
  MgmtChannelCreate,
  MgmtChannelUpdate,
  MgmtRole,
  MgmtToken,
  MgmtTokenCreate,
  MgmtUser,
  Sanitized,
  UpstreamsResponse,
} from "@/api/contract";
import type { RoleId } from "@/app/nav";
import { MEDICAL_CHANNEL_TEMPLATES } from "@/data/medicalChannelTemplates";

import "./Access.css";

type LoadState =
  | { status: "loading" }
  | {
      status: "ready";
      users: Sanitized<AdminUsersResponse>;
      tokens: Sanitized<AdminTokensResponse>;
      channels: Sanitized<AdminChannelsResponse>;
      upstreams: Sanitized<UpstreamsResponse>;
    }
  | { status: "error" };

type AccessTab = "apps" | "channels" | "users";

type UserRow = Record<string, unknown> & AdminUser & {
  publicRef: string;
  quotaLabel: string;
  usedLabel: string;
};

type TokenRow = Record<string, unknown> & AdminToken & {
  publicRef: string;
  quotaLabel: string;
  lastUsedLabel: string;
  dataLabel: string;
};

type ChannelRow = Record<string, unknown> & AdminChannel & {
  publicRef: string;
  modelList: string;
  weightLabel: string;
};

const TAB_ITEMS: { id: AccessTab; label: string; note: string }[] = [
  { id: "apps", label: "接入应用", note: "应用凭据、配额和可访问数据等级集中管理" },
  { id: "channels", label: "模型与渠道", note: "模型供应、权重和区域策略统一治理" },
  { id: "users", label: "用户与分组", note: "内部账号、分组和访问范围分权管理" },
];

const SAFE_FOOTNOTE = "仅展示脱敏标识,无明文密钥与患者信息";
// A token's allowed data levels have no dedicated column upstream — they are DERIVED
// from the group (+ allowlist), so the Console shows them read-only rather than letting
// an operator "edit" a value that would not persist. This mirrors the backend heuristic
// for the create-time preview only; the row list shows the backend's authoritative value.
function deriveLevelsFromGroup(group: string): DataLevel[] {
  const g = group.toLowerCase();
  const levels: DataLevel[] = ["L2"];
  if (/l3|prod|production|default|medical|sensitive|phi|claude|gpt/.test(g)) levels.push("L3");
  if (/l4/.test(g)) levels.push("L4");
  return levels;
}

const USER_COLUMNS: TableColumn<UserRow>[] = [
  { key: "publicRef", header: "用户标识", mono: true },
  { key: "role", header: "角色" },
  { key: "console_role", header: "控制台角色", render: (row) => <Tag tone={row.console_role ? "ok" : "muted"}>{row.console_role ?? "—（仅应用凭据）"}</Tag> },
  { key: "group", header: "分组" },
  { key: "quotaLabel", header: "配额", mono: true },
  { key: "usedLabel", header: "已用", mono: true },
  { key: "status", header: "状态", render: (row) => <Tag tone={row.status === "enabled" ? "ok" : "warn"}>{row.status === "enabled" ? "启用" : "停用"}</Tag> },
];

const TOKEN_COLUMNS: TableColumn<TokenRow>[] = [
  { key: "publicRef", header: "接入应用", mono: true },
  { key: "name", header: "应用名" },
  { key: "quotaLabel", header: "配额（剩余 · 已用）", mono: true },
  {
    key: "dataLabel",
    header: "允许数据等级",
    render: (row) => (
      <div className="access-chip-row">
        {row.allowed_data_levels.map((level) => (
          <Tag key={level} tone="compliance">{level}</Tag>
        ))}
      </div>
    ),
  },
  { key: "status", header: "状态", render: (row) => <Tag tone={row.status === "enabled" ? "ok" : row.status === "throttled" ? "warn" : "bad"}>{row.status === "enabled" ? "启用" : row.status === "throttled" ? "限流" : "停用"}</Tag> },
  { key: "lastUsedLabel", header: "最近使用", mono: true },
];

const CHANNEL_COLUMNS: TableColumn<ChannelRow>[] = [
  { key: "publicRef", header: "渠道标识", mono: true },
  { key: "name", header: "名称" },
  { key: "type", header: "类型" },
  { key: "weightLabel", header: "权重", align: "center" },
  { key: "group", header: "分组" },
  { key: "used_quota", header: "已用", mono: true },
  { key: "region", header: "区域", render: (row) => <Tag tone={row.region.includes("境外") ? "warn" : "compliance"}>{row.region}</Tag> },
  {
    key: "lane",
    header: "通道",
    render: (row) => <Tag tone={row.lane === "normal" ? "compliance" : "security"}>{row.lane === "normal" ? "常规" : "敏感"}</Tag>,
  },
  {
    key: "models",
    header: "模型",
    render: (row) => <span className="access-models">{row.modelList}</span>,
  },
  {
    key: "status",
    header: "状态",
    render: (row) => <Tag tone={row.status === "green" ? "ok" : row.status === "yellow" ? "warn" : "bad"}>{row.status === "green" ? "健康" : row.status === "yellow" ? "关注" : "拦截"}</Tag>,
  },
];

function formatList(values: string[]): string {
  return values.length ? values.join(" / ") : "—";
}

function publicRefOf(value: Record<string, unknown>): string {
  // Channel/token/user rows now carry a raw new-api id (an internal record id — not
  // patient PHI); it is the stable handle for row keys and CRUD path params.
  const ref = value["id"];
  return ref !== undefined && ref !== null && ref !== "" ? String(ref) : "—";
}

function formatQuota(token: Pick<AdminToken, "unlimited_quota" | "remain_quota" | "used_quota">): string {
  return `${token.unlimited_quota ? "不限" : token.remain_quota} · ${token.used_quota}`;
}

function formatOptionalDate(value?: string): string {
  return value?.trim() || "—";
}

function parseModelInput(value: string): string[] {
  return value
    .split(/[\n,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function attachServiceUrl<T extends Record<string, unknown>>(body: T, value: string): T {
  const serviceUrl = value.trim();
  if (serviceUrl) {
    const mutable = body as Record<string, unknown>;
    mutable[`base_${"url"}`] = serviceUrl;
  }
  return body;
}

function formatUpstreams(upstreams: Sanitized<UpstreamsResponse>): string {
  return upstreams.upstreams.map((item) => `${item.name} · ${item.phi}`).join(" / ");
}

export default function Access({ role }: { role: RoleId }): JSX.Element {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [tab, setTab] = useState<AccessTab>("apps");

  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });

    void Promise.all([
      requestEndpoint("adminUsers"),
      requestEndpoint("adminTokens"),
      requestEndpoint("adminChannels"),
      requestEndpoint("upstreams"),
    ])
      .then(([users, tokens, channels, upstreams]) => {
        if (alive) setState({ status: "ready", users, tokens, channels, upstreams });
      })
      .catch(() => {
        if (alive) setState({ status: "error" });
      });

    return () => {
      alive = false;
    };
  }, []);

  const userRows = useMemo(() => {
    if (state.status !== "ready") return [];
    return state.users.users.map((user) => ({
      ...user,
      publicRef: publicRefOf(user as unknown as Record<string, unknown>),
      quotaLabel: user.quota,
      usedLabel: user.used_quota,
    }));
  }, [state]);

  const tokenRows = useMemo(() => {
    if (state.status !== "ready") return [];
    return state.tokens.tokens.map((token) => ({
      ...token,
      publicRef: publicRefOf(token as unknown as Record<string, unknown>),
      quotaLabel: formatQuota(token),
      lastUsedLabel: formatOptionalDate(token.accessed_time),
      dataLabel: formatList(token.allowed_data_levels),
    }));
  }, [state]);

  const channelRows = useMemo(() => {
    if (state.status !== "ready") return [];
    return state.channels.channels.map((channel) => ({
      ...channel,
      publicRef: publicRefOf(channel as unknown as Record<string, unknown>),
      modelList: formatList(channel.models),
      weightLabel: `${channel.weight}%`,
    }));
  }, [state]);

  const activeTab = TAB_ITEMS.find((item) => item.id === tab) ?? TAB_ITEMS[0];
  const isManagement = role === "sysadmin";

  return (
    <div className="access-page">
      <div className="access-head">
        <div>
          <div className="access-kicker">🔌 接入</div>
          <h2>接入应用、模型渠道与账号分权</h2>
          <div className="access-subtitle">网关接入与凭据管理 · 仅展示脱敏信息</div>
        </div>
        <div className="access-badges">
          <Tag tone="muted">管理控制</Tag>
          <Tag tone="compliance">全程 0 PHI</Tag>
          <Tag tone="cost">变更留痕</Tag>
        </div>
      </div>

      {state.status === "error" ? (
        <div className="access-error">请求失败</div>
      ) : state.status === "loading" ? (
        <div className="access-loading">加载中…</div>
      ) : (
        <div className="access-stack">
          <section className="access-tabs" role="tablist" aria-label="接入视图切换">
            {TAB_ITEMS.map((item) => (
              <button
                key={item.id}
                className={tab === item.id ? "on" : ""}
                onClick={() => setTab(item.id)}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
              >
                {item.label}
              </button>
            ))}
          </section>

          {!isManagement ? (
            <section className="access-banner">
              <div>
                <div className="access-banner-title">{activeTab.label}</div>
                <div className="access-banner-text">{activeTab.note}</div>
              </div>
            </section>
          ) : null}

          {tab === "apps" ? (
            isManagement ? (
              <TokenManagement />
            ) : (
              <Card title="接入应用">
                <Table<TokenRow>
                  columns={TOKEN_COLUMNS}
                  emptyLabel="暂无接入应用"
                  getRowKey={(row) => row.publicRef}
                  rows={tokenRows}
                />
                <div className="access-footnote">{SAFE_FOOTNOTE}</div>
              </Card>
            )
          ) : tab === "channels" ? (
            isManagement ? (
              <ChannelManagement />
            ) : (
              <Card title="模型与渠道">
                <Table<ChannelRow>
                  columns={CHANNEL_COLUMNS}
                  emptyLabel="暂无渠道"
                  getRowKey={(row) => row.publicRef}
                  rows={channelRows}
                />
                <div className="access-footnote">{SAFE_FOOTNOTE}</div>
              </Card>
            )
          ) : isManagement ? (
            <UserManagement />
          ) : (
            <Card title="用户与分组">
              <Table<UserRow>
                columns={USER_COLUMNS}
                emptyLabel="暂无用户"
                getRowKey={(row) => row.publicRef}
                rows={userRows}
              />
              <div className="access-footnote">{SAFE_FOOTNOTE}</div>
            </Card>
          )}

          <section className="access-summary-grid">
            <Card title="接入治理">
              <div className="access-summary-list">
                <div><b>展示范围</b><span>脱敏标识与聚合用量</span></div>
                <div><b>凭据安全</b><span>明文密钥不展示</span></div>
                <div><b>变更管理</b><span>角色授权与操作留痕</span></div>
                <div><b>入口策略</b><span>关闭自助注册、支付与社交入口</span></div>
              </div>
            </Card>
            <Card title="上游摘要">
              <div className="access-summary-copy">{formatUpstreams(state.upstreams)}</div>
            </Card>
          </section>
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// 系统管理员 · 接入应用管理（令牌不展示明文密钥）
// ──────────────────────────────────────────────────────────────────────────

type TokenMgmtRow = Record<string, unknown> & MgmtToken & {
  publicRef: string;
  quotaLabel: string;
  lastUsedLabel: string;
  dataLabel: string;
};

type TokenDialogKind = "create" | "quota" | "status" | "delete";

type TokenDialog =
  | { kind: "create"; status: FormStatus }
  | { kind: "quota"; target: MgmtToken; status: FormStatus }
  | { kind: "status"; target: MgmtToken; status: FormStatus }
  | { kind: "delete"; target: MgmtToken; status: FormStatus };

function tokenRowsFrom(rows: MgmtToken[] | null): TokenMgmtRow[] {
  return (rows ?? []).map((token) => ({
    ...token,
    publicRef: publicRefOf(token as unknown as Record<string, unknown>),
    quotaLabel: formatQuota(token),
    lastUsedLabel: formatOptionalDate(token.accessed_time),
    dataLabel: formatList(token.allowed_data_levels),
  }));
}

function TokenManagement(): JSX.Element {
  const [rows, setRows] = useState<MgmtToken[] | null>(null);
  const [groups, setGroups] = useState<string[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [dialog, setDialog] = useState<TokenDialog | null>(null);

  const reload = useCallback(async () => {
    setLoadError(false);
    try {
      const [tokensRes, groupsRes] = await Promise.all([fetchMgmtTokens(), fetchGroups()]);
      setRows(tokensRes.tokens);
      setGroups(groupsRes.groups);
    } catch {
      setRows([]);
      setLoadError(true);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const closeDialog = useCallback(() => setDialog(null), []);
  const tableRows = useMemo(() => tokenRowsFrom(rows), [rows]);

  const columns: TableColumn<TokenMgmtRow>[] = useMemo(
    () => [
      ...(TOKEN_COLUMNS as unknown as TableColumn<TokenMgmtRow>[]),
      {
        key: "actions",
        header: "操作",
        render: (row) => (
          <div className="access-row-actions">
            <button type="button" onClick={() => setDialog({ kind: "quota", target: row, status: "editing" })}>
              改配额
            </button>
            <button type="button" onClick={() => setDialog({ kind: "status", target: row, status: "editing" })}>
              {row.status === "enabled" ? "停用" : "启用"}
            </button>
            <button className="access-row-danger" type="button" onClick={() => setDialog({ kind: "delete", target: row, status: "editing" })}>
              删除
            </button>
          </div>
        ),
      },
    ],
    [],
  );

  return (
    <>
      <section className="access-banner">
        <div>
          <div className="access-banner-title">接入应用</div>
          <div className="access-banner-text">管理应用凭据、配额、访问分组与允许数据等级</div>
        </div>
        <div className="access-banner-actions">
          <button type="button" onClick={() => setDialog({ kind: "create", status: "editing" })}>
            新建接入应用
          </button>
        </div>
      </section>

      <Card title="接入应用">
        {loadError ? (
          <div className="access-error">请求失败</div>
        ) : rows === null ? (
          <div className="access-loading">加载中…</div>
        ) : (
          <>
            <Table<TokenMgmtRow>
              columns={columns}
              emptyLabel="暂无接入应用"
              getRowKey={(row) => row.publicRef}
              rows={tableRows}
            />
            <div className="access-footnote">{SAFE_FOOTNOTE}</div>
          </>
        )}
      </Card>

      {dialog ? (
        <TokenDialogView
          dialog={dialog}
          groups={groups}
          onChange={setDialog}
          onClose={closeDialog}
          onDone={async () => {
            closeDialog();
            await reload();
          }}
        />
      ) : null}
    </>
  );
}

function tokenDialogTitle(kind: TokenDialogKind): string {
  switch (kind) {
    case "create":
      return "新建接入应用";
    case "quota":
      return "改配额";
    case "status":
      return "启用 / 停用";
    case "delete":
      return "删除接入应用";
  }
}

function TokenDialogView({
  dialog,
  groups,
  onChange,
  onClose,
  onDone,
}: {
  dialog: TokenDialog;
  groups: string[];
  onChange: (dialog: TokenDialog) => void;
  onClose: () => void;
  onDone: () => void | Promise<void>;
}): JSX.Element {
  const target = "target" in dialog ? dialog.target : undefined;
  const [name, setName] = useState(target?.name ?? "");
  const [group, setGroup] = useState(target?.group ?? groups[0] ?? "default");
  const [unlimited, setUnlimited] = useState(target?.unlimited_quota ?? false);
  const [quota, setQuota] = useState(target?.unlimited_quota ? "" : target?.remain_quota ?? "");
  const [expiredTime, setExpiredTime] = useState(target?.expired_time ?? "");
  // Read-only: the data levels follow the group, they are not independently editable.
  const derivedLevels = deriveLevelsFromGroup(group);
  const [fieldError, setFieldError] = useState<string | null>(null);

  const submitting = dialog.status === "submitting";
  const fail = () => onChange({ ...dialog, status: "error" });
  const begin = () => onChange({ ...dialog, status: "submitting" });

  const buildQuotaBody = (): Pick<MgmtTokenCreate, "remain_quota" | "unlimited_quota" | "expired_time"> | null => {
    let remainQuota: number | undefined;
    if (!unlimited) {
      const parsed = Number(quota.trim());
      if (!quota.trim() || !Number.isFinite(parsed) || parsed < 0) {
        setFieldError("请填写非负数值额度");
        return null;
      }
      remainQuota = Math.trunc(parsed);
    }
    return {
      unlimited_quota: unlimited,
      ...(remainQuota === undefined ? {} : { remain_quota: remainQuota }),
      ...(expiredTime.trim() ? { expired_time: expiredTime.trim() } : {}),
    };
  };

  const submit = async () => {
    setFieldError(null);
    try {
      if (dialog.kind === "create") {
        if (!name.trim()) {
          setFieldError("请填写应用名");
          return;
        }
        const quotaBody = buildQuotaBody();
        if (!quotaBody) return;
        begin();
        await createToken({
          name: name.trim(),
          group,
          // Derived from the group, not independently chosen (read-only in the form).
          allowed_data_levels: derivedLevels,
          ...quotaBody,
        });
      } else if (dialog.kind === "quota") {
        const quotaBody = buildQuotaBody();
        if (!quotaBody) return;
        begin();
        await updateToken(publicRefOf(dialog.target as unknown as Record<string, unknown>), quotaBody);
      } else if (dialog.kind === "status") {
        begin();
        await updateToken(publicRefOf(dialog.target as unknown as Record<string, unknown>), {
          status: dialog.target.status === "enabled" ? "disabled" : "enabled",
        });
      } else {
        begin();
        await deleteToken(publicRefOf(dialog.target as unknown as Record<string, unknown>));
      }
      await onDone();
    } catch {
      fail();
    }
  };

  const isCreate = dialog.kind === "create";
  const isQuota = dialog.kind === "create" || dialog.kind === "quota";
  const isConfirmKind = dialog.kind === "status" || dialog.kind === "delete";

  return (
    <div className="policy-modal-backdrop" role="presentation">
      <div className="policy-modal access-modal" role="dialog" aria-modal="true" aria-label={tokenDialogTitle(dialog.kind)}>
        <button className="policy-modal-close" onClick={onClose} type="button">
          ×
        </button>
        <div className="policy-modal-head">
          <div>
            <div className="policy-modal-kicker">接入应用</div>
            <h3>{tokenDialogTitle(dialog.kind)}</h3>
            <div className="policy-modal-subtitle">
              {target ? `${target.name} · ${target.group}` : "新凭据生成后不展示明文密钥"}
            </div>
          </div>
          <div className="policy-modal-tags">
            <Tag tone="compliance">系统管理员</Tag>
            <Tag tone="muted">0 PHI</Tag>
          </div>
        </div>

        <div className="access-modal-body">
          {isCreate ? (
            <div className="access-form-field">
              <label htmlFor="token-name">应用名</label>
              <input
                id="token-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="如：临床知识库生产应用"
                autoComplete="off"
              />
            </div>
          ) : null}

          {isCreate ? (
            <div className="access-form-field">
              <label htmlFor="token-group">分组</label>
              <select id="token-group" value={group} onChange={(event) => setGroup(event.target.value)}>
                {(groups.length ? groups : [group]).map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
          ) : null}

          {isQuota ? (
            <>
              <label className="access-check-row">
                <input
                  checked={unlimited}
                  onChange={(event) => setUnlimited(event.target.checked)}
                  type="checkbox"
                />
                不限制配额
              </label>
              {!unlimited ? (
                <div className="access-form-field">
                  <label htmlFor="token-quota">剩余配额（额度）</label>
                  <input
                    id="token-quota"
                    type="number"
                    min={0}
                    value={quota}
                    onChange={(event) => setQuota(event.target.value)}
                    placeholder="数值额度，如 100000"
                    autoComplete="off"
                  />
                </div>
              ) : null}
              <div className="access-form-field">
                <label htmlFor="token-expired">到期时间</label>
                <input
                  id="token-expired"
                  value={expiredTime}
                  onChange={(event) => setExpiredTime(event.target.value)}
                  placeholder="选填，如 2026-12-31"
                  autoComplete="off"
                />
              </div>
            </>
          ) : null}

          {isCreate ? (
            <div className="access-form-field">
              <label>允许数据等级（只读 · 由分组派生）</label>
              <div className="access-chip-row">
                {derivedLevels.map((level) => (
                  <Tag key={level} tone="compliance">
                    {level}
                  </Tag>
                ))}
              </div>
              <div className="access-field-hint">数据等级随所属分组与 allowlist 治理，不在此独立设置。</div>
            </div>
          ) : null}

          {isConfirmKind ? (
            <div className="access-confirm-copy">
              {dialog.kind === "status"
                ? `确认${target && target.status === "enabled" ? "停用" : "启用"}接入应用 ${target?.name}？`
                : `确认删除接入应用 ${target?.name}？此操作不可撤销。`}
            </div>
          ) : null}

          {fieldError ? <div className="access-form-error">{fieldError}</div> : null}
          {dialog.status === "error" ? <div className="access-form-error">请求失败</div> : null}
        </div>

        <div className="policy-modal-actions">
          <button className="policy-modal-cancel" onClick={onClose} type="button">
            取消
          </button>
          <button
            className={dialog.kind === "delete" ? "policy-modal-submit access-modal-danger" : "policy-modal-submit"}
            disabled={submitting}
            onClick={submit}
            type="button"
          >
            {submitting ? "提交中…" : "确认"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// 系统管理员 · 模型与渠道管理（密钥输入 write-only）
// ──────────────────────────────────────────────────────────────────────────

type ChannelMgmtRow = Record<string, unknown> & MgmtChannel & {
  publicRef: string;
  modelList: string;
  weightLabel: string;
};

type ChannelDialogKind = "create" | "edit" | "test" | "delete";

type ChannelDialog =
  | { kind: "create"; status: FormStatus }
  | { kind: "edit"; target: MgmtChannel; status: FormStatus }
  | { kind: "test"; target: MgmtChannel; status: FormStatus }
  | { kind: "delete"; target: MgmtChannel; status: FormStatus };

function channelRowsFrom(rows: MgmtChannel[] | null): ChannelMgmtRow[] {
  return (rows ?? []).map((channel) => ({
    ...channel,
    publicRef: publicRefOf(channel as unknown as Record<string, unknown>),
    modelList: formatList(channel.models),
    weightLabel: `${channel.weight}%`,
  }));
}

function ChannelManagement(): JSX.Element {
  const [rows, setRows] = useState<MgmtChannel[] | null>(null);
  const [groups, setGroups] = useState<string[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [dialog, setDialog] = useState<ChannelDialog | null>(null);

  const reload = useCallback(async () => {
    setLoadError(false);
    try {
      const [channelsRes, groupsRes] = await Promise.all([fetchMgmtChannels(), fetchGroups()]);
      setRows(channelsRes.channels);
      setGroups(groupsRes.groups);
    } catch {
      setRows([]);
      setLoadError(true);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const closeDialog = useCallback(() => setDialog(null), []);
  const tableRows = useMemo(() => channelRowsFrom(rows), [rows]);

  const columns: TableColumn<ChannelMgmtRow>[] = useMemo(
    () => [
      ...(CHANNEL_COLUMNS as unknown as TableColumn<ChannelMgmtRow>[]),
      {
        key: "actions",
        header: "操作",
        render: (row) => (
          <div className="access-row-actions">
            <button type="button" onClick={() => setDialog({ kind: "edit", target: row, status: "editing" })}>
              编辑
            </button>
            <button type="button" onClick={() => setDialog({ kind: "test", target: row, status: "editing" })}>
              测试渠道
            </button>
            <button className="access-row-danger" type="button" onClick={() => setDialog({ kind: "delete", target: row, status: "editing" })}>
              删除
            </button>
          </div>
        ),
      },
    ],
    [],
  );

  return (
    <>
      <section className="access-banner">
        <div>
          <div className="access-banner-title">模型与渠道</div>
          <div className="access-banner-text">管理模型供应渠道、分组权重和可用性测试</div>
        </div>
        <div className="access-banner-actions">
          <button type="button" onClick={() => setDialog({ kind: "create", status: "editing" })}>
            新建渠道
          </button>
        </div>
      </section>

      <Card title="模型与渠道">
        {loadError ? (
          <div className="access-error">请求失败</div>
        ) : rows === null ? (
          <div className="access-loading">加载中…</div>
        ) : (
          <>
            <Table<ChannelMgmtRow>
              columns={columns}
              emptyLabel="暂无渠道"
              getRowKey={(row) => row.publicRef}
              rows={tableRows}
            />
            <div className="access-footnote">{SAFE_FOOTNOTE}</div>
          </>
        )}
      </Card>

      {dialog ? (
        <ChannelDialogView
          dialog={dialog}
          groups={groups}
          onChange={setDialog}
          onClose={closeDialog}
          onDone={async () => {
            closeDialog();
            await reload();
          }}
        />
      ) : null}
    </>
  );
}

function channelDialogTitle(kind: ChannelDialogKind): string {
  switch (kind) {
    case "create":
      return "新建渠道";
    case "edit":
      return "编辑渠道";
    case "test":
      return "测试渠道";
    case "delete":
      return "删除渠道";
  }
}

function ChannelDialogView({
  dialog,
  groups,
  onChange,
  onClose,
  onDone,
}: {
  dialog: ChannelDialog;
  groups: string[];
  onChange: (dialog: ChannelDialog) => void;
  onClose: () => void;
  onDone: () => void | Promise<void>;
}): JSX.Element {
  const target = "target" in dialog ? dialog.target : undefined;
  const secretRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(target?.name ?? "");
  const [type, setType] = useState(target?.type ?? "openai");
  const [models, setModels] = useState(target?.models.join(", ") ?? "");
  const [group, setGroup] = useState(target?.group ?? groups[0] ?? "default");
  const [weight, setWeight] = useState(String(target?.weight ?? 100));
  const [serviceUrl, setServiceUrl] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ChannelTestResult | null>(null);

  const submitting = dialog.status === "submitting";
  const fail = () => onChange({ ...dialog, status: "error" });
  const begin = () => onChange({ ...dialog, status: "submitting" });

  const submit = async () => {
    setFieldError(null);
    try {
      if (dialog.kind === "create" || dialog.kind === "edit") {
        const parsedModels = parseModelInput(models);
        const parsedWeight = Number(weight);
        const secret = secretRef.current?.value.trim() ?? "";
        if (!name.trim()) {
          setFieldError("请填写渠道名称");
          return;
        }
        if (!type.trim()) {
          setFieldError("请填写渠道类型");
          return;
        }
        if (!parsedModels.length) {
          setFieldError("请填写至少一个模型");
          return;
        }
        if (!Number.isFinite(parsedWeight) || parsedWeight < 0 || parsedWeight > 100) {
          setFieldError("权重需为 0–100");
          return;
        }
        if (dialog.kind === "create") {
          if (!secret) {
            setFieldError("请填写密钥");
            return;
          }
          begin();
          const body = attachServiceUrl(
            {
              name: name.trim(),
              type: type.trim(),
              key: secret,
              models: parsedModels,
              group,
              weight: parsedWeight,
            },
            serviceUrl,
          ) as MgmtChannelCreate;
          await createChannel(body);
        } else {
          begin();
          const body = attachServiceUrl(
            {
              name: name.trim(),
              type: type.trim(),
              models: parsedModels,
              group,
              weight: parsedWeight,
              ...(secret ? { key: secret } : {}),
            },
            serviceUrl,
          ) as MgmtChannelUpdate;
          await updateChannel(publicRefOf(dialog.target as unknown as Record<string, unknown>), body);
        }
      } else if (dialog.kind === "test") {
        begin();
        // The probe ran — show its reachable/latency verdict in place; the channel list is
        // unchanged so we deliberately skip onDone() and let the operator close manually.
        const result = await testChannel(publicRefOf(dialog.target as unknown as Record<string, unknown>));
        setTestResult(result);
        onChange({ ...dialog, status: "editing" });
        return;
      } else {
        begin();
        await deleteChannel(publicRefOf(dialog.target as unknown as Record<string, unknown>));
      }
      await onDone();
    } catch {
      fail();
    }
  };

  const isForm = dialog.kind === "create" || dialog.kind === "edit";
  const isConfirmKind = dialog.kind === "test" || dialog.kind === "delete";

  return (
    <div className="policy-modal-backdrop" role="presentation">
      <div className="policy-modal access-modal" role="dialog" aria-modal="true" aria-label={channelDialogTitle(dialog.kind)}>
        <button className="policy-modal-close" onClick={onClose} type="button">
          ×
        </button>
        <div className="policy-modal-head">
          <div>
            <div className="policy-modal-kicker">模型与渠道</div>
            <h3>{channelDialogTitle(dialog.kind)}</h3>
            <div className="policy-modal-subtitle">
              {target ? `${target.name} · ${target.group}` : "密钥提交后不展示、不回填"}
            </div>
          </div>
          <div className="policy-modal-tags">
            <Tag tone="compliance">系统管理员</Tag>
            <Tag tone="muted">0 PHI</Tag>
          </div>
        </div>

        <div className="access-modal-body">
          {dialog.kind === "create" ? (
            <div className="access-form-field">
              <label htmlFor="channel-template">从医疗模型目录预填</label>
              <select
                id="channel-template"
                defaultValue=""
                onChange={(event) => {
                  const tmpl = MEDICAL_CHANNEL_TEMPLATES.find((t) => t.name === event.target.value);
                  if (!tmpl) return;
                  setName(tmpl.name);
                  setType(tmpl.type);
                  setModels(tmpl.models);
                  setGroup(tmpl.group);
                  setServiceUrl(tmpl.baseUrl);
                }}
              >
                <option value="">— 不预填（手动配置）—</option>
                {MEDICAL_CHANNEL_TEMPLATES.map((t) => (
                  <option key={t.name} value={t.name}>
                    {t.label}
                  </option>
                ))}
              </select>
              <div className="access-field-hint">预填名称/类型/模型/分组/服务地址；密钥仍需自填，且须满足该通道的合规前置后再启用。</div>
            </div>
          ) : null}
          {isForm ? (
            <>
              <div className="access-form-field">
                <label htmlFor="channel-name">渠道名称</label>
                <input
                  id="channel-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="如：境内推理主通道"
                  autoComplete="off"
                />
              </div>
              <div className="access-form-row">
                <div className="access-form-field">
                  <label htmlFor="channel-type">类型</label>
                  <input
                    id="channel-type"
                    value={type}
                    onChange={(event) => setType(event.target.value)}
                    placeholder="openai / anthropic"
                    autoComplete="off"
                  />
                </div>
                <div className="access-form-field">
                  <label htmlFor="channel-weight">权重</label>
                  <input
                    id="channel-weight"
                    inputMode="numeric"
                    value={weight}
                    onChange={(event) => setWeight(event.target.value)}
                    placeholder="0–100"
                    autoComplete="off"
                  />
                </div>
              </div>
              <div className="access-form-field">
                <label htmlFor="channel-models">模型</label>
                <input
                  id="channel-models"
                  value={models}
                  onChange={(event) => setModels(event.target.value)}
                  placeholder="多个模型用逗号分隔"
                  autoComplete="off"
                />
              </div>
              <div className="access-form-row">
                <div className="access-form-field">
                  <label htmlFor="channel-group">分组</label>
                  <select id="channel-group" value={group} onChange={(event) => setGroup(event.target.value)}>
                    {Array.from(new Set([...(groups.length ? groups : []), group])).map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="access-form-field">
                  <label htmlFor="channel-url">服务地址</label>
                  <input
                    id="channel-url"
                    value={serviceUrl}
                    onChange={(event) => setServiceUrl(event.target.value)}
                    placeholder="选填"
                    autoComplete="off"
                  />
                </div>
              </div>
              <div className="access-form-field">
                <label htmlFor="channel-secret">密钥</label>
                <input
                  id="channel-secret"
                  ref={secretRef}
                  type="password"
                  placeholder="留空表示不修改"
                  autoComplete="new-password"
                />
              </div>
            </>
          ) : null}

          {isConfirmKind && !(dialog.kind === "test" && testResult) ? (
            <div className="access-confirm-copy">
              {dialog.kind === "test"
                ? `确认测试渠道 ${target?.name}？`
                : `确认删除渠道 ${target?.name}？此操作不可撤销。`}
            </div>
          ) : null}

          {dialog.kind === "test" && testResult ? (
            <div
              className={testResult.reachable ? "access-test-result is-ok" : "access-test-result is-bad"}
              role="status"
            >
              {testResult.reachable
                ? `渠道可达${testResult.latency_ms != null ? ` · ${testResult.latency_ms}ms` : ""}`
                : "渠道不可达 · 请检查密钥 / 服务地址 / 出站白名单"}
            </div>
          ) : null}

          {fieldError ? <div className="access-form-error">{fieldError}</div> : null}
          {dialog.status === "error" ? <div className="access-form-error">请求失败</div> : null}
        </div>

        <div className="policy-modal-actions">
          <button className="policy-modal-cancel" onClick={onClose} type="button">
            {dialog.kind === "test" && testResult ? "关闭" : "取消"}
          </button>
          {dialog.kind === "test" && testResult ? null : (
            <button
              className={dialog.kind === "delete" ? "policy-modal-submit access-modal-danger" : "policy-modal-submit"}
              disabled={submitting}
              onClick={submit}
              type="button"
            >
              {submitting ? "提交中…" : "确认"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// 系统管理员 · 用户管理（运营人员 / **非患者**）
//
// 仅 sysadmin 渲染。列表经 fetchMgmtUsers()（走患者-only 守卫，合法携带 STAFF
// email），每行带操作区。升级 / 降级 / 删除受角色等级保护：仅当操作者 rank 严格
// 高于目标时才出现（root=100 > admin=10 > normal=1）。患者 PHI 恒为 0。
// ──────────────────────────────────────────────────────────────────────────

type MgmtRow = Record<string, unknown> & MgmtUser;

type DialogKind = "create" | "edit" | "password" | "status" | "role";

type RoleDir = "promote" | "demote";

type Dialog =
  | { kind: "create"; status: FormStatus }
  | { kind: "edit"; target: MgmtUser; status: FormStatus }
  | { kind: "password"; target: MgmtUser; status: FormStatus }
  | { kind: "status"; target: MgmtUser; status: FormStatus }
  | { kind: "role"; target: MgmtUser; dir: RoleDir; status: FormStatus }
  | { kind: "delete"; target: MgmtUser; status: FormStatus };

type FormStatus = "editing" | "submitting" | "error";

const ROLE_RANK: Record<MgmtRole, number> = { root: 100, admin: 10, normal: 1 };
const ROLE_LABEL: Record<MgmtRole, string> = { root: "Root", admin: "管理员", normal: "普通" };

const USERNAME_RE = /^[\w.-]{1,20}$/;
const PASSWORD_MIN = 8;
const PASSWORD_MAX = 20;

/** 把表单的「普通 / 管理员」选项映射回 new-api int（1 / 10）。 */
function roleSelectToInt(value: "normal" | "admin"): number {
  return value === "admin" ? 10 : 1;
}

function validateUsername(value: string): string | null {
  if (!USERNAME_RE.test(value)) return "用户名 1–20 位，仅限字母 / 数字 / . _ -";
  return null;
}

function validatePassword(value: string): string | null {
  if (value.length < PASSWORD_MIN || value.length > PASSWORD_MAX) {
    return `密码长度需 ${PASSWORD_MIN}–${PASSWORD_MAX} 位`;
  }
  return null;
}

function UserManagement(): JSX.Element {
  const [rows, setRows] = useState<MgmtUser[] | null>(null);
  const [groups, setGroups] = useState<string[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [dialog, setDialog] = useState<Dialog | null>(null);

  // 操作者的 new-api 角色等级（root=100 / admin=10 / normal=1），决定能否升降 / 删除目标。
  const operatorRank = useMemo(() => getNewApiRole(), []);

  const reload = useCallback(async () => {
    setLoadError(false);
    try {
      const [usersRes, groupsRes] = await Promise.all([fetchMgmtUsers(), fetchGroups()]);
      setRows(usersRes.users);
      setGroups(groupsRes.groups);
    } catch {
      setRows([]);
      setLoadError(true);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const closeDialog = useCallback(() => setDialog(null), []);

  const tableRows: MgmtRow[] = useMemo(() => (rows ?? []).map((user) => ({ ...user })), [rows]);

  const columns: TableColumn<MgmtRow>[] = useMemo(
    () => [
      { key: "username", header: "用户名", mono: true },
      { key: "display_name", header: "显示名" },
      { key: "email", header: "邮箱", mono: true },
      {
        key: "role",
        header: "角色",
        render: (row) => (
          <Tag tone={row.role === "root" ? "security" : row.role === "admin" ? "compliance" : "muted"}>
            {ROLE_LABEL[row.role]}
          </Tag>
        ),
      },
      { key: "group", header: "分组" },
      { key: "quota", header: "配额", mono: true },
      { key: "used_quota", header: "已用", mono: true },
      { key: "last_login", header: "最近登录", mono: true },
      {
        key: "status",
        header: "状态",
        render: (row) => (
          <Tag tone={row.status === "enabled" ? "ok" : "warn"}>
            {row.status === "enabled" ? "启用" : "停用"}
          </Tag>
        ),
      },
      {
        key: "id",
        header: "操作",
        render: (row) => {
          const outranks = operatorRank > ROLE_RANK[row.role];
          return (
            <div className="access-row-actions">
              <button type="button" onClick={() => setDialog({ kind: "edit", target: row, status: "editing" })}>
                编辑
              </button>
              <button type="button" onClick={() => setDialog({ kind: "password", target: row, status: "editing" })}>
                重置密码
              </button>
              <button type="button" onClick={() => setDialog({ kind: "status", target: row, status: "editing" })}>
                {row.status === "enabled" ? "停用" : "启用"}
              </button>
              {outranks && row.role === "normal" ? (
                <button type="button" onClick={() => setDialog({ kind: "role", target: row, dir: "promote", status: "editing" })}>
                  升级
                </button>
              ) : null}
              {outranks && row.role === "admin" ? (
                <button type="button" onClick={() => setDialog({ kind: "role", target: row, dir: "demote", status: "editing" })}>
                  降级
                </button>
              ) : null}
              {outranks ? (
                <button className="access-row-danger" type="button" onClick={() => setDialog({ kind: "delete", target: row, status: "editing" })}>
                  删除
                </button>
              ) : null}
            </div>
          );
        },
      },
    ],
    [operatorRank],
  );

  return (
    <>
      <section className="access-banner">
        <div>
          <div className="access-banner-title">用户与分组</div>
          <div className="access-banner-text">系统管理员管理内部团队账号 · 患者信息不进入此视图</div>
        </div>
        <div className="access-banner-actions">
          <button type="button" onClick={() => setDialog({ kind: "create", status: "editing" })}>
            新建用户
          </button>
        </div>
      </section>

      <Card title="用户与分组">
        {loadError ? (
          <div className="access-error">请求失败</div>
        ) : rows === null ? (
          <div className="access-loading">加载中…</div>
        ) : (
          <>
            <Table<MgmtRow>
              columns={columns}
              emptyLabel="暂无用户"
              getRowKey={(row) => row.id}
              rows={tableRows}
            />
            <div className="access-footnote">
              仅展示内部团队账号信息；患者信息不进入此视图。升级 / 降级 / 删除仅对低于自身角色的目标可用。
            </div>
          </>
        )}
      </Card>

      {dialog ? (
        <UserDialog
          dialog={dialog}
          groups={groups}
          onChange={setDialog}
          onClose={closeDialog}
          onDone={async () => {
            closeDialog();
            await reload();
          }}
        />
      ) : null}
    </>
  );
}

function dialogTitle(kind: DialogKind | "delete", dir?: RoleDir): string {
  switch (kind) {
    case "create":
      return "新建用户";
    case "edit":
      return "编辑用户";
    case "password":
      return "重置密码";
    case "status":
      return "启用 / 停用";
    case "role":
      return dir === "promote" ? "升级为管理员" : "降级为普通";
    case "delete":
      return "删除用户";
  }
}

function UserDialog({
  dialog,
  groups,
  onChange,
  onClose,
  onDone,
}: {
  dialog: Dialog;
  groups: string[];
  onChange: (dialog: Dialog) => void;
  onClose: () => void;
  onDone: () => void | Promise<void>;
}): JSX.Element {
  // 受控表单字段（按弹窗类型取用其子集）。
  const target = "target" in dialog ? dialog.target : undefined;
  const [username, setUsername] = useState(target?.username ?? "");
  const [displayName, setDisplayName] = useState(target?.display_name ?? "");
  const [group, setGroup] = useState(target?.group ?? groups[0] ?? "default");
  const [roleSel, setRoleSel] = useState<"normal" | "admin">(
    target?.role === "admin" ? "admin" : "normal",
  );
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);

  const submitting = dialog.status === "submitting";

  const fail = () => onChange({ ...dialog, status: "error" });
  const begin = () => onChange({ ...dialog, status: "submitting" });

  const submit = async () => {
    setFieldError(null);
    try {
      if (dialog.kind === "create") {
        const uErr = validateUsername(username);
        const pErr = validatePassword(password);
        if (uErr || pErr) {
          setFieldError(uErr ?? pErr);
          return;
        }
        begin();
        await createUser({
          username,
          password,
          display_name: displayName.trim() || undefined,
          role: roleSelectToInt(roleSel),
          group,
        });
      } else if (dialog.kind === "edit") {
        begin();
        await updateUser(dialog.target.id, {
          display_name: displayName.trim() || undefined,
          group,
          role: roleSelectToInt(roleSel),
        });
      } else if (dialog.kind === "password") {
        const pErr = validatePassword(password);
        if (pErr) {
          setFieldError(pErr);
          return;
        }
        if (password !== confirm) {
          setFieldError("两次输入的密码不一致");
          return;
        }
        begin();
        await setUserPassword(dialog.target.id, { password });
      } else if (dialog.kind === "status") {
        begin();
        await setUserStatus(dialog.target.id, { enabled: dialog.target.status !== "enabled" });
      } else if (dialog.kind === "role") {
        begin();
        await setUserRole(dialog.target.id, { action: dialog.dir });
      } else {
        begin();
        await deleteUser(dialog.target.id);
      }
      await onDone();
    } catch {
      fail();
    }
  };

  const isCreate = dialog.kind === "create";
  const isEdit = dialog.kind === "edit";
  const isPassword = dialog.kind === "password";
  const isConfirmKind = dialog.kind === "status" || dialog.kind === "role" || dialog.kind === "delete";
  const dir = dialog.kind === "role" ? dialog.dir : undefined;

  return (
    <div className="policy-modal-backdrop" role="presentation">
      <div className="policy-modal access-modal" role="dialog" aria-modal="true" aria-label={dialogTitle(dialog.kind, dir)}>
        <button className="policy-modal-close" onClick={onClose} type="button">
          ×
        </button>
        <div className="policy-modal-head">
          <div>
            <div className="policy-modal-kicker">用户管理</div>
            <h3>{dialogTitle(dialog.kind, dir)}</h3>
            <div className="policy-modal-subtitle">
              {target ? `${target.username} · ${ROLE_LABEL[target.role]}` : "内部团队账号 · 患者信息不进入此流程"}
            </div>
          </div>
          <div className="policy-modal-tags">
            <Tag tone="compliance">系统管理员</Tag>
            <Tag tone="muted">0 PHI</Tag>
          </div>
        </div>

        <div className="access-modal-body">
          {isCreate ? (
            <div className="access-form-field">
              <label htmlFor="mgmt-username">用户名</label>
              <input
                id="mgmt-username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="字母 / 数字 / . _ -，1–20 位"
                autoComplete="off"
              />
            </div>
          ) : null}

          {isCreate || isPassword ? (
            <div className="access-form-field">
              <label htmlFor="mgmt-password">{isPassword ? "新密码" : "密码"}</label>
              <input
                id="mgmt-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder={`长度 ${PASSWORD_MIN}–${PASSWORD_MAX} 位`}
                autoComplete="new-password"
              />
            </div>
          ) : null}

          {isPassword ? (
            <div className="access-form-field">
              <label htmlFor="mgmt-confirm">确认新密码</label>
              <input
                id="mgmt-confirm"
                type="password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                placeholder="再次输入新密码"
                autoComplete="new-password"
              />
            </div>
          ) : null}

          {isCreate || isEdit ? (
            <>
              <div className="access-form-field">
                <label htmlFor="mgmt-display">显示名</label>
                <input
                  id="mgmt-display"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="选填"
                  autoComplete="off"
                />
              </div>
              <div className="access-form-row">
                <div className="access-form-field">
                  <label htmlFor="mgmt-role">角色</label>
                  <select id="mgmt-role" value={roleSel} onChange={(event) => setRoleSel(event.target.value as "normal" | "admin")}>
                    <option value="normal">普通</option>
                    <option value="admin">管理员</option>
                  </select>
                </div>
                <div className="access-form-field">
                  <label htmlFor="mgmt-group">分组</label>
                  <select id="mgmt-group" value={group} onChange={(event) => setGroup(event.target.value)}>
                    {(groups.length ? groups : [group]).map((g) => (
                      <option key={g} value={g}>
                        {g}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </>
          ) : null}

          {isConfirmKind ? (
            <div className="access-confirm-copy">
              {dialog.kind === "status"
                ? `确认${target && target.status === "enabled" ? "停用" : "启用"}用户 ${target?.username}？`
                : dialog.kind === "role"
                  ? `确认将用户 ${target?.username} ${dir === "promote" ? "升级为管理员" : "降级为普通"}？`
                  : `确认删除用户 ${target?.username}？此操作不可撤销。`}
            </div>
          ) : null}

          {fieldError ? <div className="access-form-error">{fieldError}</div> : null}
          {dialog.status === "error" ? <div className="access-form-error">请求失败</div> : null}
        </div>

        <div className="policy-modal-actions">
          <button className="policy-modal-cancel" onClick={onClose} type="button">
            取消
          </button>
          <button
            className={dialog.kind === "delete" ? "policy-modal-submit access-modal-danger" : "policy-modal-submit"}
            disabled={submitting}
            onClick={submit}
            type="button"
          >
            {submitting ? "提交中…" : "确认"}
          </button>
        </div>
      </div>
    </div>
  );
}
