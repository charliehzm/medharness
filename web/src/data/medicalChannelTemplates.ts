// Curated medical channel templates for the channel-create "从目录预填" dropdown.
// Mirrors deploy/presets/channel-templates.medical.json (kept in sync by hand — the
// preset is the deployable source of truth, this is the Console convenience copy).
// Prefill only; the operator still supplies the real key and confirms compliance.

export interface MedicalChannelTemplate {
  /** dropdown label */
  label: string;
  /** prefilled channel name */
  name: string;
  /** provider type name (A0 maps it to the new-api int) */
  type: string;
  /** comma-separated model ids */
  models: string;
  /** new-api group */
  group: string;
  /** prefilled service URL (placeholder for private deployments) */
  baseUrl: string;
}

export const MEDICAL_CHANNEL_TEMPLATES: MedicalChannelTemplate[] = [
  { label: "DeepSeek 境内·常规便宜池 (L2)", name: "DeepSeek 境内·常规便宜池", type: "deepseek", models: "deepseek-v3", group: "default", baseUrl: "" },
  { label: "Qwen-Max 境内·常规 (L2)", name: "Qwen-Max 境内·常规", type: "ali", models: "qwen-max", group: "default", baseUrl: "" },
  { label: "Qwen2.5 私有部署·敏感·含PHI (L4)", name: "Qwen2.5 私有部署·敏感", type: "openai", models: "local-qwen", group: "sensitive", baseUrl: "http://REPLACE-vllm-host:8000/v1" },
  { label: "Lingshu-32B 私有·敏感·医疗多模态 (L4)", name: "Lingshu-32B 私有部署·敏感", type: "openai", models: "lingshu-32b", group: "sensitive", baseUrl: "http://REPLACE-vllm-host:8000/v1" },
  { label: "HuatuoGPT-o1-8B 私有·敏感·临床推理 (L4)", name: "HuatuoGPT-o1-8B 私有部署·敏感", type: "openai", models: "huatuogpt-o1-8b", group: "sensitive", baseUrl: "http://REPLACE-vllm-host:8000/v1" },
  { label: "百川医疗 API 境内·常规·脱敏后 (L2)", name: "百川医疗 API 境内·常规", type: "baichuan", models: "baichuan-m1", group: "default", baseUrl: "" },
  { label: "Claude-Sonnet 境外·常规·默认禁PHI (L2)", name: "Claude-Sonnet 境外·常规", type: "anthropic", models: "claude-sonnet-4.6", group: "default", baseUrl: "" },
  { label: "GPT-4o 境外·常规·默认禁PHI (L2)", name: "GPT-4o 境外·常规", type: "openai", models: "gpt-4o", group: "default", baseUrl: "" },
];
