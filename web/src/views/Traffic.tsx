import { useEffect, useMemo, useState } from "react";

import Card from "@/components/Card";
import EventStream from "@/components/EventStream";
import Sankey from "@/components/Sankey";
import Tag from "@/components/Tag";
import { requestEndpoint } from "@/api/client";
import type { EventsResponse, Sanitized, TrafficEvent, TrafficResponse } from "@/api/contract";

import "./Traffic.css";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; traffic: Sanitized<TrafficResponse>; events: Sanitized<EventsResponse> }
  | { status: "error" };

type FilterId = "all" | "comp" | "sec";

type TrafficEventItem = {
  tone: "compliance" | "security";
  title: string;
  time: string;
  category: string;
  chips: { label: string; tone?: "compliance" | "security" | "cost" | "muted" | "ok" | "warn" | "bad" }[];
};

const FILTERS: { id: FilterId; label: string }[] = [
  { id: "all", label: "全部" },
  { id: "comp", label: "合规(comp)" },
  { id: "sec", label: "安全(sec)" },
];

function mapEvent(event: TrafficEvent): TrafficEventItem {
  if (event.cat === "sec") {
    return {
      tone: "security",
      title: event.action,
      time: event.ts,
      category: event.sec_type,
      chips: [{ label: event.ref, tone: "security" }, { label: event.ctx, tone: "muted" }],
    };
  }

  return {
    tone: "compliance",
    title: event.action,
    time: event.ts,
    category: event.level,
    chips: [{ label: event.ref, tone: "compliance" }, { label: event.ctx, tone: "muted" }],
  };
}

function gateLabel(traffic: TrafficResponse["inbound"]["gate"]): string {
  return `命中 ${traffic.hit} · 阻断 ${traffic.blocked} · 放行 ${traffic.passed}`;
}

export default function Traffic(): JSX.Element {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [filter, setFilter] = useState<FilterId>("all");
  const [mode, setMode] = useState<"inbound" | "outbound">("inbound");

  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });

    void Promise.all([requestEndpoint("traffic"), requestEndpoint("events")])
      .then(([traffic, events]) => {
        if (alive) setState({ status: "ready", traffic, events });
      })
      .catch(() => {
        if (alive) setState({ status: "error" });
      });

    return () => {
      alive = false;
    };
  }, []);

  const visibleEvents = useMemo(() => {
    if (state.status !== "ready") return [];
    const mapped = state.events.events.map(mapEvent);
    if (filter === "comp") return mapped.filter((event) => event.tone === "compliance");
    if (filter === "sec") return mapped.filter((event) => event.tone === "security");
    return mapped;
  }, [filter, state]);

  return (
    <div className="traffic-page">
      <div className="traffic-head">
        <div>
          <div className="traffic-kicker">📊 流量监控</div>
          <h2>调用去向与处置</h2>
          <div className="traffic-subtitle">实时查看大模型调用的去向与处置 · 仅显示脱敏后占位符</div>
        </div>
        <div className="traffic-badges">
          <Tag tone="compliance">合规</Tag>
          <Tag tone="security">安全</Tag>
          <Tag tone="muted">全程 0 PHI</Tag>
        </div>
      </div>

      {state.status === "error" ? (
        <div className="traffic-error">请求失败</div>
      ) : state.status === "loading" ? (
        <div className="traffic-loading">加载中…</div>
      ) : (
        <div className="traffic-stack">
          <section className="traffic-panel">
            <div className="traffic-mode-tabs" role="tablist" aria-label="流向切换">
              <button className={mode === "inbound" ? "on" : ""} onClick={() => setMode("inbound")} type="button">
                调用请求
              </button>
              <button className={mode === "outbound" ? "on" : ""} onClick={() => setMode("outbound")} type="button">
                模型响应 <span className="traffic-wip">🚧</span>
              </button>
            </div>
            <div className="traffic-sankey-wrap">
              <Sankey mode={mode} />
            </div>
            {mode === "outbound" ? <div className="traffic-note">{state.traffic.outbound.note}</div> : null}
          </section>

          <section className="traffic-panel">
            <div className="traffic-row-head">
              <div className="traffic-panel-title">实时事件流 · 双色</div>
              <div className="traffic-legend">
                <span className="traffic-dot comp" /> 合规
                <span className="traffic-dot sec" /> 安全
              </div>
            </div>
            <div className="traffic-filters" role="tablist" aria-label="事件过滤">
              {FILTERS.map((item) => (
                <button
                  key={item.id}
                  className={filter === item.id ? "on" : ""}
                  onClick={() => setFilter(item.id)}
                  type="button"
                >
                  {item.label}
                </button>
              ))}
              <span className="traffic-window">实时 · 最近 1 小时</span>
            </div>
            <EventStream events={visibleEvents} />
            <div className="traffic-note">
              仅显示脱敏后的占位符 <span className="mono">__NAME_a1__</span> 与统计数据，不含原始信息。
            </div>
          </section>

          <section className="traffic-panel traffic-summary">
            <Card title="入站路径摘要">
              <div className="traffic-summary-grid">
                <div>
                  <div className="traffic-summary-label">上游</div>
                  <div className="traffic-summary-value">
                    {state.traffic.inbound.upstreams.map((item) => `${item.name} · ${item.rate}/h`).join(" / ")}
                  </div>
                </div>
                <div>
                  <div className="traffic-summary-label">隐私检查</div>
                  <div className="traffic-summary-value">{gateLabel(state.traffic.inbound.gate)}</div>
                </div>
                <div>
                  <div className="traffic-summary-label">下游</div>
                  <div className="traffic-summary-value">
                    {state.traffic.inbound.downstream.map((item) => `${item.name}${item.note ? ` · ${item.note}` : ""}`).join(" / ")}
                  </div>
                </div>
              </div>
            </Card>
            <Card title="出站能力">
              <div className="traffic-summary-state">🚧 规划</div>
              <div className="traffic-summary-text">
                {state.traffic.outbound.built === false ? state.traffic.outbound.note : "已建"}
              </div>
            </Card>
          </section>
        </div>
      )}
    </div>
  );
}
