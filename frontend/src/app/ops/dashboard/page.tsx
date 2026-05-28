"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle, TrendingUp, FileText, Shield,
  RefreshCw, Filter, Clock, Flag, CheckSquare, Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getOpsAnalytics, listCases } from "@/lib/api";
import type { OpsAnalytics, DisputeCase } from "@/types";
import MetricsCard from "@/components/dashboard/MetricsCard";
import CaseCard from "@/components/dispute/CaseCard";

const PRIORITY_ORDER = ["CRITICAL","HIGH","MEDIUM","LOW"] as const;
const PRIORITY_COLORS: Record<string, string> = {
  CRITICAL: "bg-red-500",
  HIGH:     "bg-orange-500",
  MEDIUM:   "bg-yellow-500",
  LOW:      "bg-green-500",
};

const QUEUE_DISPLAY: Record<string, string> = {
  FRAUD_OPS:         "Fraud Ops",
  ATM_INVESTIGATION: "ATM",
  CHARGEBACK_TEAM:   "Chargeback",
  COMPLIANCE_REVIEW: "Compliance",
  HIGH_PRIORITY:     "High Priority",
  GENERAL:           "General",
  UNASSIGNED:        "Unassigned",
};

export default function OpsDashboard() {
  const [analytics, setAnalytics] = useState<OpsAnalytics | null>(null);
  const [cases, setCases]         = useState<DisputeCase[]>([]);
  const [total, setTotal]         = useState(0);
  const [loading, setLoading]     = useState(true);
  const [filterPriority, setFilterPriority] = useState("");
  const [filterStatus, setFilterStatus]     = useState("");
  const [refreshKey, setRefreshKey]         = useState(0);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getOpsAnalytics(),
      listCases({ limit: 50, priority: filterPriority || undefined, status: filterStatus || undefined }),
    ])
      .then(([a, c]) => { setAnalytics(a); setCases(c.cases); setTotal(c.total); })
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
            <span className="text-xs text-bfsi-gold font-semibold tracking-widest uppercase">Operations Centre</span>
          </div>
          <h1 className="text-2xl font-bold text-bfsi-text">Dispute Resolution Dashboard</h1>
          <p className="text-bfsi-text-dim text-sm mt-1">Live operations overview · All queues</p>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/ops/queues" className="btn-ghost flex items-center gap-2 text-sm">
            <Layers className="w-4 h-4" /> Queues
          </Link>
          <Link href="/ops/search" className="btn-ghost flex items-center gap-2 text-sm">
            <Filter className="w-4 h-4" /> Search
          </Link>
          <button onClick={() => setRefreshKey((k) => k + 1)} className="btn-ghost flex items-center gap-2">
            <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            Refresh
          </button>
        </div>
      </div>

      {/* Primary metrics */}
      {analytics ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          <MetricsCard title="Total Cases"      value={analytics.total_cases}       subtitle="All time"            icon={FileText}   accent="gold" />
          <MetricsCard title="Open Cases"       value={analytics.open_cases}        subtitle="Requires action"     icon={TrendingUp} accent="blue" />
          <MetricsCard title="Fraud Indicators" value={analytics.fraud_cases}       subtitle={`${analytics.total_cases ? ((analytics.fraud_cases / analytics.total_cases)*100).toFixed(1) : 0}% of total`} icon={AlertTriangle} accent="red" />
          <MetricsCard title="Resolution Rate"  value={`${analytics.resolution_rate}%`} subtitle={`${analytics.resolved_cases} resolved`} icon={CheckSquare} accent="green" />
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="metric-card animate-pulse">
              <div className="h-4 bg-bfsi-muted rounded w-24 mb-4" />
              <div className="h-8 bg-bfsi-muted rounded w-16" />
            </div>
          ))}
        </div>
      )}

      {/* Secondary metrics */}
      {analytics ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div className="bfsi-card p-4 flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-red-500/10 flex items-center justify-center flex-shrink-0">
              <Clock className="w-5 h-5 text-red-400" />
            </div>
            <div>
              <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider">SLA Breached</p>
              <p className="text-xl font-bold text-red-400">{analytics.sla_breached_cases}</p>
            </div>
          </div>
          <div className="bfsi-card p-4 flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-amber-500/10 flex items-center justify-center flex-shrink-0">
              <Flag className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider">Manual Review</p>
              <p className="text-xl font-bold text-amber-400">{analytics.manual_review_cases}</p>
            </div>
          </div>
          <div className="bfsi-card p-4 flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-bfsi-gold/10 flex items-center justify-center flex-shrink-0">
              <Shield className="w-5 h-5 text-bfsi-gold" />
            </div>
            <div>
              <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider">Critical Cases</p>
              <p className="text-xl font-bold text-bfsi-gold">{analytics.critical_cases}</p>
            </div>
          </div>
          <div className="bfsi-card p-4 flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-500/10 flex items-center justify-center flex-shrink-0">
              <TrendingUp className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider">New (7 days)</p>
              <p className="text-xl font-bold text-blue-400">{analytics.new_cases_7d}</p>
            </div>
          </div>
        </div>
      ) : null}

      {/* Breakdowns */}
      {analytics && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
          <div className="bfsi-card p-5">
            <p className="section-header">Priority Breakdown</p>
            <div className="space-y-3">
              {PRIORITY_ORDER.map((p) => {
                const count = analytics.by_priority[p] || 0;
                const pct = analytics.total_cases ? Math.round((count / analytics.total_cases) * 100) : 0;
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
          <div className="bfsi-card p-5">
            <p className="section-header">Queue Distribution</p>
            <div className="space-y-2">
              {Object.entries(analytics.by_queue).sort((a, b) => b[1] - a[1]).map(([q, count]) => (
                <Link key={q} href={`/ops/queues`}
                  className="flex items-center justify-between bg-bfsi-muted rounded-md px-3 py-2 hover:bg-bfsi-border transition-colors">
                  <span className="text-xs text-bfsi-text-muted">{QUEUE_DISPLAY[q] || q}</span>
                  <span className="text-xs font-mono font-semibold text-bfsi-gold">{count}</span>
                </Link>
              ))}
              {Object.keys(analytics.by_queue).length === 0 && (
                <p className="text-xs text-bfsi-text-dim">No cases assigned to queues yet</p>
              )}
            </div>
          </div>
          <div className="bfsi-card p-5">
            <p className="section-header">Transaction Categories</p>
            <div className="space-y-2">
              {Object.entries(analytics.by_category).sort((a, b) => b[1] - a[1]).map(([cat, count]) => (
                <div key={cat} className="flex items-center justify-between bg-bfsi-muted rounded-md px-3 py-2">
                  <span className="text-xs text-bfsi-text-muted truncate">{cat}</span>
                  <span className="text-xs font-mono font-semibold text-bfsi-gold ml-2">{count}</span>
                </div>
              ))}
              {Object.keys(analytics.by_category).length === 0 && (
                <p className="text-xs text-bfsi-text-dim">No cases yet</p>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="gold-divider" />

      {/* Cases list */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5">
        <h2 className="text-base font-semibold text-bfsi-text">
          Recent Cases
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
          {[...Array(3)].map((_, i) => (
            <div key={i} className="bfsi-card p-5 animate-pulse">
              <div className="h-4 bg-bfsi-muted rounded w-48 mb-3" />
              <div className="h-3 bg-bfsi-muted rounded w-32" />
            </div>
          ))}
        </div>
      ) : cases.length === 0 ? (
        <div className="bfsi-card p-12 text-center">
          <FileText className="w-10 h-10 text-bfsi-text-dim mx-auto mb-3" />
          <p className="text-bfsi-text-muted">No cases found</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {cases.map((c) => <CaseCard key={c.case_id} case_data={c} />)}
        </div>
      )}
    </>
  );
}
