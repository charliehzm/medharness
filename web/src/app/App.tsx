import { type ReactNode, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";

import AppShell from "./AppShell";
import "./App.css";
import Access from "@/views/Access";
import Audit from "@/views/Audit";
import Cost from "@/views/Cost";
import Overview from "@/views/Overview";
import Policy from "@/views/Policy";
import System from "@/views/System";
import Traffic from "@/views/Traffic";
import Login from "@/views/Login";
import {
  NAV_BY_ID,
  ROLE_NAV,
  isLocked,
  type NavItem,
  type RoleId,
} from "./nav";
import { clearSession, loadSession } from "@/api/session";

const SCREEN_IDS: NavItem["id"][] = [
  "overview",
  "traffic",
  "audit",
  "cost",
  "access",
  "policy",
  "system",
];

function roleLandPath(role: RoleId): string {
  return NAV_BY_ID[ROLE_NAV[role].land].path;
}

function Screen({
  id,
  role,
  onRoleChange,
  onLock,
  onNavigate,
}: {
  id: NavItem["id"];
  role: RoleId;
  onRoleChange: (role: RoleId) => void;
  onLock: () => void;
  onNavigate: (id: NavItem["id"]) => void;
}): ReactNode {
  const nav = NAV_BY_ID[id];

  if (isLocked(role, id)) {
    return <Navigate replace to={roleLandPath(role)} />;
  }

  return (
    <AppShell
      activeId={id}
      onNavigate={onNavigate}
      onLock={onLock}
      onRoleChange={onRoleChange}
      role={role}
      title={nav.label}
    >
      {id === "overview" ? (
        <Overview />
      ) : id === "traffic" ? (
        <Traffic />
      ) : id === "audit" ? (
        <Audit />
      ) : id === "cost" ? (
        <Cost />
      ) : id === "access" ? (
        <Access />
      ) : id === "policy" ? (
        <Policy />
      ) : (
        <System />
      )}
    </AppShell>
  );
}

type AuthState = {
  authed: boolean;
  role: RoleId;
};

export default function App() {
  // Restore from the persisted session on boot so a browser refresh keeps the user
  // logged in (the in-memory-only default is what made every refresh bounce to /login).
  const [auth, setAuth] = useState<AuthState>(() => {
    const session = loadSession();
    return session ? { authed: true, role: session.role } : { authed: false, role: "rdlead" };
  });
  const navigate = useNavigate();

  const handleLogin = (role: RoleId) => {
    setAuth({ authed: true, role });
    navigate(roleLandPath(role), { replace: true });
  };

  const handleLock = () => {
    clearSession();
    setAuth({ authed: false, role: auth.role });
    navigate("/login", { replace: true });
  };

  const handleRoleChange = (nextRole: RoleId) => {
    setAuth({ authed: true, role: nextRole });
    navigate(roleLandPath(nextRole), { replace: true });
  };

  const handleNavigate = (id: NavItem["id"]) => {
    navigate(NAV_BY_ID[id].path);
  };

  const initialPath = auth.authed ? roleLandPath(auth.role) : "/login";

  return (
    <Routes>
      <Route
        path="/login"
        element={auth.authed ? <Navigate replace to={roleLandPath(auth.role)} /> : <Login onLogin={handleLogin} />}
      />
      {SCREEN_IDS.map((id) => (
        <Route
          key={id}
          path={NAV_BY_ID[id].path}
          element={
            auth.authed ? (
              <Screen id={id} onLock={handleLock} onNavigate={handleNavigate} onRoleChange={handleRoleChange} role={auth.role} />
            ) : (
              <Navigate replace to={initialPath} />
            )
          }
        />
      ))}
      <Route path="*" element={<Navigate replace to={initialPath} />} />
    </Routes>
  );
}
