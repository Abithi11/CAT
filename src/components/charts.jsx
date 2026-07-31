import React, { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";

// Measures the real rendered width of a container so charts can be drawn at
// exact pixel scale instead of being stretched by a mismatched SVG viewBox.
function useMeasuredWidth(fallback = 600) {
  const ref = useRef(null);
  const [width, setWidth] = useState(fallback);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect?.width;
      if (w) setWidth(w);
    });
    observer.observe(el);
    setWidth(el.getBoundingClientRect().width || fallback);
    return () => observer.disconnect();
  }, [fallback]);

  return [ref, width];
}

function roundedTopRectPath(x, y, w, h, r) {
  const radius = Math.min(r, w / 2, Math.max(h, 0));
  if (h <= 0) return `M ${x} ${y + h} L ${x + w} ${y + h} Z`;
  return `
    M ${x} ${y + h}
    L ${x} ${y + radius}
    Q ${x} ${y} ${x + radius} ${y}
    L ${x + w - radius} ${y}
    Q ${x + w} ${y} ${x + w} ${y + radius}
    L ${x + w} ${y + h}
    Z
  `;
}

const STATUS_COLORS = { ok: "#3FA34D", warn: "#F2B705", danger: "#D9531E" };

function statusFor(value, goodMin, warnMin) {
  if (value >= goodMin) return "ok";
  if (value >= warnMin) return "warn";
  return "danger";
}

// Full-width, pixel-accurate bar chart. Fills whatever height/width its
// parent gives it -- no distortion, no cramped bars.
export function BarChart({
  data,
  valueKey,
  labelKey,
  unit = "",
  height = 320,
  color = "#F2B705",
  colorByStatus = false,
  goodMin = 75,
  warnMin = 55,
}) {
  const [ref, width] = useMeasuredWidth(600);
  const max = Math.max(...data.map((d) => d[valueKey]), 1);
  const n = data.length;

  const padX = 28;
  const topPad = 44;
  const bottomPad = 40;
  const usableWidth = Math.max(width - padX * 2, 10);
  const plotHeight = Math.max(height - topPad - bottomPad, 10);

  const gapRatio = 0.55;
  let barWidth = usableWidth / (n + (n - 1) * gapRatio);
  barWidth = Math.min(barWidth, 140);
  const gap = barWidth * gapRatio;
  const contentWidth = n * barWidth + (n - 1) * gap;
  const startX = padX + (usableWidth - contentWidth) / 2;

  return (
    <div ref={ref} className="w-full" style={{ height }}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <line
          x1={padX}
          x2={width - padX}
          y1={height - bottomPad}
          y2={height - bottomPad}
          stroke="#272E35"
          strokeWidth={1}
        />
        {data.map((d, i) => {
          const value = d[valueKey];
          const h = (value / max) * plotHeight;
          const x = startX + i * (barWidth + gap);
          const y = height - bottomPad - h;
          const fill = colorByStatus ? STATUS_COLORS[statusFor(value, goodMin, warnMin)] : color;

          return (
            <g key={d[labelKey]}>
              <motion.path
                d={roundedTopRectPath(x, height - bottomPad, barWidth, 0, 6)}
                fill={fill}
                initial={{ d: roundedTopRectPath(x, height - bottomPad, barWidth, 0, 6) }}
                animate={{ d: roundedTopRectPath(x, y, barWidth, h, 6) }}
                transition={{ duration: 0.6, delay: i * 0.06, ease: [0.16, 1, 0.3, 1] }}
              />
              <motion.text
                x={x + barWidth / 2}
                y={y - 12}
                textAnchor="middle"
                fontFamily="'JetBrains Mono', monospace"
                fontSize={Math.min(16, barWidth * 0.22)}
                fontWeight={700}
                fill="#EDEFF2"
                initial={{ opacity: 0, y: y - 4 }}
                animate={{ opacity: 1, y: y - 12 }}
                transition={{ duration: 0.4, delay: i * 0.06 + 0.35 }}
              >
                {value}
                {unit}
              </motion.text>
              <text
                x={x + barWidth / 2}
                y={height - bottomPad + 22}
                textAnchor="middle"
                fontFamily="'JetBrains Mono', monospace"
                fontSize={12}
                fill="#8A939C"
              >
                {d[labelKey]}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// Renders a probability band (low/high) with a median line -- for forecast distributions.
export function BandChart({ points, height = 320 }) {
  const [ref, width] = useMeasuredWidth(600);
  const padX = 40;
  const topPad = 36;
  const bottomPad = 36;
  const maxVal = Math.max(...points.map((p) => p.high)) * 1.1;
  const plotHeight = height - topPad - bottomPad;
  const usableWidth = width - padX * 2;

  const scaleY = (v) => topPad + plotHeight - (v / maxVal) * plotHeight;
  const scaleX = (i) => padX + (points.length === 1 ? usableWidth / 2 : (i / (points.length - 1)) * usableWidth);

  const bandPath =
    points.map((p, i) => `${i === 0 ? "M" : "L"} ${scaleX(i)} ${scaleY(p.high)}`).join(" ") +
    " " +
    [...points]
      .reverse()
      .map((p, i) => `L ${scaleX(points.length - 1 - i)} ${scaleY(p.low)}`)
      .join(" ") +
    " Z";

  const medianPath = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${scaleX(i)} ${scaleY(p.median)}`)
    .join(" ");

  return (
    <div ref={ref} className="w-full" style={{ height }}>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1={padX}
            x2={width - padX}
            y1={topPad + plotHeight * f}
            y2={topPad + plotHeight * f}
            stroke="#1C2126"
            strokeWidth={1}
          />
        ))}
        <motion.path
          d={bandPath}
          fill="#F2B705"
          initial={{ opacity: 0 }}
          animate={{ opacity: 0.15 }}
          transition={{ duration: 0.6 }}
        />
        <motion.path
          d={medianPath}
          fill="none"
          stroke="#F2B705"
          strokeWidth={2.5}
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.9, ease: "easeInOut" }}
        />
        {points.map((p, i) => (
          <g key={p.label}>
            <motion.circle
              cx={scaleX(i)}
              cy={scaleY(p.median)}
              r={5}
              fill="#F2B705"
              stroke="#0D1013"
              strokeWidth={2}
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: i * 0.08 + 0.5, type: "spring", stiffness: 300 }}
            />
            <text
              x={scaleX(i)}
              y={scaleY(p.high) - 14}
              textAnchor="middle"
              fontFamily="'JetBrains Mono', monospace"
              fontSize={13}
              fontWeight={600}
              fill="#8A939C"
            >
              {p.high}
            </text>
            <text
              x={scaleX(i)}
              y={height - bottomPad + 24}
              textAnchor="middle"
              fontFamily="'JetBrains Mono', monospace"
              fontSize={13}
              fill="#5B6570"
            >
              {p.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

// Renders a usage history line with a healthy baseline band and a marked change-point (degradation onset).
export function DegradationChart({ series, baselineLow, baselineHigh, changePointIndex, height = 320 }) {
  const [ref, containerWidth] = useMeasuredWidth(600);
  const minPointGap = 26;
  const width = Math.max(containerWidth, series.length * minPointGap);
  const padX = 20;
  const topPad = 20;
  const bottomPad = 36;
  const maxVal = Math.max(...series.map((p) => p.value), baselineHigh) * 1.15;
  const plotHeight = height - topPad - bottomPad;
  const usableWidth = width - padX * 2;

  const scaleY = (v) => topPad + plotHeight - (v / maxVal) * plotHeight;
  const scaleX = (i) => padX + (series.length === 1 ? usableWidth / 2 : (i / (series.length - 1)) * usableWidth);

  const linePath = series
    .map((p, i) => `${i === 0 ? "M" : "L"} ${scaleX(i)} ${scaleY(p.value)}`)
    .join(" ");

  const cpX = changePointIndex != null ? scaleX(changePointIndex) : null;

  return (
    <div ref={ref} className="w-full overflow-x-auto">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <rect
          x={0}
          y={scaleY(baselineHigh)}
          width={width}
          height={scaleY(baselineLow) - scaleY(baselineHigh)}
          fill="#3FA34D"
          opacity={0.1}
        />
        <line
          x1={0}
          x2={width}
          y1={scaleY((baselineLow + baselineHigh) / 2)}
          y2={scaleY((baselineLow + baselineHigh) / 2)}
          stroke="#3FA34D"
          strokeDasharray="4 4"
          strokeWidth={1}
          opacity={0.5}
        />
        <motion.path
          d={linePath}
          fill="none"
          stroke="#8A939C"
          strokeWidth={2}
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1, ease: "easeInOut" }}
        />
        {series.map((p, i) => (
          <circle
            key={i}
            cx={scaleX(i)}
            cy={scaleY(p.value)}
            r={i === changePointIndex ? 6 : 3}
            fill={i >= (changePointIndex ?? Infinity) ? "#D9531E" : "#5B6570"}
          />
        ))}
        {cpX != null && (
          <line x1={cpX} x2={cpX} y1={10} y2={height - bottomPad} stroke="#D9531E" strokeWidth={1.5} strokeDasharray="3 3" />
        )}
      </svg>
    </div>
  );
}
