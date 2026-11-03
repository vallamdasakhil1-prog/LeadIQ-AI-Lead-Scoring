import { Flame, Snowflake, Thermometer } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Classification, Confidence } from "@/lib/api";

const STYLE: Record<Classification, string> = {
  HOT: "bg-hot-bg text-hot",
  WARM: "bg-warm-bg text-warm",
  COLD: "bg-cold-bg text-cold",
};
const ICON = { HOT: Flame, WARM: Thermometer, COLD: Snowflake };

export function ClassificationBadge({ value, className }: { value: Classification; className?: string }) {
  const Icon = ICON[value];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold", STYLE[value], className)}>
      <Icon className="size-3.5" aria-hidden /> {value}
    </span>
  );
}

export function ConfidenceBadge({ value }: { value: Confidence }) {
  const tone = value === "HIGH" ? "text-pos" : value === "MEDIUM" ? "text-warm" : "text-neg";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-ink">
      <span className={cn("size-2 rounded-full bg-current", tone)} aria-hidden />
      {value.charAt(0) + value.slice(1).toLowerCase()} confidence
    </span>
  );
}

export const CLASS_COLOR: Record<Classification, string> = {
  HOT: "var(--hot)",
  WARM: "var(--warm)",
  COLD: "var(--cold)",
};
