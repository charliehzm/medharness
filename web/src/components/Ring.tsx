import type { CSSProperties } from "react";

type ColorToken = `var(--${string})`;

type RingProps = {
  value: number;
  color: ColorToken;
  label: string;
  denominator?: string;
  size?: number;
};

const DEFAULT_SIZE = 96;
const DEFAULT_RADIUS = 42;
const DEFAULT_STROKE = 9;

const clamp = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, value));

const circleStyle: CSSProperties = {
  display: "inline-grid",
  placeItems: "center",
  position: "relative",
  flex: "none",
};

const contentStyle: CSSProperties = {
  position: "absolute",
  inset: 0,
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
};

const valueStyle: CSSProperties = {
  fontSize: 30,
  fontWeight: 800,
  color: "var(--navy)",
  lineHeight: 1,
};

const denominatorStyle: CSSProperties = {
  fontSize: 10,
  color: "var(--muted)",
  lineHeight: 1.2,
  marginTop: 2,
};

export default function Ring({
  value,
  color,
  label,
  denominator = "/100",
  size = DEFAULT_SIZE,
}: RingProps) {
  const pct = clamp(Number.isFinite(value) ? value : 0, 0, 100);
  const radius = DEFAULT_RADIUS;
  const strokeWidth = DEFAULT_STROKE;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - pct / 100);

  return (
    <div
      aria-label={`${label} ${pct}${denominator}`}
      role="img"
      style={{ ...circleStyle, width: size, height: size }}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${DEFAULT_SIZE} ${DEFAULT_SIZE}`}
        style={{ transform: "rotate(-90deg)" }}
      >
        <circle
          cx={DEFAULT_SIZE / 2}
          cy={DEFAULT_SIZE / 2}
          r={radius}
          fill="none"
          stroke="var(--ring-track)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={DEFAULT_SIZE / 2}
          cy={DEFAULT_SIZE / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeWidth={strokeWidth}
        />
      </svg>
      <div style={contentStyle}>
        <div style={valueStyle}>{pct}</div>
        <div style={denominatorStyle}>
          {label} {denominator}
        </div>
      </div>
    </div>
  );
}
