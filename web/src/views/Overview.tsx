import { useEffect, useState } from "react";

import Card from "@/components/Card";
import Ring from "@/components/Ring";
import Tag from "@/components/Tag";
import { requestEndpoint } from "@/api/client";
import type { PostureGoal, PostureResponse, Sanitized } from "@/api/contract";

import "./Overview.css";

const GOAL_ACCENT: Record<PostureGoal["key"], "var(--teal)" | "var(--violet)" | "var(--navy)" | "var(--cost)"> = {
  security: "var(--teal)",
  cost: "var(--cost)",
  compliance: "var(--violet)",
  stability: "var(--navy)",
};

type LoadState =
  | { status: "loading" }
  | { status: "ready"; data: Sanitized<PostureResponse> }
  | { status: "error" };

const GATE_META: Record<string, { icon: string; label: string }> = {
  "phi-inbound": { icon: "🔎", label: "患者隐私(PHI)扫描" },
  desensitize: { icon: "🔐", label: "脱敏加密" },
  "model-router": { icon: "🧭", label: "模型准入" },
  injection: { icon: "🛡", label: "注入攻击防御" },
  "outbound-safety": { icon: "↩️", label: "响应安全检查" },
  "rate-limit": { icon: "⏱", label: "用量与成本护栏" },
};

function GateState({ built }: { built?: boolean }): JSX.Element {
  return built === false ? <span className="overview-wip">即将推出</span> : <Tag tone="ok">已上线</Tag>;
}

function GateCard({
  gate,
}: {
  gate: PostureResponse["gates"][number];
}): JSX.Element {
  const meta = GATE_META[gate.id] ?? { icon: "•", label: gate.id };
  const tone = gate.group === "compliance" ? "compliance" : "security";
  return (
    <article className={`overview-gate overview-gate-${gate.group}`}>
      <div className="overview-gate-head">
        <span className="overview-gate-icon" aria-hidden="true">
          {meta.icon}
        </span>
        <GateState built={gate.built} />
      </div>
      <div className="overview-gate-title">{meta.label}</div>
      <div className="overview-gate-metric">{gate.metric}</div>
      {gate.desc ? <div className="overview-gate-desc">{gate.desc}</div> : null}
      <div className="overview-gate-chiprow">
        <Tag tone={tone}>{gate.group === "compliance" ? "合规" : "安全"}</Tag>
        <Tag tone="muted">{gate.status === "planned" ? "即将推出" : gate.status}</Tag>
      </div>
    </article>
  );
}

function TargetCard({
  title,
  ring,
  metric,
  submetric,
  accent,
  summary,
  foot,
}: {
  title: string;
  ring: number;
  metric: string;
  submetric: string;
  accent: "var(--teal)" | "var(--violet)" | "var(--navy)" | "var(--cost)";
  summary: string;
  foot: string;
}): JSX.Element {
  return (
    <Card>
      <div className="overview-target">
        <div className="overview-target-head">
          <span className="overview-goal-pill">{title}</span>
          <div className="overview-target-summary">{summary}</div>
        </div>
        <div className="overview-target-body">
          <Ring value={ring} color={accent} label="综合" denominator="/100" />
          <div className="overview-target-copy">
            <div className="overview-target-metric">{metric}</div>
            <div className="overview-target-submetric">{submetric}</div>
            <div className="overview-target-foot">{foot}</div>
          </div>
        </div>
      </div>
    </Card>
  );
}

export default function Overview(): JSX.Element {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });

    void requestEndpoint("posture")
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

  return (
    <div className="overview-page">
      {state.status === "error" ? (
        <div className="overview-error">请求失败</div>
      ) : state.status === "loading" ? (
        <div className="overview-loading">加载中…</div>
      ) : (
        <div className="overview-stack">
          <div className="overview-page-head">
            <div className="overview-kicker">🏠 总览</div>
            <h2>四目标一屏看懂</h2>
            <div className="overview-subtitle">四目标一屏看懂 · 全程 0 PHI</div>
          </div>

          <section className="overview-attention">
            <div className="overview-section-title">需要注意（{state.data.alerts.length}）</div>
            {state.data.alerts.map((alert, index) => (
              <div className="overview-alert-row" key={`${alert.type}-${index}`}>
                <div>
                  <div className="overview-alert-title">
                    {alert.level === "warn" ? "🟡" : "🔴"} {alert.summary}
                  </div>
                  <div className="overview-alert-meta">
                    {alert.cat === "security" ? "安全" : "合规"} · {alert.type}
                  </div>
                </div>
                <div className="overview-alert-ref">查看怎么修 →</div>
              </div>
            ))}
          </section>

          <section className="overview-grid overview-grid-4">
            {state.data.goals.map((goal) => (
              <TargetCard
                key={goal.key}
                accent={GOAL_ACCENT[goal.key]}
                foot="网关实时聚合"
                metric={goal.metric}
                ring={goal.score}
                submetric={goal.submetric}
                summary={goal.summary}
                title={goal.summary}
              />
            ))}
          </section>

          <section>
            <div className="overview-section-title">安全检查能力</div>
            <div className="overview-gate-grid">
              {state.data.gates.map((gate) => (
                <GateCard gate={gate} key={gate.id} />
              ))}
            </div>
          </section>

          <section className="overview-grid overview-grid-2">
            <section className="overview-summary-card">
              <div className="overview-summary-title">本月安全小结</div>
              <div className="overview-summary-text">{state.data.summaries.security}</div>
              <div className="overview-summary-tags">
                <Tag tone="ok">实时聚合</Tag>
              </div>
            </section>
            <section className="overview-summary-card">
              <div className="overview-summary-title">本月成本小结</div>
              <div className="overview-summary-text">{state.data.summaries.cost}</div>
              <div className="overview-summary-tags">
                <Tag tone="cost">实时聚合</Tag>
              </div>
            </section>
          </section>
        </div>
      )}
    </div>
  );
}
