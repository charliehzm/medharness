/**
 * INT-2 · api-client LIVE-path seam test (vitest).
 *
 * Verifies the M3 mock->live cutover code in client.ts: in live mode every
 * successful response transits assertNoPhi before it can reach React state, and
 * every failure maps to a GENERIC error code (no upstream body / PHI leak). This
 * is the FE half of the contract seam (INT-1 is the A0/BE half).
 *
 * Pure logic — no DOM — so the default vitest node env is enough.
 */
import { describe, expect, it, vi } from "vitest";

import { login, requestEndpoint } from "@/api/client";
import { PhiLeakError } from "@/api/contract";
import traffic from "@/api/contract/fixtures/traffic.json";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api-client live path", () => {
  it("returns the sanitized contract body and builds API_BASE + query URL", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(traffic));

    const data = await requestEndpoint("traffic", {
      mode: "live",
      fetchImpl,
      query: { window: "24h" },
    });

    expect(data).toEqual(traffic);
    expect(fetchImpl).toHaveBeenCalledOnce();
    const calls = fetchImpl.mock.calls as unknown as Array<[RequestInfo | URL, RequestInit?]>;
    const url = String(calls[0]![0]);
    expect(url).toContain("/api/v1/traffic");
    expect(url).toContain("window=24h");
  });

  it("maps a non-200 to the EXACT generic api_http_error (no upstream body leaks)", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ upstream_secret: "should-never-surface" }, 500));

    let caught: unknown;
    try {
      await requestEndpoint("posture", { mode: "live", fetchImpl });
    } catch (e) {
      caught = e;
    }
    // exact generic shape — nothing from the upstream body may ride along
    expect(caught).toEqual({ error: { code: "api_http_error", msg: "请求失败" } });
    const serialized = JSON.stringify(caught);
    expect(serialized).not.toContain("should-never-surface");
    expect(serialized).not.toContain("upstream_secret");
  });

  it("maps invalid JSON to the exact generic api_invalid_json", async () => {
    const fetchImpl = vi.fn(async () => new Response("not-json{", { status: 200 }));

    await expect(
      requestEndpoint("posture", { mode: "live", fetchImpl }),
    ).rejects.toEqual({ error: { code: "api_invalid_json", msg: "请求失败" } });
  });

  it("maps a fetch/network throw to the exact generic api_network_error", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error("connection refused");
    });

    await expect(
      requestEndpoint("posture", { mode: "live", fetchImpl }),
    ).rejects.toEqual({ error: { code: "api_network_error", msg: "请求失败" } });
  });

  it("BLOCKS a PHI-dirty live response before it reaches state (0-PHI seam)", async () => {
    const dirty = { ...(traffic as object), _leak: "patient.leak@hospital.com" };
    const fetchImpl = vi.fn(async () => jsonResponse(dirty));

    await expect(
      requestEndpoint("traffic", { mode: "live", fetchImpl, query: { window: "24h" } }),
    ).rejects.toBeInstanceOf(PhiLeakError);
  });

  it("never calls fetch in mock mode (default), so screens render offline", async () => {
    const fetchImpl = vi.fn();

    const data = await requestEndpoint("posture", { mode: "mock", fetchImpl });

    expect(fetchImpl).not.toHaveBeenCalled();
    expect(data).toBeTruthy();
  });
});

describe("api-client login", () => {
  it("live: POSTs {username,password} to /api/v1/auth/login and maps the role", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ ok: true, role: "sysadmin", username: "root", display_name: "Root" }),
    );

    const result = await login("root", "secret123", { mode: "live", fetchImpl });

    expect(result).toEqual({ ok: true, role: "sysadmin", username: "root", displayName: "Root", token: "" });
    expect(fetchImpl).toHaveBeenCalledOnce();
    const calls = fetchImpl.mock.calls as unknown as Array<[RequestInfo | URL, RequestInit]>;
    expect(String(calls[0]![0])).toContain("/api/v1/auth/login");
    expect(calls[0]![1].method).toBe("POST");
    expect(JSON.parse(String(calls[0]![1].body))).toEqual({ username: "root", password: "secret123" });
  });

  it("live: bad credentials (401) throw the EXACT generic error with no backend leak", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ error: { code: "unauthorized", msg: "用户名或密码错误" }, leak: "user not found in db" }, 401),
    );

    let caught: unknown;
    try {
      await login("root", "wrong", { mode: "live", fetchImpl });
    } catch (e) {
      caught = e;
    }
    expect(caught).toEqual({ error: { code: "api_http_error", msg: "请求失败" } });
    expect(JSON.stringify(caught)).not.toContain("user not found");
  });

  it("live: a network throw maps to the generic api_network_error", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error("connection refused");
    });

    await expect(login("root", "secret123", { mode: "live", fetchImpl })).rejects.toEqual({
      error: { code: "api_network_error", msg: "请求失败" },
    });
  });

  it("mock: non-empty creds pass as a demo gate; 'admin' lands sysadmin; never fetches", async () => {
    const fetchImpl = vi.fn();

    const dev = await login("dev", "x", { mode: "mock", fetchImpl });
    const admin = await login("admin-ops", "x", { mode: "mock", fetchImpl });

    expect(dev.role).toBe("rdlead");
    expect(admin.role).toBe("sysadmin");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("mock: empty credentials are rejected", async () => {
    await expect(login("", "", { mode: "mock" })).rejects.toEqual({
      error: { code: "api_request_error", msg: "请求失败" },
    });
  });
});
