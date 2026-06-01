import { useEffect, useMemo, useState } from "react";

import Card from "@/components/Card";
import Table, { type TableColumn } from "@/components/Table";
import Tag from "@/components/Tag";
import { requestEndpoint } from "@/api/client";
import type {
  AdminChannel,
  AdminChannelsResponse,
  AdminToken,
  AdminTokensResponse,
  AdminUser,
  AdminUsersResponse,
  Sanitized,
  UpstreamsResponse,
} from "@/api/contract";

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

export default function Access(): JSX.Element {
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
              >
                {item.label}
              </button>
            ))}
          </section>

          <section className="access-banner">
            <div>
              <div className="access-banner-title">{activeTab.label}</div>
              <div className="access-banner-text">{activeTab.note}</div>
            </div>
            <div className="access-banner-actions">
              <button type="button">{APPROVAL_ACTION[tab]}</button>
            </div>
          </section>

          {tab === "apps" ? (
            <div className="access-grid access-grid-apps">
              <Card title="接入应用">
                <div className="access-planned">🚧 规划</div>
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
