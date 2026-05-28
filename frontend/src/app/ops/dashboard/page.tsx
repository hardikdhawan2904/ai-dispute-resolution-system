"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, TrendingUp, FileText, Shield, Plus, RefreshCw, Filter, Brain } from "lucide-react";
// CaseCard handles its own link navigation via href prop
import { formatConfidence, cn } from "@/lib/utils";
import { listCases, getDashboardStats } from "@/lib/api";
import type { DashboardStats, DisputeCase } from "@/types";
import MetricsCard from "@/components/dashboard/MetricsCard";
import CaseCard from "@/components/dispute/CaseCard";

const PRIORITY_ORDER = ["CRITICAL","HIGH","MEDIUM","LOW"] as const;
const PRIORITY_COLORS: Record<string, string> = { CRITICAL:"bg-red-500", HIGH:"bg-orange-500", MEDIUM:"bg-yellow-500", LOW:"bg-green-500" };

export default function OpsDashboard() {
  const [stats, setStats]               = useState<DashboardStats | null>(null);
  const [cases, setCases]               = useState<DisputeCase[]>([]);
  const [total, setTotal]               = useState(0);
  const [loading, setLoading]           = useState(true);
  const [filterPriority, setFilterPriority] = useState("");
  const [filterStatus, setFilterStatus]     = useState("");
  const [refreshKey, setRefreshKey]         = useState(0);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getDashboardStats(),
      listCases({ limit: 50, priority: filterPriority || undefined, status: filterStatus || undefined }),
    ])
      .then(([s, c]) => { setStats(s); setCases(c.cases); setTotal(c.total); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [refreshKey, filterPriority, filterStatus]);

  return (
    <>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1 h-5 bg-bfsi-gold rounded-full" />
            <span className="text-xs text-bfsi-gold font-semibold tracking-widest uppercase">Operations Center</span>
          </div>
          <h1 className="text-2xl font-bold text-bfsi-text">AI Dispute Resolution Dashboard</h1>
          <p className="text-bfsi-text-dim text-sm mt-1">Real-time case intelligence powered by LangGraph</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => setRefreshKey((k) => k + 1)} className="btn-ghost flex items-center gap-2">
            <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            Refresh
          </button>
          <Link href="/ops/disputes?new=1" className="btn-gold flex items-center gap-2">
            <Plus className="w-4 h-4" />
            New Case
          </Link>
        </div>
      </div>

      {/* Metrics */}
      {stats ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <MetricsCard title="Total Cases"    value={stats.total_cases}  subtitle="All time"           icon={FileText}       accent="gold" />
          <MetricsCard title="Open Cases"     value={stats.open_cases}   subtitle="Requires action"    icon={TrendingUp}     accent="blue" />
          <MetricsCard title="Fraud Cases"    value={stats.fraud_cases}  subtitle={`${stats.total_cases ? ((stats.fraud_cases / stats.total_cases)*100).toFixed(1) : 0}% of total`} icon={AlertTriangle} accent="red" />
          <MetricsCard title="AI Confidence"  value={formatConfidence(stats.avg_confidence_score)} subtitle="Average score" icon={Shield} accent="green" />
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          {[...Array(4)].map((_, i) => <div key={i} className="metric-card animate-pulse"><div className="h-4 bg-bfsi-muted rounded w-24 mb-4" /><div className="h-8 bg-bfsi-muted rounded w-16" /></div>)}
        </div>
      )}

      {/* Breakdowns */}
      {stats && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
          <div className="bfsi-card p-5">
            <p className="section-header">Priority Breakdown</p>
            <div className="space-y-3">
              {PRIORITY_ORDER.map((p) => {
                const count = stats.cases_by_priority[p] || 0;
                const pct = total ? Math.round((count / total) * 100) : 0;
                return (
                  <div key={p}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-bfsi-text-muted">{p}</span>
                      <span className="text-bfsi-text font-mono">{count}</span>
                    </div>
                    <div className="h-1.5 bg-bfsi-muted rounded-full overflow-hidden">
                      <div className={cn("h-full rounded-full transition-all duration-700", PRIORITY_COLORS[p])} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="bfsi-card p-5 lg:col-span-2">
            <p className="section-header">Category Distribution</p>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(stats.cases_by_category).sort((a, b) => b[1] - a[1]).map(([cat, count]) => (
                <div key={cat} className="flex items-center justify-between bg-bfsi-muted rounded-md px-3 py-2">
                  <span className="text-xs text-bfsi-text-muted truncate">{cat}</span>
                  <span className="text-xs font-mono font-semibold text-bfsi-gold ml-2">{count}</span>
                </div>
              ))}
              {Object.keys(stats.cases_by_category).length === 0 && (
                <p className="text-xs text-bfsi-text-dim col-span-2">No cases yet</p>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="gold-divider" />

      {/* Cases list */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5">
        <h2 className="text-base font-semibold text-bfsi-text">
          Recent Dispute Cases
          <span className="text-bfsi-text-dim text-sm font-normal ml-2">({total})</span>
        </h2>
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-bfsi-text-dim" />
          <select className="bfsi-select text-xs py-1.5 px-2 w-auto" value={filterPriority} onChange={(e) => setFilterPriority(e.target.value)}>
            <option value="">All Priorities</option>
            {PRIORITY_ORDER.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <select className="bfsi-select text-xs py-1.5 px-2 w-auto" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="">All Statuses</option>
            {["Dispute Raised","Under Investigation","Pending Documents","Escalated","Resolved","Rejected","Closed"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => <div key={i} className="bfsi-card p-5 animate-pulse"><div className="h-4 bg-bfsi-muted rounded w-48 mb-3" /><div className="h-3 bg-bfsi-muted rounded w-32" /></div>)}
        </div>
      ) : cases.length === 0 ? (
        <div className="bfsi-card p-12 text-center">
          <Brain className="w-10 h-10 text-bfsi-text-dim mx-auto mb-3" />
          <p className="text-bfsi-text-muted">No cases found</p>
          <p className="text-bfsi-text-dim text-sm mt-1">Submit a new dispute to get started.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {cases.map((c) => (
            <CaseCard key={c.case_id} case_data={c} />
          ))}
        </div>
      )}
    </>
  );
}
