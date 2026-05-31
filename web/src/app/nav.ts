export type RoleId = "rdlead" | "sysadmin";

export type NavGroupId = "security" | "cost" | "governance";

export type NavItem = {
  id: "overview" | "traffic" | "audit" | "cost" | "access" | "policy" | "system";
  label: string;
  icon: string;
  path: string;
  group?: NavGroupId;
};

export const NAV_ITEMS: NavItem[] = [
  { id: "overview", label: "总览", icon: "🏠", path: "/" },
  { id: "traffic", label: "流量监控", icon: "📊", path: "/traffic", group: "security" },
  { id: "audit", label: "审计与报表", icon: "🔍", path: "/audit", group: "security" },
  { id: "cost", label: "用量与成本", icon: "💰", path: "/cost", group: "cost" },
  { id: "access", label: "接入", icon: "🔌", path: "/access", group: "cost" },
  { id: "policy", label: "策略", icon: "⚙️", path: "/policy", group: "governance" },
  { id: "system", label: "系统", icon: "🛠", path: "/system", group: "governance" },
] as const;

export const NAV_GROUP_LABEL: Record<NavGroupId, string> = {
  security: "安全",
  cost: "划算",
  governance: "治理 / 运维",
};

export const ROLE_NAV: Record<RoleId, { nav: NavItem["id"][]; land: NavItem["id"] }> = {
  rdlead: {
    nav: ["overview", "traffic", "audit", "cost", "access", "policy", "system"],
    land: "overview",
  },
  sysadmin: {
    nav: ["overview", "cost", "access", "system"],
    land: "access",
  },
};

export const NAV_BY_ID = Object.fromEntries(NAV_ITEMS.map((item) => [item.id, item])) as Record<
  NavItem["id"],
  NavItem
>;

export function isAllowed(role: RoleId, id: NavItem["id"]): boolean {
  return ROLE_NAV[role].nav.includes(id);
}

export function isLocked(role: RoleId, id: NavItem["id"]): boolean {
  return !isAllowed(role, id);
}
