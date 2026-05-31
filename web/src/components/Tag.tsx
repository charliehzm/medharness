import type { CSSProperties } from "react";

type TagTone = "compliance" | "security" | "cost" | "muted" | "ok" | "warn" | "bad";

type TagProps = {
  tone?: TagTone;
  children: string;
};

const baseStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  minHeight: 26,
  borderRadius: 999,
  padding: "0 10px",
  fontSize: 12,
  fontWeight: 700,
  lineHeight: 1,
  border: "1px solid transparent",
};

const toneStyle: Record<TagTone, CSSProperties> = {
  compliance: {
    color: "var(--teal-d)",
    background: "var(--teal-bg)",
    borderColor: "var(--compliance-border)",
  },
  security: {
    color: "var(--violet-d)",
    background: "var(--violet-bg)",
    borderColor: "var(--security-border)",
  },
  cost: {
    color: "var(--cost)",
    background: "var(--cost-bg)",
    borderColor: "var(--cost-border)",
  },
  muted: {
    color: "var(--muted)",
    background: "var(--surface)",
    borderColor: "var(--border)",
  },
  ok: {
    color: "var(--ok-d)",
    background: "var(--ok-bg)",
    borderColor: "var(--ok-border)",
  },
  warn: {
    color: "var(--warn-d)",
    background: "var(--warn-bg)",
    borderColor: "var(--warn-border)",
  },
  bad: {
    color: "var(--bad-d)",
    background: "var(--bad-bg)",
    borderColor: "var(--bad-border)",
  },
};

export default function Tag({ tone = "muted", children }: TagProps) {
  return <span style={{ ...baseStyle, ...toneStyle[tone] }}>{children}</span>;
}
