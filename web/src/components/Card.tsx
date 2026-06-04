import type { CSSProperties, ReactNode } from "react";

type CardProps = {
  title?: string;
  eyebrow?: string;
  children: ReactNode;
};

const cardStyle: CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-lg)",
  boxShadow: "var(--shadow-soft)",
};

const headStyle: CSSProperties = {
  padding: "18px 20px 0",
};

const eyebrowStyle: CSSProperties = {
  color: "var(--teal-d)",
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: "0.02em",
};

const titleStyle: CSSProperties = {
  margin: "6px 0 0",
  color: "var(--primary)",
  fontSize: 18,
  lineHeight: 1.25,
};

const bodyStyle: CSSProperties = {
  padding: "14px 20px 18px",
};

export default function Card({ title, eyebrow, children }: CardProps) {
  return (
    <section style={cardStyle}>
      {(eyebrow || title) && (
        <header style={headStyle}>
          {eyebrow ? <div style={eyebrowStyle}>{eyebrow}</div> : null}
          {title ? <h2 style={titleStyle}>{title}</h2> : null}
        </header>
      )}
      <div style={bodyStyle}>{children}</div>
    </section>
  );
}
