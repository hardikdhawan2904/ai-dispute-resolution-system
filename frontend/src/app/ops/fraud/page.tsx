"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Shield, ChevronRight, RefreshCw, TrendingUp } from "lucide-react";
import { listCases, getDashboardStats } from "@/lib/api";
import type { DisputeCase, DashboardStats } from "@/types";
import { cn, getPriorityColor, getStatusColor, formatCurrency, formatConfidence, getConfidenceColor } from "@/lib/utils";
import RiskTags from "@/components/dispute/RiskTags";

const FRAUD_RISK_TAGS = ["POSSIBLE_FRAUD","OTP_VERIFIED","DEVICE_MISMATCH","SUSPICIOUS_BEHAVIOR","MERCHANT_BLACKLISTED","VELOCITY_BREACH","CARD_NOT_PRESENT"];

export default function OpsfraudPage() {
  const [fraudCases, setFraudCases] = useState<DisputeCase[]>([]);
  const [stats, setStats]           = useState<DashboardStats | null>(null);
  const [loading, setLoading]       = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      listCases({ limit: 200, fraud_only: true } as any),
      getDashboardStats(),
    ]).then(([r, s]) => {
      setFraudCases(r.cases);
      setStats(s);
    }).catch(console.error).finally(() => setLoading(false));
  }, [refreshKey]);

  const criticalFraud = fraudCases.filter((c) => c.priority === "CRITICAL");
  const highFraud     = fraudCases.filter((c) => c.priority === "HIGH");
  const totalAmount   = fraudCases.reduce((s, c) => s + c.amount, 0);

  return (
    <>
      <div className="flex items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1 h-5 bg-red-500 rounded-full" />
            <span className="text-xs text-red-400 font-semibold tracking-widest uppercase">Fraud Intelligence</span>
          </div>
          <h1 className="text-2xl font-bold text-bfsi-text">Fraud Analysis Center</h1>
          <p className="text-bfsi-text-dim text-sm mt-1">AI-detected fraud signals and suspicious transaction patterns</p>
        </div>
        <button onClick={() => setRefreshKey((k) => k + 1)} className="btn-ghost flex items-center gap-2">
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} /> Refresh
        </button>
      </div>

      {/* Fraud metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[
          { label:"Fraud Suspected",  value: fraudCases.length,     color:"text-red-400",    bg:"bg-red-400/10 border-red-400/20" },
          { label:"Critical Cases",   value: criticalFraud.length,  color:"text-orange-400", bg:"bg-orange-400/10 border-orange-400/20" },
          { label:"High Priority",    value: highFraud.length,      color:"text-yellow-400", bg:"bg-yellow-400/10 border-yellow-400/20" },
          { label:"Total at Risk",    value: `₹${(totalAmount/1000).toFixed(0)}K`, color:"text-red-300", bg:"bg-red-300/10 border-red-300/20" },
        ].map((m) => (
          <div key={m.label} className={cn("bfsi-card border p-5", m.bg)}>
            <p className="text-bfsi-text-dim text-xs mb-2">{m.label}</p>
            <p className={cn("text-2xl font-bold font-mono", m.color)}>{m.value}</p>
          </div>
        ))}
      </div>

      {/* Risk tag frequency */}
      {fraudCases.length > 0 && (
        <div className="bfsi-card p-5 mb-6">
          <p className="section-header">Fraud Signal Frequency</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {FRAUD_RISK_TAGS.map((tag) => {
              const count = fraudCases.filter((c) => c.risk_tags?.includes(tag as any)).length;
              if (count === 0) return null;
              return (
                <div key={tag} className="bg-red-400/5 border border-red-400/20 rounded-lg px-3 py-2">
                  <p className="text-[10px] text-red-300 font-mono uppercase tracking-wide mb-1">{tag.replace(/_/g," ")}</p>
                  <p className="text-lg font-bold text-red-400 font-mono">{count}</p>
                </div>
              );
            }).filter(Boolean)}
          </div>
        </div>
      )}

      {/* Fraud cases list */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-bfsi-text">
          Fraud-Suspected Cases
          <span className="text-bfsi-text-dim text-sm font-normal ml-2">({fraudCases.length})</span>
        </h2>
      </div>

      {loading ? (
        <div className="space-y-2">{[...Array(4)].map((_, i) => <div key={i} className="bfsi-card p-4 animate-pulse h-16" />)}</div>
      ) : fraudCases.length === 0 ? (
        <div className="bfsi-card p-12 text-center">
          <Shield className="w-10 h-10 text-green-400 mx-auto mb-3" />
          <p className="text-bfsi-text-muted font-medium">No fraud-suspected cases</p>
          <p className="text-bfsi-text-dim text-sm">All current cases are within normal risk parameters.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {fraudCases.sort((a, b) => {
            const order = { CRITICAL:0, HIGH:1, MEDIUM:2, LOW:3 };
            return (order[a.priority as keyof typeof order] ?? 4) - (order[b.priority as keyof typeof order] ?? 4);
          }).map((c) => (
            <Link key={c.case_id} href={`/ops/case/${c.case_id}`}>
              <div className="bfsi-card border border-red-400/20 p-5 hover:border-red-400/40 transition-all cursor-pointer">
                <div className="flex items-start justify-between gap-4 mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <AlertTriangle className="w-4 h-4 text-red-400" />
                      <span className="text-xs font-mono text-bfsi-text-dim">{c.case_id}</span>
                      <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full border", getPriorityColor(c.priority as any))}>
                        {c.priority}
                      </span>
                    </div>
                    <p className="font-semibold text-bfsi-text">{c.merchant}</p>
                    <p className="text-xs text-bfsi-text-dim">{c.customer_name} · {c.customer_id}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-lg font-bold text-bfsi-text font-mono">{formatCurrency(c.amount, c.currency)}</p>
                    <p className={cn("text-sm font-semibold", getConfidenceColor(c.confidence_score))}>
                      {formatConfidence(c.confidence_score)} confidence
                    </p>
                  </div>
                </div>
                {c.risk_tags?.length > 0 && <RiskTags tags={c.risk_tags} />}
                <div className="flex items-center justify-between mt-2 pt-2 border-t border-bfsi-border">
                  <span className={cn("text-xs px-2 py-0.5 rounded-full border", getStatusColor(c.status as any))}>
                    {c.status}
                  </span>
                  <ChevronRight className="w-4 h-4 text-bfsi-text-dim" />
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
