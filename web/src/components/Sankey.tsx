import "./Sankey.css";

type SankeyMode = "inbound" | "outbound";

type SankeyProps = {
  mode: SankeyMode;
};

const PATHS = {
  inbound: [
    { d: "M160,61 C262.5,61 262.5,170 365,170", color: "var(--teal)", width: 12, flow: 4 },
    { d: "M160,151 C262.5,151 262.5,170 365,170", color: "var(--teal)", width: 7, flow: 3 },
    { d: "M160,241 C262.5,241 262.5,170 365,170", color: "var(--ok)", width: 4, flow: 2 },
    { d: "M535,170 C637.5,170 637.5,81 740,81", color: "var(--violet)", width: 9, flow: 3 },
    { d: "M535,170 C637.5,170 637.5,235 740,235", color: "var(--warn)", width: 5, flow: 2 },
  ],
  outbound: [
    { d: "M160,170 C262.5,170 262.5,170 365,170", color: "var(--violet)", width: 9, flow: 3, blocked: false },
    { d: "M540,170 C642,170 642,111 740,111", color: "var(--ok)", width: 6, flow: 3, blocked: false },
    { d: "M540,170 C642,170 642,251 740,251", color: "var(--bad)", width: 4, flow: 0, blocked: true },
  ],
} as const;

function FlowPath({
  d,
  color,
  width,
  flow,
  blocked,
}: {
  d: string;
  color: string;
  width: number;
  flow: number;
  blocked?: boolean;
}): JSX.Element {
  if (blocked) {
    return <path d={d} stroke={color} strokeDasharray="3 6" strokeWidth={width} fill="none" opacity=".45" />;
  }

  const circles = Array.from({ length: flow }, (_, index) => (
    <circle key={index} r={Math.max(2.2, width / 3)} fill={color}>
      <animateMotion
        begin={`-${((index * 2.6) / flow).toFixed(2)}s`}
        dur="2.6s"
        path={d}
        repeatCount="indefinite"
      />
    </circle>
  ));

  return (
    <>
      <path d={d} stroke={color} strokeWidth={width} fill="none" opacity=".22" />
      {circles}
    </>
  );
}

function SankeyBase({ mode }: SankeyProps): JSX.Element {
  return (
    <div className={`sankey sankey-${mode}`}>
      <svg viewBox="0 0 900 340" preserveAspectRatio="none">
        {PATHS[mode].map((path) => (
          <FlowPath key={path.d} {...path} />
        ))}
      </svg>
      {mode === "inbound" ? (
        <>
          <div className="snode" style={{ left: 10, top: 38 }}>
            <div className="t">Dify RAG</div>
            <div className="s">生产 · 1.2k/h</div>
          </div>
          <div className="snode" style={{ left: 10, top: 128 }}>
            <div className="t">ComfyUI</div>
            <div className="s">生产 · 380/h</div>
          </div>
          <div className="snode" style={{ left: 10, top: 218 }}>
            <div className="t">Codex（开发）</div>
            <div className="s">开发 · 90/h</div>
          </div>
          <div className="snode gate" style={{ left: 365, top: 144, width: 170 }}>
            <div className="t">🛡 安全检查</div>
            <div className="s">隐私扫描 + 脱敏 + 准入</div>
          </div>
          <div className="snode sens" style={{ left: 740, top: 58 }}>
            <div className="t">
              私有模型 <span className="dot d-sec" />
            </div>
            <div className="s">敏感通道 · 脱敏后</div>
          </div>
          <div className="snode bad" style={{ left: 740, top: 212 }}>
            <div className="t">境外模型</div>
            <div className="s">已脱敏 12 · ✗ 阻断 3</div>
          </div>
        </>
      ) : (
        <>
          <div className="snode" style={{ left: 10, top: 146 }}>
            <div className="t">模型响应</div>
            <div className="s">待检查</div>
          </div>
          <div className="snode gate gateout" style={{ left: 365, top: 142, width: 175 }}>
            <div className="t">↩️ 响应安全检查</div>
            <div className="s">🚧 隐私回流 / 有害 / 幻觉</div>
          </div>
          <div className="snode" style={{ left: 740, top: 88 }}>
            <div className="t">返回应用 ✓</div>
            <div className="s">安全响应 · 占位符</div>
          </div>
          <div className="snode bad" style={{ left: 740, top: 228 }}>
            <div className="t">✗ 拦截</div>
            <div className="s">隐私回流 / 有害</div>
          </div>
        </>
      )}
    </div>
  );
}

export default function Sankey({ mode }: SankeyProps): JSX.Element {
  return mode === "outbound" ? (
    <div className="sankey-shell">
      <div className="sankey-wip">🚧 规划</div>
      <SankeyBase mode={mode} />
    </div>
  ) : (
    <SankeyBase mode={mode} />
  );
}
