import { type FormEvent, type JSX, useState } from "react";

import Tag from "@/components/Tag";
import { login, type ConsoleRole } from "@/api/client";

import "./Login.css";

type LoginProps = {
  onLogin: (role: ConsoleRole) => void;
};

const GOALS = ["安全", "省钱", "合规", "稳定"] as const;

export default function Login({ onLogin }: LoginProps): JSX.Element {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (submitting) return;
    setError("");
    setSubmitting(true);
    try {
      const result = await login(username, password);
      onLogin(result.role);
    } catch {
      setError("登录失败：用户名或密码错误，或登录服务暂不可用");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login">
      <div className="login-bg" aria-hidden="true">
        <div className="login-grid" />
        <div className="login-orb login-orb-teal" />
        <div className="login-orb login-orb-violet" />
        {Array.from({ length: 6 }).map((_, index) => (
          <span className={`login-pt login-pt-${index + 1}`} key={index} />
        ))}
      </div>

      <section className="login-hero">
        <div className="login-brand">
          <div className="login-logo">⊕</div>
          <div>
            <div className="login-brand-name">MedHarness</div>
            <div className="login-brand-sub">医疗大模型流量网关</div>
          </div>
        </div>
        <h1>
          让每一次大模型调用
          <br />
          都<span>安全 · 省钱 · 合规 · 稳定</span>
        </h1>
        <p>把开发态与生产态的大模型流量收口为单一受控入口。脱敏、分级路由、防篡改审计，一套网关，四个目标。</p>
        <div className="login-goals">
          {GOALS.map((goal) => (
            <Tag key={goal} tone={goal === "安全" ? "security" : goal === "省钱" ? "cost" : goal === "合规" ? "compliance" : "muted"}>
              {goal}
            </Tag>
          ))}
        </div>
        <div className="login-badges">
          <span>✓ 全程 0 PHI</span>
          <span>✓ HIPAA · PIPL · 数据安全法</span>
          <span>✓ 单主机部署</span>
        </div>
      </section>

      <section className="login-panel">
        <form className="login-panel-card" onSubmit={handleSubmit}>
          <div className="login-panel-kicker">登录控制台</div>
          <h2>企业统一身份 · 全程留痕</h2>

          <label className="login-field">
            <span className="login-label">用户名</span>
            <input
              autoComplete="username"
              className="login-input"
              disabled={submitting}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="请输入用户名"
              required
              type="text"
              value={username}
            />
          </label>

          <label className="login-field">
            <span className="login-label">密码</span>
            <input
              autoComplete="current-password"
              className="login-input"
              disabled={submitting}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              required
              type="password"
              value={password}
            />
          </label>

          {error ? (
            <div className="login-error" role="alert">
              {error}
            </div>
          ) : null}

          <button className="login-btn primary" disabled={submitting} type="submit">
            {submitting ? "登录中…" : "登录"}
          </button>

          <div className="login-sec">账号由管理员开通 · 操作全程留痕可审计</div>
        </form>
      </section>

      <div className="login-env">
        环境 <b>生产</b> · medharness.local
      </div>
    </div>
  );
}
