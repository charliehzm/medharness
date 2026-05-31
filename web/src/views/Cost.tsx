import { useEffect, useMemo, useState } from "react";
import { VChart, type IBarChartSpec, type ILineChartSpec } from "@visactor/react-vchart";

import Card from "@/components/Card";
import Ring from "@/components/Ring";
import Table, { type TableColumn } from "@/components/Table";
import Tag from "@/components/Tag";
import { requestEndpoint } from "@/api/client";
import type { ChannelsResponse, CostResponse, Sanitized } from "@/api/contract";

import "./Cost.css";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; cost: Sanitized<CostResponse>; channels: Sanitized<ChannelsResponse> }
  | { status: "error" };

type CostDim = CostResponse["by_lane"][number];

type ChannelRow = {
  [key: string]: unknown;
  name: string;
  model: string;
  weight: number;
  unit_price: string;
  p95_ms: number;
  region: string;
  picked: boolean;
  status: ChannelsResponse["channels"][number]["status"];
  weightLabel: string;
  p95Label: string;
};

type ThemeColors = {
  cost: string;
  costBorder: string;
  teal: string;
  navy: string;
  ok: string;
  laneNormal: string;
  laneSensitive: string;
  line: string;
  muted: string;
};

const CHANNEL_COLUMNS: TableColumn<ChannelRow>[] = [
  { key: "name", header: "渠道" },
  { key: "model", header: "模型", mono: true },
  { key: "weightLabel", header: "权重", align: "center" },
  { key: "unit_price", header: "单价", mono: true },
  { key: "p95Label", header: "延迟", mono: true },
  {
    key: "region",
    header: "区域",
    render: (row) => <Tag tone={toneForRegion(row.region)}>{row.region}</Tag>,
  },
  {
    key: "status",
    header: "状态",
    render: (row) => (
      <Tag tone={row.status === "green" ? "ok" : row.status === "yellow" ? "warn" : "bad"}>
        {row.picked ? "最优" : "健康"}
      </Tag>
    ),
  },
];

function toneForRegion(region: string): "compliance" | "security" | "cost" | "muted" | "ok" | "warn" | "bad" {
  return region.includes("境外") ? "warn" : "compliance";
}

function readToken(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function useThemeColors(): ThemeColors {
  return useMemo(
    () => ({
      cost: readToken("--cost", "var(--cost)"),
      costBorder: readToken("--cost-border", "var(--cost-border)"),
      teal: readToken("--teal", "var(--teal)"),
      navy: readToken("--navy", "var(--navy)"),
      ok: readToken("--ok", "var(--ok)"),
      laneNormal: readToken("--lane-normal", "var(--lane-normal)"),
      laneSensitive: readToken("--lane-sensitive", "var(--lane-sensitive)"),
      line: readToken("--line", "var(--line)"),
      muted: readToken("--muted", "var(--muted)"),
    }),
    [],
  );
}

function colorFromToken(token: string, colors: ThemeColors): string {
  const map: Record<string, string> = {
    "lane-normal": colors.laneNormal,
    "lane-sensitive": colors.laneSensitive,
    compliance: colors.teal,
    primary: colors.navy,
    ok: colors.ok,
    cost: colors.cost,
  };
  return map[token] ?? colors.cost;
}

function buildBarSpec(title: string, items: CostDim[], colors: ThemeColors): IBarChartSpec {
  return {
    type: "bar",
    direction: "horizontal",
    data: [
      {
        id: title,
        values: items.map((item) => ({
          name: item.name,
          pct: item.pct,
          amount: item.amount,
          color: colorFromToken(item.color_token, colors),
        })),
      },
    ],
    xField: "pct",
    yField: "name",
    color: items.map((item) => colorFromToken(item.color_token, colors)),
    axes: [
      { orient: "bottom", visible: false },
      { orient: "left", label: { style: { fill: colors.muted, fontSize: 11 } } },
    ],
    label: {
      visible: true,
      position: "right",
      formatter: "{pct}%",
      style: { fill: colors.muted, fontSize: 11 },
    },
    tooltip: { visible: false },
    padding: { top: 8, right: 34, bottom: 6, left: 0 },
  } as unknown as IBarChartSpec;
}

function buildTrendSpec(values: number[], colors: ThemeColors): ILineChartSpec {
  return {
    type: "line",
    data: [
      {
        id: "cost-trend",
        values: values.map((value, index) => ({
          day: `D-${values.length - index - 1}`,
          value,
        })),
      },
    ],
    xField: "day",
    yField: "value",
    point: { visible: true, style: { fill: colors.cost, stroke: colors.costBorder, lineWidth: 2 } },
    line: { style: { stroke: colors.cost, lineWidth: 3 } },
    axes: [
      { orient: "bottom", label: { style: { fill: colors.muted, fontSize: 11 } }, domainLine: { visible: false }, tick: { visible: false } },
      { orient: "left", visible: false, grid: { visible: true, style: { stroke: colors.line, lineDash: [4, 4] } } },
    ],
    tooltip: { visible: false },
    padding: { top: 8, right: 10, bottom: 24, left: 8 },
  } as unknown as ILineChartSpec;
}

function ChartPanel({
  title,
  items,
  colors,
}: {
  title: string;
  items: CostDim[];
  colors: ThemeColors;
}): JSX.Element {
  return (
    <Card title={title}>
      <div className="cost-chart" aria-label={title}>
        <VChart spec={buildBarSpec(title, items, colors)} />
      </div>
      <div className="cost-bar-legend">
        {items.map((item) => (
          <div className="cost-bar-legend-row" key={item.name}>
            <span className="cost-legend-dot" style={{ background: colorFromToken(item.color_token, colors) }} />
            <span>{item.name}</span>
            <b>{item.amount}</b>
          </div>
        ))}
      </div>
    </Card>
  );
}

export default function Cost(): JSX.Element {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const colors = useThemeColors();

  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });

    void Promise.all([requestEndpoint("cost"), requestEndpoint("channels")])
      .then(([cost, channels]) => {
        if (alive) setState({ status: "ready", cost, channels });
      })
      .catch(() => {
        if (alive) setState({ status: "error" });
      });

    return () => {
      alive = false;
    };
  }, []);

  const kpiCards = useMemo(() => {
    if (state.status !== "ready") return [];
    return [
      {
        title: "本月成本",
        value: state.cost.kpi.month_cost,
        foot: `较直连省 ${state.cost.kpi.saved_vs_direct} · ${state.cost.kpi.saved_ratio}`,
      },
      {
        title: "缓存省",
        value: state.cost.kpi.cache_saved,
        foot: `缓存命中 ${state.cost.kpi.cache_hit_ratio}`,
      },
      {
        title: "常规通道",
        value: state.cost.kpi.normal_lane_ratio,
        foot: "常规通道承载更多低成本流量",
      },
      {
        title: "节省比",
        value: state.cost.kpi.saved_ratio,
        foot: `按聚合口径估算节省 ${state.cost.kpi.saved_vs_direct}`,
      },
    ];
  }, [state]);

  const channelRows = useMemo<ChannelRow[]>(() => {
    if (state.status !== "ready") return [];
    return state.channels.channels.map((channel) => ({
      ...channel,
      weightLabel: `${channel.weight}%`,
      p95Label: `${channel.p95_ms} ms`,
    }));
  }, [state]);

  return (
    <div className="cost-page">
      <div className="cost-head">
        <div>
          <div className="cost-kicker">💰 用量与成本</div>
          <h2>用量、开销、降本一目了然</h2>
          <div className="cost-subtitle">全程聚合视图 · 只显示成本、节省、护栏与比价。</div>
        </div>
        <div className="cost-badges">
          <Tag tone="cost">省钱建议</Tag>
          <Tag tone="compliance">常规通道</Tag>
          <Tag tone="muted">全程 0 PHI</Tag>
        </div>
      </div>

      {state.status === "error" ? (
        <div className="cost-error">请求失败</div>
      ) : state.status === "loading" ? (
        <div className="cost-loading">加载中…</div>
      ) : (
        <div className="cost-stack">
          <section className="cost-grid cost-grid-kpi">
            {kpiCards.map((card) => (
              <Card key={card.title}>
                <div className="cost-kpi-card">
                  <div className="cost-kpi-title">{card.title}</div>
                  <div className="cost-kpi-value">{card.value}</div>
                  <div className="cost-kpi-foot">{card.foot}</div>
                </div>
              </Card>
            ))}
          </section>

          <section className="cost-grid cost-grid-guard">
            <Card title="成本护栏">
              <div className="cost-guard">
                <Ring value={Number.parseInt(state.cost.kpi.cap_left_ratio, 10)} color="var(--cost)" label="余量" denominator="% left" />
                <div className="cost-guard-copy">
                  <div className="cost-guard-line">
                    <span>日上限</span>
                    <b>{state.cost.kpi.cap_day}</b>
                  </div>
                  <div className="cost-guard-line">
                    <span>今日已用</span>
                    <b>{state.cost.kpi.cap_used}</b>
                  </div>
                  <div className="cost-guard-line">
                    <span>剩余比例</span>
                    <b>{state.cost.kpi.cap_left_ratio}</b>
                  </div>
                </div>
              </div>
            </Card>

            <Card title="趋势">
              <div className="cost-chart cost-trend-chart" aria-label="近 7 日趋势">
                <VChart spec={buildTrendSpec(state.cost.trend, colors)} />
              </div>
              <div className="cost-trend-foot">近 7 日聚合趋势</div>
            </Card>
          </section>

          <section className="cost-grid cost-grid-bars">
            <ChartPanel colors={colors} items={state.cost.by_lane} title="成本构成 · 按通道" />
            <ChartPanel colors={colors} items={state.cost.by_model} title="成本构成 · 按模型" />
          </section>

          <section className="cost-grid cost-grid-table">
            <Card title="智能选路比价">
              <div className="cost-table-head">
                <div className="cost-panel-title">渠道择优</div>
                <div className="cost-panel-subtitle">同模型多渠道自动选更省的，仍限准入名单内。</div>
              </div>
              <Table<ChannelRow>
                columns={CHANNEL_COLUMNS}
                emptyLabel="暂无渠道"
                getRowKey={(row) => `${row.name}-${row.model}`}
                rows={channelRows}
              />
            </Card>
            <Card title="省钱建议">
              <div className="cost-tips">
                {state.cost.tips.map((tip) => (
                  <div className="cost-tip" key={tip.tip}>
                    <div className="cost-tip-text">{tip.tip}</div>
                    <Tag tone="cost">{tip.saving}</Tag>
                  </div>
                ))}
              </div>
            </Card>
          </section>
        </div>
      )}
    </div>
  );
}
