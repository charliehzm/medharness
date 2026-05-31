import { useEffect, useMemo, useState } from "react";

import Table, { type TableColumn } from "@/components/Table";
import Tag from "@/components/Tag";
import { requestEndpoint } from "@/api/client";
import type {
  AuditExportResponse,
  AuditLineageResponse,
  EventsResponse,
  Sanitized,
  TrafficEvent,
} from "@/api/contract";

import "./Audit.css";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; data: Sanitized<EventsResponse> }
  | { status: "error" };

type AuditRow = Record<string, unknown> & {
  ts: string;
  cat: "comp" | "sec";
  status: "green" | "yellow" | "red";
  upstream: string;
  ctx: "dev" | "prod";
  action: string;
  ref: string;
  eventType: string;
};

type LineageState =
  | { status: "idle" }
  | { status: "loading"; ref: string }
  | { status: "ready"; data: Sanitized<AuditLineageResponse> }
  | { status: "error"; ref: string };

type ExportState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: Sanitized<AuditExportResponse> }
  | { status: "error" };

const STATUS_TONE: Record<AuditRow["status"], "ok" | "warn" | "bad"> = {
  green: "ok",
  yellow: "warn",
  red: "bad",
};

const STATUS_LABEL: Record<AuditRow["status"], string> = {
  green: "通过",
  yellow: "关注",
  red: "拦截",
};

const CAT_LABEL: Record<AuditRow["cat"], string> = {
  comp: "合规",
  sec: "安全",
};

const EXPORT_STATUS_LABEL: Record<AuditExportResponse["status"], string> = {
  packing: "打包中",
  ready: "已生成",
};

const columns: TableColumn<AuditRow>[] = [
  {
    key: "ts",
    header: "时间",
    mono: true,
    render: (row) => <span className="audit-time">{formatTime(row.ts)}</span>,
  },
  {
    key: "cat",
    header: "类别",
    render: (row) => (
      <Tag tone={row.cat === "sec" ? "security" : "compliance"}>{CAT_LABEL[row.cat]}</Tag>
    ),
  },
  {
    key: "eventType",
    header: "分类",
    render: (row) => (
      <Tag tone={row.cat === "sec" ? "security" : "compliance"}>{row.eventType}</Tag>
    ),
  },
  {
    key: "upstream",
    header: "上游",
    render: (row) => (
      <span>
        {row.upstream} <span className="audit-muted">· {row.ctx}</span>
      </span>
    ),
  },
  {
    key: "status",
    header: "处置",
    render: (row) => <Tag tone={STATUS_TONE[row.status]}>{STATUS_LABEL[row.status]}</Tag>,
  },
  {
    key: "action",
    header: "动作",
  },
  {
    key: "ref",
    header: "事件编号",
    mono: true,
    render: (row) => <span className="audit-code">{row.ref}</span>,
  },
];

function toAuditRow(event: TrafficEvent): AuditRow {
  return {
    ts: event.ts,
    cat: event.cat,
    status: event.status,
    upstream: event.upstream,
    ctx: event.ctx,
    action: event.action,
    ref: event.ref,
    eventType: event.cat === "sec" ? event.sec_type : event.level,
  };
}

function formatTime(value: string): string {
  return value.replace("T", " ").replace("Z", " UTC");
}

function matchesSearch(row: AuditRow, query: string): boolean {
  if (!query) return true;
  const haystack = [
    row.ts,
    row.cat,
    CAT_LABEL[row.cat],
    row.status,
    STATUS_LABEL[row.status],
    row.upstream,
    row.ctx,
    row.action,
    row.ref,
    row.eventType,
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function displayDetailKey(key: string, value: string): string {
  return value === "（不留存）" ? "原文内容" : key;
}

function displayDetailValue(value: string): string {
  return value === "（不留存）" ? "不留存" : value;
}

export default function Audit(): JSX.Element {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [query, setQuery] = useState("");
  const [lineage, setLineage] = useState<LineageState>({ status: "idle" });
  const [exportState, setExportState] = useState<ExportState>({ status: "idle" });

  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });

    void requestEndpoint("events")
      .then((data) => {
        if (alive) setState({ status: "ready", data });
      })
      .catch(() => {
        if (alive) setState({ status: "error" });
      });

    return () => {
      alive = false;
    };
  }, []);

  const rows = useMemo(() => {
    if (state.status !== "ready") return [];
    return state.data.events.map(toAuditRow).filter((row) => matchesSearch(row, query.trim()));
  }, [query, state]);

  const handleRowClick = (row: AuditRow) => {
    setLineage({ status: "loading", ref: row.ref });
    void requestEndpoint("audit", { path: { ref: row.ref } })
      .then((data) => setLineage({ status: "ready", data }))
      .catch(() => setLineage({ status: "error", ref: row.ref }));
  };

  const handleExport = () => {
    setExportState({ status: "loading" });
    void requestEndpoint("auditExport", { body: { scope: "all" } })
      .then((data) => setExportState({ status: "ready", data }))
      .catch(() => setExportState({ status: "error" }));
  };

  return (
    <div className="audit-page">
      <div className="audit-head">
        <div>
          <div className="audit-kicker">🔍 审计与报表</div>
          <h2>查得清 · 改不了 · 交得出</h2>
          <div className="audit-subtitle">仅展示脱敏占位符、哈希引用与聚合处置结果。</div>
        </div>
        <div className="audit-badges" aria-label="审计状态">
          <Tag tone="ok">防篡改链</Tag>
          <Tag tone="muted">每日校验</Tag>
          <Tag tone="compliance">全程 0 PHI</Tag>
          <button
            className="audit-export-button"
            disabled={exportState.status === "loading"}
            onClick={handleExport}
            type="button"
          >
            {exportState.status === "loading" ? "打包中…" : "导出监管应对包"}
          </button>
        </div>
      </div>

      {state.status === "error" ? (
        <div className="audit-error">请求失败</div>
      ) : state.status === "loading" ? (
        <div className="audit-loading">加载中…</div>
      ) : (
        <div className="audit-stack">
          <section className="audit-panel">
            <div className="audit-toolbar">
              <div>
                <div className="audit-panel-title">可检索审计列表</div>
                <div className="audit-panel-subtitle">
                  仅列出事件时间、类别、上游、处置与编号；安全事件只显示分类与处置。
                </div>
              </div>
              <label className="audit-search">
                <span>检索</span>
                <input
                  aria-label="检索审计事件"
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="事件编号、上游、处置、分类"
                  type="search"
                  value={query}
                />
              </label>
            </div>

            <Table
              columns={columns}
              emptyLabel="暂无匹配事件"
              getRowKey={(row) => row.ref}
              onRowClick={handleRowClick}
              rows={rows}
            />

            <div className="audit-footnote">
              明细仅显示脱敏后的占位符与哈希引用；原始信息不在 Console 内反查。
            </div>

            {exportState.status === "ready" ? (
              <section className="audit-export-result" aria-label="监管应对包导出结果">
                <div>
                  <div className="audit-panel-title">监管应对包</div>
                  <div className="audit-panel-subtitle">仅生成包引用与校验哈希，不导出原始数据。</div>
                </div>
                <div className="audit-export-grid">
                  <div>
                    <span>包编号</span>
                    <b>{exportState.data.bundle_id}</b>
                  </div>
                  <div>
                    <span>状态</span>
                    <b>{EXPORT_STATUS_LABEL[exportState.data.status]}</b>
                  </div>
                  <div>
                    <span>校验哈希</span>
                    <b>{exportState.data.sha256}</b>
                  </div>
                </div>
              </section>
            ) : exportState.status === "error" ? (
              <div className="audit-inline-error">请求失败</div>
            ) : null}
          </section>

          <aside className="audit-drawer" aria-live="polite">
            <div className="audit-panel-title">血缘与哈希链</div>
            {lineage.status === "idle" ? (
              <div className="audit-drawer-copy">选择一条审计事件后查看血缘与哈希链。</div>
            ) : lineage.status === "loading" ? (
              <>
                <div className="audit-selected-ref">{lineage.ref}</div>
                <div className="audit-drawer-copy">加载中…</div>
              </>
            ) : lineage.status === "error" ? (
              <>
                <div className="audit-selected-ref">{lineage.ref}</div>
                <div className="audit-inline-error">请求失败</div>
              </>
            ) : (
              <>
                <div>
                  <div className="audit-lineage-title">{lineage.data.title}</div>
                  <div className="audit-selected-ref">{lineage.data.ref}</div>
                </div>
                <div className="audit-lineage" aria-label="审计血缘">
                  {lineage.data.nodes.map((node, index) => (
                    <div className="audit-lineage-node" key={`${node.t}-${index}`}>
                      <div className="audit-lineage-icon" aria-hidden="true">
                        {node.ico}
                      </div>
                      <div>
                        <b>{node.t}</b>
                        <span>{node.s}</span>
                      </div>
                    </div>
                  ))}
                </div>
                <section className="audit-hash-block" aria-label="哈希链">
                  <div className="audit-hash-label">当前哈希</div>
                  <div className="audit-hash-value">{lineage.data.hash}</div>
                  <div className="audit-hash-tags">
                    <Tag tone="ok">链完整</Tag>
                    <Tag tone="muted">每日校验</Tag>
                    <Tag tone="security">🔒 不可删改</Tag>
                  </div>
                </section>
                <dl className="audit-detail-list">
                  {lineage.data.details.map((item) => (
                    <div key={item.k}>
                      <dt>{displayDetailKey(item.k, item.v)}</dt>
                      <dd>{displayDetailValue(item.v)}</dd>
                    </div>
                  ))}
                </dl>
              </>
            )}
          </aside>
        </div>
      )}
    </div>
  );
}
