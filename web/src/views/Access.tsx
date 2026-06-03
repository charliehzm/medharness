import { useCallback, useEffect, useMemo, useState } from "react";

import Card from "@/components/Card";
import Table, { type TableColumn } from "@/components/Table";
import Tag from "@/components/Tag";
import {
  createUser,
  deleteUser,
  fetchGroups,
  fetchMgmtUsers,
  requestEndpoint,
  setUserPassword,
  setUserRole,
  setUserStatus,
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
  MgmtRole,
  MgmtUser,
  Sanitized,
  UpstreamsResponse,
} from "@/api/contract";
import type { RoleId } from "@/app/nav";

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

type AccessTab = "apps" | "channels" | "tokens" | "users";

type UserRow = Record<string, unknown> & AdminUser & {
  quotaLabel: string;
  usedLabel: string;
};

type TokenRow = Record<string, unknown> & AdminToken & {
  remainLabel: string;
  usedLabel: string;
  dataLabel: string;
};

type ChannelRow = Record<string, unknown> & AdminChannel & {
  modelList: string;
  weightLabel: string;
};

const TAB_ITEMS: { id: AccessTab; label: string; note: string }[] = [
  { id: "apps", label: "接入应用", note: "base_url 零改造接入 · 写口仍走提交审批" },
  { id: "channels", label: "模型与渠道", note: "多路权重 · 单价 · 区域 · Lane" },
  { id: "tokens", label: "令牌与配额", note: "配额 + 数据等级 · 无明文 key" },
  { id: "users", label: "用户与分组", note: "OIDC / passkey · 仅脱敏 id_hash" },
];

const APPROVAL_ACTION: Record<AccessTab, string> = {
  apps: "提交审批 · 接入应用",
  channels: "提交审批 · 调整渠道",
  tokens: "提交审批 · 新增令牌",
  users: "提交审批 · 新增用户",
};

const USER_COLUMNS: TableColumn<UserRow>[] = [
  { key: "id_hash", header: "用户", mono: true },
  { key: "role", header: "角色" },
  { key: "console_role", header: "Console 角色", render: (row) => <Tag tone={row.console_role ? "ok" : "muted"}>{row.console_role ?? "—（仅令牌）"}</Tag> },
  { key: "group", header: "分组" },
  { key: "quotaLabel", header: "配额", mono: true },
  { key: "usedLabel", header: "已用", mono: true },
  { key: "status", header: "状态", render: (row) => <Tag tone={row.status === "enabled" ? "ok" : "warn"}>{row.status === "enabled" ? "启用" : "停用"}</Tag> },
];

const TOKEN_COLUMNS: TableColumn<TokenRow>[] = [
  { key: "id_hash", header: "令牌", mono: true },
  { key: "name", header: "标签" },
  { key: "remainLabel", header: "剩余配额", mono: true },
  { key: "usedLabel", header: "已用", mono: true },
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
];

const CHANNEL_COLUMNS: TableColumn<ChannelRow>[] = [
  { key: "id_hash", header: "渠道", mono: true },
  { key: "name", header: "名称" },
  { key: "type", header: "类型" },
  { key: "weightLabel", header: "权重", align: "center" },
  { key: "region", header: "区域", render: (row) => <Tag tone={row.region.includes("境外") ? "warn" : "compliance"}>{row.region}</Tag> },
  {
    key: "lane",
    header: "Lane",
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
      quotaLabel: user.quota,
      usedLabel: user.used_quota,
    }));
  }, [state]);

  const tokenRows = useMemo(() => {
    if (state.status !== "ready") return [];
    return state.tokens.tokens.map((token) => ({
      ...token,
      remainLabel: token.remain_quota,
      usedLabel: token.used_quota,
      dataLabel: formatList(token.allowed_data_levels),
    }));
  }, [state]);

  const channelRows = useMemo(() => {
    if (state.status !== "ready") return [];
    return state.channels.channels.map((channel) => ({
      ...channel,
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
          <h2>用户、令牌、渠道与零改造接入</h2>
          <div className="access-subtitle">读路径走 A0 admin 代理，只显示脱敏 id_hash、配额、数据等级与区域。</div>
        </div>
        <div className="access-badges">
          <Tag tone="muted">仅管理面</Tag>
          <Tag tone="compliance">全程 0 PHI</Tag>
          <Tag tone="cost">提交审批</Tag>
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

          {!(tab === "users" && isManagement) ? (
            <section className="access-banner">
              <div>
                <div className="access-banner-title">{activeTab.label}</div>
                <div className="access-banner-text">{activeTab.note}</div>
              </div>
              <div className="access-banner-actions">
                <button type="button">{APPROVAL_ACTION[tab]}</button>
              </div>
            </section>
          ) : null}

          {tab === "apps" ? (
            <div className="access-grid access-grid-apps">
              <Card title="接入应用">
                <div className="access-planned">即将推出</div>
                <div className="access-copy">
                  当前契约未提供 apps 端点；先保留为占位，不编造应用列表。
                </div>
              </Card>
              <Card title="零改造接入">
              <div className="access-copy">
                <p>把 base_url 指向网关即可；写口改动走提交审批，不直接生效。</p>
                <div className="access-note-list">
                  <div>工程师 / 服务：只用令牌，不进 Console。</div>
                  <div>自助注册 / 社交登录：已关闭。</div>
                  <div>读路径：仅 A0 admin 代理。</div>
                </div>
              </div>
            </Card>
            </div>
          ) : tab === "channels" ? (
            <Card title="模型与渠道">
              <Table<ChannelRow>
                columns={CHANNEL_COLUMNS}
                emptyLabel="暂无渠道"
                getRowKey={(row) => row.id_hash}
                rows={channelRows}
              />
              <div className="access-footnote">渠道仅显示 id_hash、名称、类型、权重、区域、Lane、模型与状态。</div>
            </Card>
          ) : tab === "tokens" ? (
            <Card title="令牌与配额">
              <Table<TokenRow>
                columns={TOKEN_COLUMNS}
                emptyLabel="暂无令牌"
                getRowKey={(row) => row.id_hash}
                rows={tokenRows}
              />
              <div className="access-footnote">令牌只显示脱敏标签、配额和允许数据等级；无明文 key。</div>
            </Card>
          ) : isManagement ? (
            <UserManagement />
          ) : (
            <Card title="用户与分组">
              <Table<UserRow>
                columns={USER_COLUMNS}
                emptyLabel="暂无用户"
                getRowKey={(row) => row.id_hash}
                rows={userRows}
              />
              <div className="access-footnote">用户仅显示 id_hash、角色、分组、配额与 Console 角色；无 email / phone / display_name。</div>
            </Card>
          )}

          <section className="access-summary-grid">
            <Card title="管理面约束">
              <div className="access-summary-list">
                <div><b>读路径</b><span>A0 admin 代理</span></div>
                <div><b>写操作</b><span>提交审批</span></div>
                <div><b>认证</b><span>OIDC / passkey</span></div>
                <div><b>禁用入口</b><span>注册 / 支付 / 订阅 / 兑换 / 充值 / 钱包 / 社交登录</span></div>
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
          <div className="access-banner-text">系统管理员管理内部运营人员（operators）的账号 · 患者 PHI 恒为 0</div>
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
              本视图展示的是内部运营人员（operators）身份，**非患者**——故合法携带 STAFF 邮箱 / 显示名；
              患者 PHI 全程为 0（密码线下交付，不发邮件）。升级 / 降级 / 删除仅对低于自身角色的目标可用。
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
              {target ? `${target.username} · ${ROLE_LABEL[target.role]}` : "内部运营人员（非患者）· 患者 PHI 恒为 0"}
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
