"use client";

import { useEffect, useState } from "react";
import { Brain, RefreshCw, TrendingUp, AlertTriangle, Shield } from "lucide-react";
import { listCases, getDashboardStats } from "@/lib/api";
import type { DisputeCase, DashboardStats } from "@/types";
import { cn, formatConfidence, getConfidenceColor } from "@/lib/utils";

const RISK_TAGS_ALL = [
  "HIGH_VALUE_TRANSACTION","INTERNATIONAL_TRANSACTION","POSSIBLE_FRAUD","DUPLICATE_PAYMENT",
  "FRIENDLY_FRAUD_RISK","HIGH_PRIORITY_CASE","OTP_VERIFIED","DEVICE_MISMATCH",
  "SUSPICIOUS_BEHAVIOR","CARD_NOT_PRESENT","RECURRING_DISPUTE","MERCHANT_BLACKLISTED","VELOCITY_BREACH",
];

const CONFIDENCE_BUCKETS = [
  { label:"Very High (85–100%)", min:0.85, max:1.01,  color:"text-green-400",  bar:"bg-green-500" },
  { label:"High (70–85%)",       min:0.70, max:0.85,  color:"text-emerald-400",bar:"bg-emerald-500" },
  { label:"Moderate (55–70%)",   min:0.55, max:0.70,  color:"text-yellow-400", bar:"bg-yellow-500" },
  { label:"Low (40–55%)",        min:0.40, max:0.55,  color:"text-orange-400", bar:"bg-orange-500" },
  { label:"Very Low (0–40%)",    min:0.00, max:0.40,  color:"text-red-400",    bar:"bg-red-500" },
];

export default function OpsAnalysisPage() {
  const [cases, setCases]     = useState<DisputeCase[]>([]);
  const [stats, setStats]     = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    Promise.all([listCases({ limit: 200 }), getDashboardStats()])
      .then(([r, s]) => { setCases(r.cases); setStats(s); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [refreshKey]);

  const avgConfidence    = cases.length ? cases.reduce((s, c) => s + c.confidence_score, 0) / cases.length : 0;
  const fraudRate        = cases.length ? (cases.filter((c) => c.fraud_suspicion).length / cases.length * 100).toFixed(1) : "0";
  const criticalRate     = cases.length ? (cases.filter((c) => c.priority === "CRITICAL").length / cases.length * 100).toFixed(1) : "0";

  const tagCounts = RISK_TAGS_ALL.reduce((acc, tag) => {
    acc[tag] = cases.filter((c) => c.risk_tags?.includes(tag as any)).length;
    return acc;
  }, {} as Record<string, number>);

  const sortedTags = Object.entries(tagCounts).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  const maxTag = sortedTags[0]?.[1] || 1;

  return (
    <>
      <div className="flex items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1 h-5 bg-bfsi-gold rounded-full" />
            <span className="text-xs text-bfsi-gold font-semibold tracking-widest uppercase">AI Intelligence</span>
          </div>
          <h1 className="text-2xl font-bold text-bfsi-text">AI Analysis Center</h1>
          <p className="text-bfsi-text-dim text-sm mt-1">Confidence scores, classification performance, and risk signal intelligence</p>
        </div>
        <button onClick={() => setRefreshKey((k) => k + 1)} className="btn-ghost flex items-center gap-2">
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} /> Refresh
        </button>
      </div>

      {/* AI performance summary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <div className="bfsi-card p-5 bfsi-card-accent">
          <div className="flex items-center gap-2 mb-3">
            <Brain className="w-4 h-4 text-bfsi-gold" />
            <p className="text-xs text-bfsi-text-dim uppercase tracking-wider">Avg AI Confidence</p>
          </div>
          <p className={cn("text-4xl font-bold font-mono", getConfidenceColor(avgConfidence))}>
            {formatConfidence(avgConfidence)}
          </p>
          <p className="text-xs text-bfsi-text-dim mt-1">Across {cases.length} analyzed cases</p>
        </div>
        <div className="bfsi-card p-5">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-4 h-4 text-red-400" />
            <p className="text-xs text-bfsi-text-dim uppercase tracking-wider">Fraud Detection Rate</p>
          </div>
          <p className="text-4xl font-bold font-mono text-red-400">{fraudRate}%</p>
          <p className="text-xs text-bfsi-text-dim mt-1">Cases flagged as potential fraud</p>
        </div>
        <div className="bfsi-card p-5">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="w-4 h-4 text-orange-400" />
            <p className="text-xs text-bfsi-text-dim uppercase tracking-wider">Critical Case Rate</p>
          </div>
          <p className="text-4xl font-bold font-mono text-orange-400">{criticalRate}%</p>
          <p className="text-xs text-bfsi-text-dim mt-1">Cases classified as CRITICAL</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Confidence distribution */}
        <div className="bfsi-card p-5">
          <p className="section-header">AI Confidence Distribution</p>
          <div className="space-y-3">
            {CONFIDENCE_BUCKETS.map((bucket) => {
              const count = cases.filter((c) => c.confidence_score >= bucket.min && c.confidence_score < bucket.max).length;
              const pct   = cases.length ? (count / cases.length) * 100 : 0;
              return (
                <div key={bucket.label}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className={bucket.color}>{bucket.label}</span>
                    <span className="text-bfsi-text font-mono">{count} ({pct.toFixed(0)}%)</span>
                  </div>
                  <div className="h-2 bg-bfsi-muted rounded-full overflow-hidden">
                    <div className={cn("h-full rounded-full transition-all duration-700", bucket.bar)} style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Category performance */}
        <div className="bfsi-card p-5">
          <p className="section-header">Category Classification Performance</p>
          {stats ? (
            <div className="space-y-2">
              {Object.entries(stats.cases_by_category).sort((a, b) => b[1] - a[1]).map(([cat, count]) => {
                const catCases = cases.filter((c) => c.dispute_category === cat);
                const catAvgConf = catCases.length ? catCases.reduce((s, c) => s + c.confidence_score, 0) / catCases.length : 0;
                return (
                  <div key={cat} className="flex items-center justify-between p-2.5 bg-bfsi-muted rounded-lg gap-2">
                    <span className="text-xs text-bfsi-text-muted flex-1 truncate">{cat}</span>
                    <span className="text-xs font-mono text-bfsi-text shrink-0">{count} cases</span>
                    <span className={cn("text-xs font-mono font-semibold shrink-0", getConfidenceColor(catAvgConf))}>
                      {formatConfidence(catAvgConf)}
                    </span>
                  </div>
                );
              })}
              {Object.keys(stats.cases_by_category).length === 0 && (
                <p className="text-xs text-bfsi-text-dim">No case data available</p>
              )}
            </div>
          ) : <div className="animate-pulse h-32 bg-bfsi-muted rounded" />}
        </div>
      </div>

      {/* Risk tag heatmap */}
      <div className="bfsi-card p-5">
        <p className="section-header">Risk Signal Intelligence — Tag Frequency</p>
        {sortedTags.length === 0 ? (
          <p className="text-sm text-bfsi-text-dim">No risk tags detected in current case set.</p>
        ) : (
          <div className="space-y-2">
            {sortedTags.map(([tag, count]) => {
              const pct = (count / maxTag) * 100;
              const isDanger = ["POSSIBLE_FRAUD","OTP_VERIFIED","DEVICE_MISMATCH","SUSPICIOUS_BEHAVIOR","MERCHANT_BLACKLISTED","VELOCITY_BREACH"].includes(tag);
              return (
                <div key={tag}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className={isDanger ? "text-red-400" : "text-bfsi-text-muted"}>
                      {tag.replace(/_/g," ")}
                    </span>
                    <span className="font-mono text-bfsi-text">{count} cases ({(count / cases.length * 100).toFixed(1)}%)</span>
                  </div>
                  <div className="h-1.5 bg-bfsi-muted rounded-full overflow-hidden">
                    <div
                      className={cn("h-full rounded-full transition-all duration-700", isDanger ? "bg-red-500" : "bg-bfsi-gold/60")}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
