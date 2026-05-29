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
import { assertNoPhi, findPhi, PhiLeakError } from "./sanitize.ts";

const here = dirname(fileURLToPath(import.meta.url));
const fixDir = join(here, "fixtures");

test("所有合成 fixtures 0 PHI（与 api-phi-exfil drill 同口径）", () => {
  const files = readdirSync(fixDir).filter((f) => f.endsWith(".json"));
  assert.ok(files.length >= 8, `fixtures 应 ≥ 8 个，实际 ${files.length}`);
  for (const f of files) {
    const data = JSON.parse(readFileSync(join(fixDir, f), "utf-8"));
    assert.deepEqual(findPhi(data), [], `${f} 不应有 PHI / payload 违规`);
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
