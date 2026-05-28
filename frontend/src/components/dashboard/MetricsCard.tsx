"use client";
import { cn } from "@/lib/utils";

interface MetricsCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ElementType;
  iconColor?: string;
  trend?: { value: number; label: string };
  accent?: "gold" | "red" | "green" | "blue";
}

export default function MetricsCard({
  title, value, subtitle, icon: Icon, iconColor, trend, accent = "gold",
}: MetricsCardProps) {
  const accentMap = {
    gold:  { bar: "bg-bfsi-gold",  icon: "bg-bfsi-gold/10 border-bfsi-gold/20 text-bfsi-gold" },
    red:   { bar: "bg-red-500",    icon: "bg-red-400/10 border-red-400/20 text-red-400" },
    green: { bar: "bg-green-500",  icon: "bg-green-400/10 border-green-400/20 text-green-400" },
    blue:  { bar: "bg-blue-500",   icon: "bg-blue-400/10 border-blue-400/20 text-blue-400" },
  };

  const { bar, icon } = accentMap[accent];

  return (
    <div className="metric-card">
      {/* Accent bar */}
      <div className={cn("absolute top-0 left-0 right-0 h-0.5 rounded-t-lg", bar)} />

      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-xs font-medium text-bfsi-text-dim uppercase tracking-wider mb-3">{title}</p>
          <p className="text-3xl font-bold text-bfsi-text font-mono">{value}</p>
          {subtitle && <p className="text-xs text-bfsi-text-dim mt-1">{subtitle}</p>}
          {trend && (
            <div className="flex items-center gap-1 mt-2">
              <span className={cn("text-xs font-medium", trend.value >= 0 ? "text-green-400" : "text-red-400")}>
                {trend.value >= 0 ? "↑" : "↓"} {Math.abs(trend.value)}%
              </span>
              <span className="text-[11px] text-bfsi-text-dim">{trend.label}</span>
            </div>
          )}
        </div>
        <div className={cn("w-10 h-10 rounded-lg border flex items-center justify-center flex-shrink-0", icon)}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  );
}
