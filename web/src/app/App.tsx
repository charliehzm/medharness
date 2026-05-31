import { type ReactNode, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";

import AppShell from "./AppShell";
import {
  NAV_BY_ID,
  NAV_GROUP_LABEL,
  ROLE_NAV,
  isLocked,
  type NavItem,
  type RoleId,
} from "./nav";

const SCREEN_IDS: NavItem["id"][] = [
  "overview",
  "traffic",
  "audit",
  "cost",
  "access",
  "policy",
  "system",
];

const SCREEN_COPY: Record<NavItem["id"], { note: string }> = {
  overview: { note: "四目标卡、六闸门、需要注意与本月小结将从这里接入。" },
  traffic: { note: "双向桑基、双色事件流与三态过滤将从这里接入。" },
  audit: { note: "事件流、检索、血缘与导出监管包将从这里接入。" },
  cost: { note: "成本 KPI、渠道构成、比价与省钱建议将从这里接入。" },
  access: { note: "接入应用、用户、令牌与分组将从这里接入。" },
  policy: { note: "合规、安全、成本护栏与审批差异将从这里接入。" },
  system: { note: "部署健康、备份与升级入口将从这里接入。" },
};

const styles = `
.screen-shell{display:grid;gap:16px;max-width:980px}
.screen-card{background:var(--surface);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow-elev-1);padding:24px}
.screen-kicker{font-size:12px;font-weight:800;letter-spacing:.4px;color:var(--cost)}
.screen-card h2{margin:8px 0 8px;font-size:28px;line-height:1.12;color:var(--navy)}
.screen-desc{margin:0;color:var(--muted);font-size:14px;line-height:1.7}
.screen-chip-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
.screen-chip{padding:6px 10px;border-radius:999px;border:1px solid var(--line);background:var(--bg);color:var(--muted);font-size:12px;font-weight:600}
.screen-chip.primary{background:var(--teal-bg);color:var(--teal-d);border-color:var(--teal-bg)}
.screen-chip.warn{background:var(--cost-bg);color:var(--cost);border-color:var(--cost-border)}
.screen-chip.neutral{background:var(--surface);color:var(--text);border-color:var(--line)}
.screen-note{display:flex;gap:12px;align-items:flex-start;padding:16px 18px;border-radius:12px;background:var(--bg);border:1px dashed var(--line);color:var(--muted);font-size:13px;line-height:1.6}
.screen-note b{color:var(--text)}
`;

function roleLandPath(role: RoleId): string {
  return NAV_BY_ID[ROLE_NAV[role].land].path;
}

function roleLabel(role: RoleId): string {
  return role === "rdlead" ? "研发负责人" : "系统管理员";
}

function Screen({
  id,
  role,
  onRoleChange,
  onNavigate,
}: {
  id: NavItem["id"];
  role: RoleId;
  onRoleChange: (role: RoleId) => void;
  onNavigate: (id: NavItem["id"]) => void;
}): ReactNode {
  const nav = NAV_BY_ID[id];

  if (isLocked(role, id)) {
    return <Navigate replace to={roleLandPath(role)} />;
  }

  const groupLabel = nav.group ? NAV_GROUP_LABEL[nav.group] : "四目标";

  return (
    <AppShell
      activeId={id}
      onNavigate={onNavigate}
      onRoleChange={onRoleChange}
      role={role}
      title={nav.label}
    >
      <div className="screen-shell">
        <style>{styles}</style>
        <section className="screen-card">
          <div className="screen-kicker">{groupLabel}</div>
          <h2>{nav.label}</h2>
          <p className="screen-desc">🚧 规划中 · 仅展示占位符、哈希与聚合数。</p>
          <div className="screen-chip-row" aria-label="页面状态">
            <span className="screen-chip primary">0 PHI</span>
            <span className="screen-chip warn">built:false</span>
            <span className="screen-chip neutral">{roleLabel(role)}</span>
          </div>
        </section>
        <section className="screen-note">
          <b>状态</b>
          <span>{SCREEN_COPY[id].note}</span>
        </section>
      </div>
    </AppShell>
  );
}

export default function App() {
  const [role, setRole] = useState<RoleId>("rdlead");
  const navigate = useNavigate();

  const handleRoleChange = (nextRole: RoleId) => {
    setRole(nextRole);
    navigate(roleLandPath(nextRole), { replace: true });
  };

  const handleNavigate = (id: NavItem["id"]) => {
    navigate(NAV_BY_ID[id].path);
  };

  return (
    <Routes>
      {SCREEN_IDS.map((id) => (
        <Route
          key={id}
          path={NAV_BY_ID[id].path}
          element={<Screen id={id} onNavigate={handleNavigate} onRoleChange={handleRoleChange} role={role} />}
        />
      ))}
      <Route path="*" element={<Navigate replace to={roleLandPath(role)} />} />
    </Routes>
  );
}
