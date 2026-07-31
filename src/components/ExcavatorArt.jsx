import React from "react";

export function ExcavatorArt({ className }) {
  return (
    <svg
      viewBox="0 0 640 420"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Illustration of a tracked excavator with a live telemetry tag"
    >
      <ellipse cx="320" cy="378" rx="260" ry="18" fill="#0D1013" />

      {/* tracks */}
      <rect x="150" y="300" width="230" height="56" rx="28" fill="#1C2126" stroke="#3A4249" strokeWidth="2" />
      {Array.from({ length: 8 }).map((_, i) => (
        <circle key={i} cx={172 + i * 27} cy="328" r="13" fill="#272E35" stroke="#5B6570" strokeWidth="1.5" />
      ))}

      {/* undercarriage / body */}
      <rect x="185" y="248" width="180" height="60" rx="6" fill="#F2B705" stroke="#0D1013" strokeWidth="3" />
      <rect x="185" y="248" width="180" height="14" fill="#0D1013" opacity="0.15" />

      {/* cab */}
      <path d="M225 190 h95 a14 14 0 0 1 14 14 v44 h-129 v-38 a20 20 0 0 1 20-20 z" fill="#F2B705" stroke="#0D1013" strokeWidth="3" />
      <rect x="238" y="204" width="58" height="34" rx="4" fill="#8A939C" opacity="0.55" stroke="#0D1013" strokeWidth="2" />
      <circle cx="270" cy="270" r="34" fill="#1C2126" stroke="#0D1013" strokeWidth="3" />
      <circle cx="270" cy="270" r="9" fill="#5B6570" />

      {/* boom arm */}
      <rect x="255" y="180" width="26" height="120" rx="8" fill="#D9531E" stroke="#0D1013" strokeWidth="3" transform="rotate(-28 268 240)" />
      <rect x="330" y="120" width="22" height="140" rx="8" fill="#D9531E" stroke="#0D1013" strokeWidth="3" transform="rotate(38 341 190)" />

      {/* bucket */}
      <path d="M430 165 l48 14 -8 34 -46 4 -18 -30 z" fill="#272E35" stroke="#0D1013" strokeWidth="3" />

      {/* telemetry tag */}
      <g transform="translate(420 250)">
        <rect x="0" y="0" width="150" height="70" rx="6" fill="#14181C" stroke="#F2B705" strokeWidth="2" />
        <circle cx="14" cy="14" r="3" fill="#D7DBDE" opacity="0.3" />
        <circle cx="136" cy="14" r="3" fill="#D7DBDE" opacity="0.3" />
        <text x="14" y="26" fontFamily="'JetBrains Mono', monospace" fontSize="10" fill="#8A939C">
          UNIT EQX-1002
        </text>
        <circle cx="18" cy="42" r="4" fill="#3FA34D" />
        <text x="30" y="46" fontFamily="'JetBrains Mono', monospace" fontSize="11" fill="#EDEFF2">
          LIVE · 118.4 HR
        </text>
        <text x="14" y="62" fontFamily="'JetBrains Mono', monospace" fontSize="9" fill="#5B6570">
          SITE 04 · FUEL 71%
        </text>
      </g>
    </svg>
  );
}
