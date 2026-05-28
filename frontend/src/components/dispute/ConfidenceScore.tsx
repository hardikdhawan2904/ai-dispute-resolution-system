"use client";
import { cn, formatConfidence, getConfidenceColor, getConfidenceLabel } from "@/lib/utils";

interface ConfidenceScoreProps {
  score: number;
  showLabel?: boolean;
  size?: "sm" | "md" | "lg";
}

export default function ConfidenceScore({ score, showLabel = true, size = "md" }: ConfidenceScoreProps) {
  const pct = Math.round(score * 100);
  const color = getConfidenceColor(score);
  const label = getConfidenceLabel(score);

  const trackColor =
    score >= 0.8 ? "bg-green-400" :
    score >= 0.6 ? "bg-yellow-400" :
    score >= 0.4 ? "bg-orange-400" : "bg-red-400";

  if (size === "lg") {
    return (
      <div className="space-y-3">
        <div className="flex items-end justify-between">
          <div>
            <div className={cn("text-4xl font-bold font-mono", color)}>{formatConfidence(score)}</div>
            {showLabel && <div className="text-xs text-bfsi-text-dim mt-1">{label} Confidence</div>}
          </div>
          <ConfidenceCircle score={score} pct={pct} trackColor={trackColor} color={color} />
        </div>

        {/* Progress bar */}
        <div className="h-2 bg-bfsi-muted rounded-full overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all duration-700", trackColor)}
            style={{ width: `${pct}%` }}
          />
        </div>

        {/* Scale labels */}
        <div className="flex justify-between text-[10px] text-bfsi-text-dim font-mono">
          <span>0%</span>
          <span>25%</span>
          <span>50%</span>
          <span>75%</span>
          <span>100%</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-1.5 bg-bfsi-muted rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-500", trackColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className={cn("font-mono font-semibold whitespace-nowrap", size === "sm" ? "text-xs" : "text-sm", color)}>
        {formatConfidence(score)}
      </div>
      {showLabel && (
        <div className="text-xs text-bfsi-text-dim hidden sm:block">{label}</div>
      )}
    </div>
  );
}

function ConfidenceCircle({
  score, pct, trackColor, color
}: { score: number; pct: number; trackColor: string; color: string }) {
  const r = 28;
  const circumference = 2 * Math.PI * r;
  const strokeDash = circumference * score;

  const strokeColor =
    score >= 0.8 ? "#10b981" :
    score >= 0.6 ? "#f59e0b" :
    score >= 0.4 ? "#f97316" : "#ef4444";

  return (
    <div className="relative w-20 h-20">
      <svg className="w-20 h-20 -rotate-90" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r={r} fill="none" stroke="#1e1e32" strokeWidth="6" />
        <circle
          cx="36" cy="36" r={r}
          fill="none"
          stroke={strokeColor}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={`${strokeDash} ${circumference}`}
          className="transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className={cn("text-sm font-bold font-mono", color)}>{pct}%</span>
      </div>
    </div>
  );
}
