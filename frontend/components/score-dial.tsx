import type { Classification } from "@/lib/api";
import { CLASS_COLOR } from "./classification";
import { fmtScore } from "@/lib/utils";

/** Semicircular dial with the WARM / HOT thresholds marked, so the score can be read against them. */
export function ScoreDial({
  score,
  classification,
  hot,
  warm,
}: {
  score: number;
  classification: Classification;
  hot: number;
  warm: number;
}) {
  const cx = 130, cy = 125, r = 98;
  const pt = (f: number, rad = r) => {
    const t = Math.PI * (1 - f);
    return [cx + rad * Math.cos(t), cy - rad * Math.sin(t)];
  };
  const [sx, sy] = pt(0);
  const [ex, ey] = pt(1);
  const [vx, vy] = pt(Math.min(Math.max(score, 0), 100) / 100);
  const tick = (value: number, label: string) => {
    const [x1, y1] = pt(value / 100, r - 12);
    const [x2, y2] = pt(value / 100, r + 10);
    const [lx, ly] = pt(value / 100, r + 24);
    return (
      <g key={label}>
        <line x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--ink)" strokeWidth={2} />
        <text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" fontSize="11" fill="var(--muted)">
          {label} {value}
        </text>
      </g>
    );
  };
  return (
    <svg viewBox="0 0 260 168" role="img" className="w-full max-w-[300px]"
      aria-label={`Lead score ${fmtScore(score)} out of 100, classified ${classification}`}>
      <path d={`M ${sx} ${sy} A ${r} ${r} 0 0 1 ${ex} ${ey}`} fill="none" stroke="var(--soft)" strokeWidth={16} strokeLinecap="round" />
      {score > 0 && (
        <path d={`M ${sx} ${sy} A ${r} ${r} 0 0 1 ${vx} ${vy}`} fill="none" stroke={CLASS_COLOR[classification]} strokeWidth={16} strokeLinecap="round" />
      )}
      {tick(warm, "Warm")}
      {tick(hot, "Hot")}
      <text x={cx} y={cy - 18} textAnchor="middle" fontSize="52" fontWeight="700" fill="var(--ink)" className="num">
        {fmtScore(score)}
      </text>
      <text x={cx} y={cy + 8} textAnchor="middle" fontSize="13" fill="var(--muted)">
        out of 100
      </text>
    </svg>
  );
}
