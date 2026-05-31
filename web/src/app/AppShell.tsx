import { type ReactNode } from "react";
import { Outlet } from "react-router-dom";

import { NAV_GROUP_LABEL, NAV_ITEMS, type NavItem, type RoleId, isLocked } from "./nav";
import "./AppShell.css";

type AppShellProps = {
  role: RoleId;
  onRoleChange?: (role: RoleId) => void;
  activeId?: NavItem["id"];
  title?: string;
  children?: ReactNode;
  onNavigate?: (id: NavItem["id"]) => void;
};

export default function AppShell({
  role,
  onRoleChange,
  activeId = "overview",
  title = "总览",
  children,
  onNavigate,
}: AppShellProps) {
  const renderedGroups = new Set<NonNullable<NavItem["group"]>>();

  return (
    <div className="app-shell">
      <aside className="side">
        <div className="brand">
          <div className="logo">⊕</div>
          <div>
            <b>MedHarness</b>
            <small>医疗大模型流量网关</small>
          </div>
        </div>
        <nav aria-label="主导航">
          {NAV_ITEMS.flatMap((item) => {
            const nodes: ReactNode[] = [];
            if (item.group && !renderedGroups.has(item.group)) {
              renderedGroups.add(item.group);
              nodes.push(
                <div className="nav-grp" key={`group-${item.group}`}>
                  {NAV_GROUP_LABEL[item.group]}
                </div>,
              );
            }
            const locked = isLocked(role, item.id);
            nodes.push(
              <button
                aria-label={locked ? `${item.label}，需研发负责人` : item.label}
                className={`nav-item ${item.id === activeId ? "active" : ""} ${locked ? "disabled" : ""}`}
                key={item.id}
                onClick={() => {
                  if (!locked) onNavigate?.(item.id);
                }}
                title={locked ? "需研发负责人" : undefined}
                type="button"
              >
                <span className="ico">{item.icon}</span>
                <span>{item.label}</span>
                {locked ? <span aria-hidden="true">🔒</span> : null}
              </button>,
            );
            return nodes;
          })}
        </nav>
        <div className="side-foot">
          v0.7 重设计 demo · 合成数据
          <br />
          四目标：安全·划算·审计·稳定
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <h1>
            {title} <small>MedHarness Console</small>
          </h1>
          <div className="top-right">
            <div className="env-pill">
              环境 <b style={{ color: "var(--navy)" }}>生产</b> ▾
            </div>
            <div className="phi-badge">
              <span className="dot" />
              全程 0 PHI
            </div>
            <div className="role-select" aria-label="角色切换">
              <button
                className={role === "rdlead" ? "on" : ""}
                onClick={() => onRoleChange?.("rdlead")}
                type="button"
              >
                研发负责人
              </button>
              <button
                className={role === "sysadmin" ? "on" : ""}
                onClick={() => onRoleChange?.("sysadmin")}
                type="button"
              >
                系统管理员
              </button>
            </div>
            <div className="lock">🔒 锁定</div>
          </div>
        </header>
        <div className="content">
          <div className="view show">{children ?? <Outlet />}</div>
        </div>
      </div>
    </div>
  );
}
