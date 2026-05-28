"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ClipboardCheck, AlertTriangle, CheckCircle, RefreshCw, ChevronRight } from "lucide-react";
import { listCases, getDashboardStats } from "@/lib/api";
import type { DisputeCase, DashboardStats } from "@/types";
import { cn, getPriorityColor, getStatusColor, formatCurrency, formatDate } from "@/lib/utils";

export default function OpsCompliancePage() {
  const [allCases, setAllCases] = useState<DisputeCase[]>([]);
  const [stats, setStats]       = useState<DashboardStats | null>(null);
  const [loading, setLoading]   = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    Promise.all([listCases({ limit: 200 }), getDashboardStats()])
      .then(([r, s]) => { setAllCases(r.cases); setStats(s); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [refreshKey]);

  const escalated   = allCases.filter((c) => c.status === "Escalated");
  const highValue   = allCases.filter((c) => c.amount >= 100000);
  const intl        = allCases.filter((c) => c.risk_tags?.includes("INTERNATIONAL_TRANSACTION"));
  const needsReview = allCases.filter((c) => ["Dispute Raised","Escalated"].includes(c.status) && c.priority === "CRITICAL");

  const COMPLIANCE_METRICS = [
    { label:"Escalated Cases",     value: escalated.length,   color:"text-red-400",    urgent: escalated.length > 0 },
    { label:"High-Value (>₹1L)",   value: highValue.length,   color:"text-orange-400", urgent: false },
    { label:"International Txns",  value: intl.length,        color:"text-yellow-400", urgent: false },
    { label:"Critical Unreviewed", value: needsReview.length, color:"text-red-400",    urgent: needsReview.length > 0 },
  ];

  return (
    <>
      <div className="flex items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1 h-5 bg-purple-500 rounded-full" />
            <span className="text-xs text-purple-400 font-semibold tracking-widest uppercase">Compliance & Regulatory</span>
          </div>
          <h1 className="text-2xl font-bold text-bfsi-text">Compliance Dashboard</h1>
          <p className="text-bfsi-text-dim text-sm mt-1">Regulatory compliance monitoring and escalation management</p>
        </div>
        <button onClick={() => setRefreshKey((k) => k + 1)} className="btn-ghost flex items-center gap-2">
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} /> Refresh
        </button>
      </div>

      {/* Compliance metrics */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {COMPLIANCE_METRICS.map((m) => (
          <div key={m.label} className={cn("bfsi-card p-5", m.urgent && "border border-red-400/30")}>
            {m.urgent && <AlertTriangle className="w-4 h-4 text-red-400 mb-2" />}
            <p className="text-bfsi-text-dim text-xs mb-2">{m.label}</p>
            <p className={cn("text-2xl font-bold font-mono", m.color)}>{m.value}</p>
          </div>
        ))}
      </div>

      {/* Status breakdown for compliance */}
      {stats && (
        <div className="bfsi-card p-5 mb-6">
          <p className="section-header">Case Status Distribution</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {Object.entries(stats.cases_by_status).map(([status, count]) => (
              <div key={status} className="bg-bfsi-muted rounded-lg px-3 py-3">
                <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wide mb-1">{status}</p>
                <p className="text-xl font-bold text-bfsi-text font-mono">{count}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Escalated cases — urgent */}
      {escalated.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="w-4 h-4 text-red-400" />
            <h2 className="text-base font-semibold text-red-400">Escalated Cases — Immediate Attention Required</h2>
          </div>
          <div className="space-y-3">
            {escalated.map((c) => (
              <Link key={c.case_id} href={`/ops/case/${c.case_id}`}>
                <div className="bfsi-card border border-red-400/30 p-5 hover:border-red-400/50 transition-all cursor-pointer flex items-center gap-4">
                  <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-bfsi-text">{c.merchant}</p>
                    <p className="text-xs text-bfsi-text-dim">{c.customer_name} · {c.case_id.slice(-10)}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="font-mono font-bold text-bfsi-text">{formatCurrency(c.amount, c.currency)}</p>
                    <p className="text-xs text-bfsi-text-dim">{formatDate(c.created_at)}</p>
                  </div>
                  <ChevronRight className="w-4 h-4 text-bfsi-text-dim shrink-0" />
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* High-value cases */}
      <div className="mb-6">
        <h2 className="text-base font-semibold text-bfsi-text mb-4">
          High-Value Cases (≥ ₹1,00,000)
          <span className="text-bfsi-text-dim font-normal text-sm ml-2">({highValue.length})</span>
        </h2>
        {highValue.length === 0 ? (
          <div className="bfsi-card p-8 text-center">
            <CheckCircle className="w-8 h-8 text-green-400 mx-auto mb-2" />
            <p className="text-bfsi-text-muted text-sm">No high-value cases requiring review</p>
          </div>
        ) : (
          <div className="bfsi-card overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-bfsi-border">
                  {["Case ID","Customer","Merchant","Amount","Priority","Status"].map((h) => (
                    <th key={h} className="text-left text-xs text-bfsi-text-dim font-medium px-4 py-3">{h}</th>
                  ))}
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-bfsi-border">
                {highValue.slice(0, 20).map((c) => (
                  <tr key={c.case_id} className="hover:bg-bfsi-muted/50 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-bfsi-gold">{c.case_id.slice(-10)}</td>
                    <td className="px-4 py-3 text-xs text-bfsi-text">{c.customer_name ?? "—"}</td>
                    <td className="px-4 py-3 text-xs text-bfsi-text-muted">{c.merchant}</td>
                    <td className="px-4 py-3 font-mono text-xs font-bold text-bfsi-text">{formatCurrency(c.amount, c.currency)}</td>
                    <td className="px-4 py-3">
                      <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full border", getPriorityColor(c.priority as any))}>
                        {c.priority}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("text-[10px] px-2 py-0.5 rounded-full border", getStatusColor(c.status as any))}>
                        {c.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <Link href={`/ops/case/${c.case_id}`} className="text-bfsi-gold hover:text-bfsi-text">
                        <ChevronRight className="w-4 h-4" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
