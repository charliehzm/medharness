import { type ReactNode, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";

import AppShell from "./AppShell";
import "./App.css";
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
