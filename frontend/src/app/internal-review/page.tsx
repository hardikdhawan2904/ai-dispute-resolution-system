"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import { Brain, RefreshCw, Wifi, WifiOff, AlertTriangle, Loader2, Activity, Search, X, Filter } from "lucide-react";
import { listCases } from "@/lib/api";
import { cn, formatCurrency, formatDate, getPriorityColor, getStatusColor } from "@/lib/utils";
import type { DisputeCase } from "@/types";
import {
  useDisputeSocket,
  type DisputeSocketEvent,
  type DisputeQueuedEvent,
} from "@/hooks/useDisputeSocket";

interface LiveEntry {
  case_id: string;
  status: "analyzing" | "complete" | "failed";
  queued_at: string;
  customer_name?: string;
  merchant?: string;
  amount?: number;
  currency?: string;
  caseData?: DisputeCase;
  errors?: string[];
}

const PRIORITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;
const STATUSES   = ["Dispute Raised","Under Investigation","Pending Documents","Escalated","Resolved","Rejected","Closed"] as const;

const PRIORITY_CHIP: Record<string, string> = {
  CRITICAL: "border-red-500/60 text-red-400 bg-red-500/20",
  HIGH:     "border-orange-500/60 text-orange-400 bg-orange-500/20",
  MEDIUM:   "border-yellow-500/60 text-yellow-400 bg-yellow-500/20",
  LOW:      "border-green-500/60 text-green-400 bg-green-500/20",
};

export default function InternalReviewPage() {
  const [cases, setCases]         = useState<DisputeCase[]>([]);
  const [total, setTotal]         = useState(0);
  const [loading, setLoading]     = useState(true);
  const [liveQueue, setLiveQueue] = useState<LiveEntry[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);

  // Filter state
  const [search,         setSearch]         = useState("");
  const [filterPriority, setFilterPriority] = useState("");
  const [filterStatus,   setFilterStatus]   = useState("");
  const [fraudOnly,      setFraudOnly]      = useState(false);

  useEffect(() => {
    setLoading(true);
    listCases({ limit: 200 })
      .then((r) => { setCases(r.cases); setTotal(r.total); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [refreshKey]);

  const handleSocketEvent = useCallback((event: DisputeSocketEvent) => {
    if (event.type === "DISPUTE_QUEUED") {
      const e = event as DisputeQueuedEvent;
      setLiveQueue((q) => {
        if (q.find((x) => x.case_id === e.case_id)) return q;
        return [{
          case_id: e.case_id, status: "analyzing", queued_at: e.timestamp,
          customer_name: e.customer_name, merchant: e.merchant,
          amount: e.amount, currency: e.currency,
        }, ...q];
      });
    }
    if (event.type === "ANALYSIS_COMPLETE") {
      const caseData = event.case as unknown as DisputeCase;
      setLiveQueue((q) => q.map((x) => x.case_id === event.case_id ? { ...x, status: "complete", caseData } : x));
      setCases((prev) => {
        if (prev.find((c) => c.case_id === event.case_id)) return prev;
        return [caseData, ...prev];
      });
      setTotal((t) => t + 1);
    }
    if (event.type === "ANALYSIS_FAILED") {
      setLiveQueue((q) => q.map((x) => x.case_id === event.case_id ? { ...x, status: "failed", errors: event.errors } : x));
    }
  }, []);

  const { isConnected } = useDisputeSocket(handleSocketEvent);
  const analyzingCount = liveQueue.filter((e) => e.status === "analyzing").length;

  // Client-side filtering
  const filtered = useMemo(() => {
    return cases.filter((c) => {
      if (filterPriority && c.priority !== filterPriority) return false;
      if (filterStatus   && c.status   !== filterStatus)   return false;
      if (fraudOnly      && !c.fraud_suspicion)            return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          c.case_id.toLowerCase().includes(q) ||
          c.merchant.toLowerCase().includes(q) ||
          c.customer_id.toLowerCase().includes(q) ||
          (c.customer_name ?? "").toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [cases, filterPriority, filterStatus, fraudOnly, search]);

  const hasFilter = filterPriority || filterStatus || fraudOnly || search;

  function clearAll() {
    setFilterPriority("");
    setFilterStatus("");
    setFraudOnly(false);
    setSearch("");
  }

  return (
    <>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1 h-5 bg-bfsi-gold rounded-full" />
            <span className="text-xs text-bfsi-gold font-semibold tracking-widest uppercase">Live Intelligence</span>
          </div>
          <h1 className="text-2xl font-bold text-bfsi-text">Internal Review Dashboard</h1>
          <p className="text-bfsi-text-dim text-sm mt-1">Real-time dispute analysis — powered by LangGraph + Groq</p>
        </div>
        <div className="flex items-center gap-3">
          <div className={cn(
            "flex items-center gap-2 text-xs px-3 py-1.5 rounded-full border",
            isConnected ? "text-green-400 bg-green-400/10 border-green-400/30" : "text-slate-400 bg-slate-400/10 border-slate-400/30"
          )}>
            {isConnected ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            {isConnected ? "Live" : "Connecting..."}
          </div>
          <button onClick={() => setRefreshKey((k) => k + 1)} className="btn-ghost flex items-center gap-2">
            <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            Refresh
          </button>
        </div>
      </div>

      {/* Live incoming queue */}
      {liveQueue.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center gap-2 mb-3">
            <Activity className="w-4 h-4 text-bfsi-gold" />
            <p className="section-header">Incoming Cases</p>
            {analyzingCount > 0 && (
              <span className="ml-1 text-xs text-yellow-400 bg-yellow-400/10 border border-yellow-400/30 px-2 py-0.5 rounded-full animate-pulse">
                {analyzingCount} analyzing
              </span>
            )}
          </div>
          <div className="space-y-2">
            {liveQueue.map((entry) => <LiveEntryRow key={entry.case_id} entry={entry} />)}
          </div>
          <div className="gold-divider mt-6" />
        </div>
      )}

      {/* Filter panel */}
      <div className="bfsi-card p-4 mb-5 space-y-3">
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-bfsi-text-dim" />
          <input
            value={search} onChange={(e) => setSearch(e.target.value)}
            className="bfsi-input pl-9 text-sm w-full"
            placeholder="Search by case ID, customer, merchant…"
          />
        </div>

        {/* Priority chips */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] text-bfsi-text-dim uppercase tracking-wider w-14 flex-shrink-0">Priority</span>
          <button onClick={() => setFilterPriority("")}
            className={cn("text-xs px-3 py-1 rounded-full border transition-all",
              filterPriority === "" ? "bg-bfsi-gold/20 border-bfsi-gold text-bfsi-gold font-semibold" : "border-bfsi-border text-bfsi-text-dim hover:border-bfsi-gold/40 hover:text-bfsi-text"
            )}>All</button>
          {PRIORITIES.map((p) => (
            <button key={p} onClick={() => setFilterPriority(filterPriority === p ? "" : p)}
              className={cn("text-xs px-3 py-1 rounded-full border transition-all font-medium",
                filterPriority === p ? PRIORITY_CHIP[p] : "border-bfsi-border text-bfsi-text-dim hover:border-bfsi-gold/40 hover:text-bfsi-text"
              )}>{p}</button>
          ))}
        </div>

        {/* Stage chips */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] text-bfsi-text-dim uppercase tracking-wider w-14 flex-shrink-0">Stage</span>
          <button onClick={() => setFilterStatus("")}
            className={cn("text-xs px-3 py-1 rounded-full border transition-all",
              filterStatus === "" ? "bg-bfsi-gold/20 border-bfsi-gold text-bfsi-gold font-semibold" : "border-bfsi-border text-bfsi-text-dim hover:border-bfsi-gold/40 hover:text-bfsi-text"
            )}>All</button>
          {STATUSES.map((s) => (
            <button key={s} onClick={() => setFilterStatus(filterStatus === s ? "" : s)}
              className={cn("text-xs px-3 py-1 rounded-full border transition-all",
                filterStatus === s ? "bg-bfsi-gold/20 border-bfsi-gold text-bfsi-gold font-semibold" : "border-bfsi-border text-bfsi-text-dim hover:border-bfsi-gold/40 hover:text-bfsi-text"
              )}>{s}</button>
          ))}
        </div>

        {/* Fraud toggle */}
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-bfsi-text-dim uppercase tracking-wider w-14 flex-shrink-0">Fraud</span>
          <button onClick={() => setFraudOnly(!fraudOnly)}
            className={cn("text-xs px-3 py-1 rounded-full border transition-all flex items-center gap-1.5 font-medium",
              fraudOnly ? "bg-red-500/20 border-red-500/60 text-red-400" : "border-bfsi-border text-bfsi-text-dim hover:border-red-500/40 hover:text-red-400"
            )}>
            <AlertTriangle className="w-3 h-3" /> Fraud only
          </button>
        </div>

        {/* Active summary + clear */}
        {hasFilter && (
          <div className="flex items-center gap-2 pt-1 border-t border-bfsi-border">
            <Filter className="w-3.5 h-3.5 text-bfsi-gold flex-shrink-0" />
            <span className="text-xs text-bfsi-text-muted">
              {filtered.length} of {total} case{total !== 1 ? "s" : ""} shown
              {filterPriority && <span className="ml-1 text-bfsi-text font-semibold">· {filterPriority}</span>}
              {filterStatus   && <span className="ml-1 text-bfsi-text font-semibold">· {filterStatus}</span>}
              {fraudOnly      && <span className="ml-1 text-red-400 font-semibold">· Fraud</span>}
            </span>
            <button onClick={clearAll} className="ml-auto text-xs text-bfsi-text-dim hover:text-bfsi-text flex items-center gap-1 transition-colors">
              <X className="w-3 h-3" /> Clear
            </button>
          </div>
        )}
      </div>

      {/* All cases */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-bfsi-text">
          {hasFilter ? "Filtered Cases" : "All Cases"}
          <span className="text-bfsi-text-dim text-sm font-normal ml-2">
            ({hasFilter ? `${filtered.length} of ${total}` : total})
          </span>
        </h2>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="bfsi-card p-5 animate-pulse">
              <div className="h-4 bg-bfsi-muted rounded w-48 mb-3" />
              <div className="h-3 bg-bfsi-muted rounded w-32" />
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="bfsi-card p-12 text-center">
          <Brain className="w-10 h-10 text-bfsi-text-dim mx-auto mb-3" />
          <p className="text-bfsi-text-muted">
            {hasFilter ? "No cases match your filters" : "No cases yet"}
          </p>
          {hasFilter ? (
            <button onClick={clearAll} className="text-xs text-bfsi-gold hover:underline mt-2">Clear filters</button>
          ) : (
            <p className="text-bfsi-text-dim text-sm mt-1">Cases submitted via the dispute form will appear here in real time.</p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((c) => <CaseRow key={c.case_id} c={c} />)}
        </div>
      )}
    </>
  );
}

function LiveEntryRow({ entry }: { entry: LiveEntry }) {
  return (
    <div className={cn(
      "bfsi-card p-4 flex items-center gap-4 transition-all",
      entry.status === "analyzing" && "border-l-2 border-l-yellow-500",
      entry.status === "complete"  && "border-l-2 border-l-green-500",
      entry.status === "failed"    && "border-l-2 border-l-red-500",
    )}>
      <div className="shrink-0">
        {entry.status === "analyzing" && <Loader2 className="w-5 h-5 text-yellow-400 animate-spin" />}
        {entry.status === "complete"  && <div className="w-5 h-5 rounded-full bg-green-500/20 flex items-center justify-center"><div className="w-2 h-2 rounded-full bg-green-400" /></div>}
        {entry.status === "failed"    && <AlertTriangle className="w-5 h-5 text-red-400" />}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-bfsi-text-dim">{entry.case_id}</span>
          {entry.status === "analyzing" && <span className="text-xs text-yellow-400 animate-pulse">AI analysing…</span>}
          {entry.status === "complete"  && <span className="text-xs text-green-400">Analysis complete</span>}
          {entry.status === "failed"    && <span className="text-xs text-red-400">Failed: {entry.errors?.join(", ")}</span>}
        </div>
        {(entry.merchant || entry.customer_name) && (
          <p className="text-xs text-bfsi-text-muted mt-0.5 truncate">
            {entry.customer_name} — {entry.merchant}
            {entry.amount != null && ` — ${formatCurrency(entry.amount, entry.currency)}`}
          </p>
        )}
      </div>
      {entry.status === "complete" && (
        <Link href={`/internal-review/${entry.case_id}`} className="shrink-0 text-xs text-bfsi-gold hover:underline">View →</Link>
      )}
    </div>
  );
}

function CaseRow({ c }: { c: DisputeCase }) {
  return (
    <Link href={`/internal-review/${c.case_id}`} className="block group">
      <div className={cn(
        "bfsi-card p-4 flex items-center gap-4 transition-all duration-200",
        "hover:border-bfsi-gold/30 hover:shadow-bfsi-glow",
        c.fraud_suspicion && "border-l-2 border-l-red-500",
        c.priority === "CRITICAL" && !c.fraud_suspicion && "border-l-2 border-l-orange-500",
      )}>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono text-bfsi-text-dim">{c.case_id}</span>
            {c.fraud_suspicion && (
              <span className="text-xs text-red-400 bg-red-400/10 border border-red-400/20 px-1.5 py-0.5 rounded-full flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" /> Fraud
              </span>
            )}
          </div>
          <p className="text-sm text-bfsi-text font-medium truncate">
            {c.customer_name || c.customer_id} — {c.merchant}
          </p>
        </div>

        <div className="hidden sm:flex items-center gap-2 shrink-0">
          <span className="text-xs font-mono font-bold text-bfsi-text">{formatCurrency(c.amount, c.currency)}</span>
          <span className={cn("text-xs px-2 py-0.5 rounded-full border", getPriorityColor(c.priority as never))}>{c.priority}</span>
          <span className={cn("text-xs px-2 py-0.5 rounded-full border", getStatusColor(c.status as never))}>{c.status}</span>
          <span className="text-xs text-bfsi-text-dim">{formatDate(c.created_at)}</span>
        </div>

        <span className="text-xs text-bfsi-gold opacity-0 group-hover:opacity-100 transition-opacity shrink-0">→</span>
      </div>
    </Link>
  );
}
