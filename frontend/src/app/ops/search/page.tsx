"use client";

import { useState } from "react";
import Link from "next/link";
import { Search, Filter, ChevronRight, Loader2, AlertTriangle } from "lucide-react";
import { cn, formatCurrency, formatDate, getPriorityColor, getStatusColor } from "@/lib/utils";
import { searchCases } from "@/lib/api";
import type { DisputeCase } from "@/types";

const STATUSES = ["Dispute Raised","Under Investigation","Pending Documents","Escalated","Resolved","Rejected","Closed"];
const PRIORITIES = ["CRITICAL","HIGH","MEDIUM","LOW"];
const QUEUES = [
  { value: "FRAUD_OPS",         label: "Fraud Operations" },
  { value: "ATM_INVESTIGATION", label: "ATM Investigation" },
  { value: "CHARGEBACK_TEAM",   label: "Chargeback Team" },
  { value: "COMPLIANCE_REVIEW", label: "Compliance Review" },
  { value: "HIGH_PRIORITY",     label: "High Priority" },
  { value: "GENERAL",           label: "General" },
];

export default function SearchPage() {
  const [query,    setQuery]    = useState("");
  const [status,   setStatus]   = useState("");
  const [priority, setPriority] = useState("");
  const [queue,    setQueue]    = useState("");
  const [fraudOnly, setFraudOnly]         = useState(false);
  const [manualOnly, setManualOnly]       = useState(false);
  const [slaBreached, setSlaBreached]     = useState(false);
  const [minAmt, setMinAmt]               = useState("");
  const [maxAmt, setMaxAmt]               = useState("");

  const [results, setResults]   = useState<DisputeCase[] | null>(null);
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(false);

  async function handleSearch() {
    setLoading(true);
    try {
      const r = await searchCases({
        query: query || undefined,
        status: status || undefined,
        priority: priority || undefined,
        queue: queue || undefined,
        fraud_only: fraudOnly,
        manual_review_only: manualOnly,
        sla_breached_only: slaBreached,
        min_amount: minAmt ? parseFloat(minAmt) : undefined,
        max_amount: maxAmt ? parseFloat(maxAmt) : undefined,
        limit: 100,
      });
      setResults(r.cases);
      setTotal(r.total);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-1 h-5 bg-bfsi-gold rounded-full" />
          <span className="text-xs text-bfsi-gold font-semibold tracking-widest uppercase">Advanced Search</span>
        </div>
        <h1 className="text-xl font-bold text-bfsi-text">Case Search</h1>
      </div>

      <div className="bfsi-card p-6 mb-6">
        {/* Text search */}
        <div className="flex gap-3 mb-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-bfsi-text-dim" />
            <input
              className="bfsi-select pl-9 w-full text-sm"
              placeholder="Search by case ID, customer, transaction, merchant…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
          </div>
          <button onClick={handleSearch} disabled={loading}
            className="btn-gold flex items-center gap-2 disabled:opacity-50">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            Search
          </button>
        </div>

        {/* Filters */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          <select className="bfsi-select text-sm" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All Statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="bfsi-select text-sm" value={priority} onChange={(e) => setPriority(e.target.value)}>
            <option value="">All Priorities</option>
            {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <select className="bfsi-select text-sm" value={queue} onChange={(e) => setQueue(e.target.value)}>
            <option value="">All Queues</option>
            {QUEUES.map((q) => <option key={q.value} value={q.value}>{q.label}</option>)}
          </select>
          <div className="flex gap-2">
            <input className="bfsi-select text-sm flex-1" type="number" placeholder="Min ₹" value={minAmt} onChange={(e) => setMinAmt(e.target.value)} />
            <input className="bfsi-select text-sm flex-1" type="number" placeholder="Max ₹" value={maxAmt} onChange={(e) => setMaxAmt(e.target.value)} />
          </div>
        </div>

        {/* Boolean filters */}
        <div className="flex flex-wrap gap-4">
          {[
            { label: "Fraud only",          val: fraudOnly,   set: setFraudOnly },
            { label: "Manual review only",  val: manualOnly,  set: setManualOnly },
            { label: "SLA breached only",   val: slaBreached, set: setSlaBreached },
          ].map(({ label, val, set }) => (
            <label key={label} className="flex items-center gap-2 text-xs text-bfsi-text-muted cursor-pointer">
              <input type="checkbox" checked={val} onChange={(e) => set(e.target.checked)} className="rounded" />
              {label}
            </label>
          ))}
        </div>
      </div>

      {/* Results */}
      {results !== null && (
        <>
          <p className="text-sm text-bfsi-text-muted mb-4">
            {total} case{total !== 1 ? "s" : ""} found
          </p>
          {results.length === 0 ? (
            <div className="bfsi-card p-12 text-center">
              <Search className="w-10 h-10 text-bfsi-text-dim mx-auto mb-3" />
              <p className="text-bfsi-text-muted text-sm">No cases match your filters</p>
            </div>
          ) : (
            <div className="space-y-2">
              {results.map((c) => (
                <Link key={c.case_id} href={`/ops/case/${c.case_id}`}
                  className="bfsi-card p-4 flex items-center gap-4 hover:border-bfsi-gold/40 transition-all group">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <span className="text-xs font-mono text-bfsi-text-dim">{c.case_id}</span>
                      <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full border", getPriorityColor(c.priority as never))}>
                        {c.priority}
                      </span>
                      <span className={cn("text-xs px-2 py-0.5 rounded-full border", getStatusColor(c.status as never))}>
                        {c.status}
                      </span>
                      {c.sla_breached && (
                        <span className="text-[10px] text-red-400 bg-red-400/10 px-1.5 py-0.5 rounded border border-red-400/30 flex items-center gap-1">
                          <AlertTriangle className="w-3 h-3" /> SLA Breached
                        </span>
                      )}
                      {c.requires_manual_review && (
                        <span className="text-[10px] text-amber-400 bg-amber-400/10 px-1.5 py-0.5 rounded border border-amber-400/30">Manual Review</span>
                      )}
                    </div>
                    <div className="flex items-center gap-4 text-xs text-bfsi-text-muted">
                      <span>{c.customer_name || c.customer_id}</span>
                      <span className="font-mono font-semibold">{formatCurrency(c.amount, c.currency)}</span>
                      <span>{c.merchant}</span>
                      <span>{c.dispute_category || "—"}</span>
                      <span className="text-bfsi-text-dim ml-auto">{formatDate(c.created_at)}</span>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-bfsi-text-dim group-hover:text-bfsi-gold transition-colors flex-shrink-0" />
                </Link>
              ))}
            </div>
          )}
        </>
      )}
    </>
  );
}
