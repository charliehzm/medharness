import { useEffect, useState } from "react";

import Card from "@/components/Card";
import Tag from "@/components/Tag";
import { requestEndpoint } from "@/api/client";
import type { Sanitized, UpstreamsResponse } from "@/api/contract";

import "./System.css";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; data: Sanitized<UpstreamsResponse> }
  | { status: "error" };

export default function System(): JSX.Element {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let alive = true;
    setState({ status: "loading" });

    void requestEndpoint("upstreams")
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
    <div className="system-page">
      <div className="system-head">
        <div>
          <div className="system-kicker">🛠 系统</div>
          <h2>部署健康、备份与升级</h2>
          <div className="system-subtitle">只展示上游健康与聚合统计；备份/升级保留为动作，不编造假指标。</div>
        </div>
        <div className="system-badges">
          <Tag tone="muted">两角色可见</Tag>
          <Tag tone="compliance">全程 0 PHI</Tag>
          <Tag tone="cost">提交审批</Tag>
        </div>
      </div>

      {state.status === "error" ? (
        <div className="system-error">请求失败</div>
      ) : state.status === "loading" ? (
        <div className="system-loading">加载中…</div>
      ) : (
        <div className="system-stack">
          <section className="system-grid">
            <Card title="上游健康">
              <div className="system-list">
                {state.data.upstreams.map((item) => (
                  <div className="system-row" key={item.name}>
                    <div>
                      <div className="system-name">{item.name}</div>
                      <div className="system-meta">
                        {item.ctx} · {item.protocol} · 今日 {item.traffic_today}
                      </div>
                    </div>
                    <div className="system-right">
                      <Tag tone={item.status === "green" ? "ok" : item.status === "yellow" ? "warn" : "bad"}>{item.status === "green" ? "健康" : item.status === "yellow" ? "关注" : "拦截"}</Tag>
                      <span className="system-phi">{item.phi}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            <Card title="备份 / 升级">
              <div className="system-planned">🚧 待接入</div>
              <div className="system-copy">
                备份与升级暂未提供专门契约；保留为动作入口，不展示假数据。
              </div>
              <div className="system-actions">
                <button type="button">一键备份</button>
                <button type="button">检查升级</button>
                <button type="button">提交审批</button>
              </div>
              <div className="system-note">系统屏两角色可见；写口动作统一走审批，不直接生效。</div>
            </Card>
          </section>
        </div>
      )}
    </div>
  );
}
