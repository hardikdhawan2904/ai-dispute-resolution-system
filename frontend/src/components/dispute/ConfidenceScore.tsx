import { cn, getConfidenceLabel } from "@/lib/utils";

interface ConfidenceScoreProps {
  score: number;
  showLabel?: boolean;
  size?: "sm" | "md" | "lg";
}

/** Conservative bar-style confidence meter. No circles or neon. */
export default function ConfidenceScore({ score, showLabel = true, size = "md" }: ConfidenceScoreProps) {
  const pct   = Math.round(score * 100);
  const label = getConfidenceLabel(score);

  const barColor =
    score >= 0.75 ? "#15803D" :
    score >= 0.55 ? "#B45309" : "#B91C1C";

  const textColor =
    score >= 0.75 ? "#4ADE80" :
    score >= 0.55 ? "#FCD34D" : "#FCA5A5";

  if (size === "lg") {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">
              Investigation Confidence
            </div>
            {showLabel && (
              <div style={{ color: textColor }} className="text-xs font-semibold">{label}</div>
            )}
          </div>
          <div style={{ color: textColor }} className="text-xl font-bold font-sans">{pct}%</div>
        </div>
        {/* Bar */}
        <div className="h-1.5 bg-slate-700 rounded-sm overflow-hidden">
          <div style={{ width: `${pct}%`, backgroundColor: barColor }} className="h-full rounded-sm transition-[width] duration-500 ease" />
        </div>
        {/* Scale */}
        <div className="flex justify-between text-[10px] text-slate-500 font-mono">
          <span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2.5">
      <div className="flex-1 h-1 bg-slate-700 rounded-sm overflow-hidden">
        <div style={{ width: `${pct}%`, backgroundColor: barColor }} className="h-full rounded-sm transition-[width] duration-400 ease" />
      </div>
      <div
        style={{ color: textColor }}
        className={cn("font-mono font-semibold whitespace-nowrap", size === "sm" ? "text-[11.2px]" : "text-xs")}
      >
        {pct}%
      </div>
      {showLabel && (
        <div className="text-[10px] text-slate-500 hidden sm:block">{label}</div>
      )}
    </div>
  );
}
