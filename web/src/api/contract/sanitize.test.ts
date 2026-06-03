/**
 * A0 契约 · 0 PHI 守卫测试（node:test · 类型擦除直跑，不依赖 F1 工具链）
 *
 *   node --experimental-strip-types --test web/src/api/contract/sanitize.test.ts
 *
 * 与 python `drill_api_phi_exfil.py` 同口径：fixtures 必须 0 PHI；对抗样本必被抓；
 * 违规记录绝不含原文。
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { assertNoPatientPhi, assertNoPhi, findPatientPhi, findPhi, PhiLeakError } from "./sanitize.ts";

const here = dirname(fileURLToPath(import.meta.url));
const fixDir = join(here, "fixtures");

// 管理面用户列表 fixture 是**唯一**合法携带运营人员（**非患者**）邮箱的 fixture：
// 它走患者-only 守卫 assertNoPatientPhi（放行 email），不经 dashboard 级 assertNoPhi。
// 故从「全量 0 PHI」blanket 循环中豁免，单独按患者-only 口径核验（见下一条 test）。
const PATIENT_ONLY_FIXTURES = new Set(["admin_users_mgmt.json"]);

test("所有合成 fixtures 0 PHI（与 api-phi-exfil drill 同口径）", () => {
  const files = readdirSync(fixDir).filter((f) => f.endsWith(".json"));
  assert.ok(files.length >= 8, `fixtures 应 ≥ 8 个，实际 ${files.length}`);
  for (const f of files) {
    if (PATIENT_ONLY_FIXTURES.has(f)) continue;
    const data = JSON.parse(readFileSync(join(fixDir, f), "utf-8"));
    assert.deepEqual(findPhi(data), [], `${f} 不应有 PHI / payload 违规`);
  }
});

test("管理面 fixture：患者 0 PHI（放行 STAFF email，仍拦患者标识）", () => {
  for (const f of PATIENT_ONLY_FIXTURES) {
    const data = JSON.parse(readFileSync(join(fixDir, f), "utf-8"));
    // 患者-only 守卫必须通过：身份证 / 手机 / 卡号 / 护照 / payload 仍 0。
    assert.deepEqual(findPatientPhi(data), [], `${f} 不应含患者 PHI`);
    assert.doesNotThrow(() => assertNoPatientPhi(data, `fixture ${f}`));
    // 反证：carve-out 是真的——全量 assertNoPhi 在此 fixture 上**只**因 email 命中，
    // 证明放行的仅是邮箱、患者标识未被顺带放过。
    const full = findPhi(data);
    assert.ok(full.length > 0, `${f} 应被全量守卫因 email 命中`);
    assert.ok(full.every((v) => v.kind === "email"), `${f} 全量命中应仅限 email`);
  }
});

test("占位符 / 哈希 / 聚合数 / 百分比不误报", () => {
  assert.deepEqual(
    findPhi({ a: "__NAME_a1__", b: "routing#a1b2", c: 1627, d: "100%", e: "block #18,420" }),
    [],
  );
  assert.deepEqual(findPhi({ sha256: "a".repeat(64) }), []); // 纯 hex 不算 PHI
});

test("对抗样本：手机 / 身份证 / 邮箱 / 银行卡必被抓", () => {
  const kinds = findPhi({
    phone: "13800138000",
    id: "11010119900307391X",
    email: "patient@hospital.cn",
    card: "6222021234567890123",
  })
    .map((v) => v.kind)
    .sort();
  for (const k of ["bank_card", "cn_id", "cn_phone", "email"]) {
    assert.ok(kinds.includes(k as never), `应命中 ${k}`);
  }
});

test("违规记录绝不含原文（守卫自身 0 PHI）", () => {
  const v = findPhi({ phone: "13800138000", email: "patient@hospital.cn" });
  const dump = JSON.stringify(v);
  assert.ok(!dump.includes("13800138000"));
  assert.ok(!dump.includes("patient@hospital.cn"));
});

test("payload != null = 违规（安全事件不回显）", () => {
  const v = findPhi({ alerts: [{ payload: "注入指令原文" }] });
  assert.equal(v.length, 1);
  assert.equal(v[0].kind, "payload_not_null");
  assert.ok(!JSON.stringify(v).includes("注入指令原文"));
});

test("assertNoPhi：通过返回原值、命中抛 PhiLeakError", () => {
  const clean = { composite: 92, alerts: [{ payload: null }] };
  assert.equal(assertNoPhi(clean), clean);
  assert.throws(() => assertNoPhi({ phone: "13800138000" }, "GET /test"), PhiLeakError);
});
