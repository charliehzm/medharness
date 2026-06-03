// Persisted Console session — single source of truth for "am I logged in across a
// refresh". The A0-minted Bearer token lives in localStorage; App restores from it
// on boot, client.ts attaches it to every live request, and logout clears it.

export type ConsoleRole = "rdlead" | "sysadmin";

export interface StoredSession {
  token: string;
  role: ConsoleRole;
  username: string;
}

const KEY = "mh.session";

export function saveSession(session: StoredSession): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(session));
  } catch {
    /* storage unavailable (private mode) — session just won't survive a refresh */
  }
}

export function loadSession(): StoredSession | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredSession>;
    if (
      parsed &&
      typeof parsed.token === "string" &&
      typeof parsed.username === "string" &&
      (parsed.role === "rdlead" || parsed.role === "sysadmin")
    ) {
      return { token: parsed.token, role: parsed.role, username: parsed.username };
    }
  } catch {
    /* corrupt payload — treat as logged out */
  }
  return null;
}

export function clearSession(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

export function getToken(): string {
  return loadSession()?.token ?? "";
}

// The new-api role int (100 root / 10 admin / 1 normal), decoded from the token's
// `nr` claim — used by the user-management UI to enforce the role hierarchy (an
// operator may only act on strictly-lower roles). Falls back to the console role
// for mock tokens that aren't a real JWS.
export function getNewApiRole(): number {
  const session = loadSession();
  if (!session) return 0;
  const parts = session.token.split(".");
  if (parts.length === 3) {
    try {
      const json = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
      const nr = (JSON.parse(json) as { nr?: number }).nr;
      if (typeof nr === "number") return nr;
    } catch {
      /* not a decodable JWS payload — fall through */
    }
  }
  return session.role === "sysadmin" ? 10 : 1;
}
