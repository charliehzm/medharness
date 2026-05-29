/**
 * A0 只读聚合 API 契约 · barrel（🔒 单 owner: charliehzm）
 *
 * FE 统一从这里 import：
 *   import { ENDPOINTS, resolveMock, type PostureResponse } from "@/api/contract";
 */
export * from "./types";
export * from "./endpoints";
export { CONTRACT_VERSION, API_BASE } from "./version";
export { resolveMock, type MockResult } from "./mock";
export {
  assertNoPhi,
  findPhi,
  PhiLeakError,
  type Sanitized,
  type PhiViolation,
  type PhiKind,
} from "./sanitize";
