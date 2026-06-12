"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import { RefreshCw, Wifi, WifiOff, AlertTriangle, Loader2, Search, X, Filter } from "lucide-react";
import { listCases } from "@/lib/api";
import { cn, formatCurrency, formatDate, getPriorityColor, getStatusColor } from "@/lib/utils";
import type { DisputeCase } from "@/types";
import { useDisputeSocket, type DisputeSocketEvent, type DisputeQueuedEvent } from "@/hooks/useDisputeSocket";

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

const S = {
  page:      { padding: "0" } as React.CSSProperties,
  header:    { marginBottom: "1.5rem" } as React.CSSProperties,
  title:     { fontSize: "1.1rem", fontWeight: 700, color: "#F8FAFC", margin: 0 } as React.CSSProperties,
  subtitle:  { fontSize: "0.72rem", color: "#64748B", marginTop: 2 } as React.CSSProperties,
  metricRow: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "0.75rem", marginBottom: "1.25rem" } as React.CSSProperties,
};

export default function InternalReviewPage() {
  const [cases, setCases]           = useState<DisputeCase[]>([]);
  const [total, setTotal]           = useState(0);
  const [loading, setLoading]       = useState(true);
  const [liveQueue, setLiveQueue]   = useState<LiveEntry[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [search, setSearch]         = useState("");
  const [filterPriority, setFilterPriority] = useState("");
  const [filterStatus, setFilterStatus]     = useState("");
  const [fraudOnly, setFraudOnly]           = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listCases({ limit: 50 })
      .then((r) => { if (!cancelled) { setCases(r.cases); setTotal(r.total); } })
      .catch((err) => { if (!cancelled) console.error(err); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [refreshKey]);

  const handleSocketEvent = useCallback((event: DisputeSocketEvent) => {
    if (event.type === "DISPUTE_QUEUED") {
      const e = event as DisputeQueuedEvent;
      setLiveQueue((q) => {
        if (q.find((x) => x.case_id === e.case_id)) return q;
        return [{ case_id: e.case_id, status: "analyzing", queued_at: e.timestamp, customer_name: e.customer_name, merchant: e.merchant, amount: e.amount, currency: e.currency }, ...q];
      });
    }
    if (event.type === "ANALYSIS_COMPLETE") {
      const caseData = event.case as unknown as DisputeCase;
      setLiveQueue((q) => q.map((x) => x.case_id === event.case_id ? { ...x, status: "complete", caseData } : x));
      setCases((prev) => prev.find((c) => c.case_id === event.case_id) ? prev : [caseData, ...prev]);
      setTotal((t) => t + 1);
    }
    if (event.type === "ANALYSIS_FAILED") {
      setLiveQueue((q) => q.map((x) => x.case_id === event.case_id ? { ...x, status: "failed", errors: event.errors } : x));
    }
  }, []);

  const { isConnected } = useDisputeSocket(handleSocketEvent);

  const filtered = useMemo(() => {
    return cases.filter((c) => {
      if (filterPriority && c.priority !== filterPriority) return false;
      if (filterStatus   && c.status   !== filterStatus)   return false;
      if (fraudOnly      && !c.fraud_suspicion)            return false;
      if (search) {
        const q = search.toLowerCase();
        return c.case_id.toLowerCase().includes(q) || c.merchant.toLowerCase().includes(q) ||
               c.customer_id.toLowerCase().includes(q) || (c.customer_name ?? "").toLowerCase().includes(q);
      }
      return true;
    });
  }, [cases, filterPriority, filterStatus, fraudOnly, search]);

  const hasFilter = !!(filterPriority || filterStatus || fraudOnly || search);
  const clearAll = () => { setFilterPriority(""); setFilterStatus(""); setFraudOnly(false); setSearch(""); };

  // Derived stats
  const openCount    = cases.filter(c => ["Dispute Raised","Under Investigation","Pending Documents","Escalated"].includes(c.status)).length;
  const fraudCount   = cases.filter(c => c.fraud_suspicion).length;
  const critCount    = cases.filter(c => c.priority === "CRITICAL").length;
  const pendingDocs  = cases.filter(c => c.status === "Pending Documents").length;
  const resolvedCount= cases.filter(c => c.status === "Resolved").length;

  // Agent 4 — EIA evidence metrics (derived from loaded cases)
  const evidencePending = cases.filter(c => {
    const wf = c.workflow_plan as { required_agents?: string[]; completed_agents?: string[] } | null;
    if (!wf) return false;
    const required  = wf.required_agents ?? [];
    const completed = wf.completed_agents ?? [];
    return required.includes("EVIDENCE_AGENT") && !completed.includes("EVIDENCE_AGENT") && !c.evidence_assessment;
  }).length;

  const evidenceCompleted = cases.filter(c => {
    const wf = c.workflow_plan as { required_agents?: string[]; completed_agents?: string[] } | null;
    if (!wf) return false;
    return (wf.required_agents ?? []).includes("EVIDENCE_AGENT") && !!c.evidence_assessment;
  }).length;

  const blockedInvestigations = cases.filter(c =>
    (c.evidence_assessment as { investigation_blocked?: boolean } | null)?.investigation_blocked
  ).length;

  const completenessValues = cases
    .map(c => (c.evidence_assessment as { evidence_completeness?: number } | null)?.evidence_completeness)
    .filter((v): v is number => typeof v === "number" && v > 0);
  const avgCompleteness = completenessValues.length
    ? Math.round(completenessValues.reduce((a, b) => a + b, 0) / completenessValues.length)
    : null;

  return (
    <div>
      {/* Page header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "1.5rem" }}>
        <div>
          <div style={{ fontSize: "0.6rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748B", marginBottom: 4 }}>
            Dispute Operations
          </div>
          <h1 style={S.title}>Case Queue</h1>
          <p style={S.subtitle}>Dispute management and investigation workspace</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", fontSize: "0.7rem", padding: "0.3rem 0.75rem", border: "1px solid #334155", borderRadius: 3, color: isConnected ? "#4ADE80" : "#64748B", backgroundColor: "#111827" }}>
            {isConnected ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            {isConnected ? "Live" : "Offline"}
          </div>
          <button
            onClick={() => setRefreshKey((k) => k + 1)}
            className="btn-ghost"
            style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}
          >
            <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
            Refresh
          </button>
        </div>
      </div>

      {/* Metrics strip */}
      <div style={S.metricRow}>
        {[
          { label: "Total Cases",       value: total,        color: "#F8FAFC" },
          { label: "Open",              value: openCount,    color: "#60A5FA" },
          { label: "Fraud Review",      value: fraudCount,   color: "#FCA5A5" },
          { label: "Critical Priority", value: critCount,    color: "#FCA5A5" },
          { label: "Pending Documents", value: pendingDocs,  color: "#FCD34D" },
          { label: "Resolved",          value: resolvedCount, color: "#4ADE80" },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 4, padding: "0.75rem 1rem" }}>
            <div style={{ fontSize: "1.25rem", fontWeight: 700, color, letterSpacing: "-0.02em" }}>{value}</div>
            <div style={{ fontSize: "0.6rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#64748B", marginTop: 3 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Evidence metrics strip — only shown when any evidence data exists */}
      {(evidencePending > 0 || evidenceCompleted > 0 || blockedInvestigations > 0 || avgCompleteness !== null) && (
        <div style={{ marginBottom: "1.25rem" }}>
          <div style={{ fontSize: "0.6rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em", color: "#475569", marginBottom: "0.5rem" }}>
            Evidence Review
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "0.75rem" }}>
            <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 4, padding: "0.75rem 1rem" }}>
              <div style={{ fontSize: "1.25rem", fontWeight: 700, color: evidencePending > 0 ? "#FCD34D" : "#4ADE80", letterSpacing: "-0.02em" }}>{evidencePending}</div>
              <div style={{ fontSize: "0.6rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#64748B", marginTop: 3 }}>Awaiting Evidence Review</div>
            </div>
            <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 4, padding: "0.75rem 1rem" }}>
              <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "#4ADE80", letterSpacing: "-0.02em" }}>{evidenceCompleted}</div>
              <div style={{ fontSize: "0.6rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#64748B", marginTop: 3 }}>Evidence Reviews Done</div>
            </div>
            <div style={{ backgroundColor: "#1E293B", border: blockedInvestigations > 0 ? "1px solid #FECACA" : "1px solid #334155", borderRadius: 4, padding: "0.75rem 1rem" }}>
              <div style={{ fontSize: "1.25rem", fontWeight: 700, color: blockedInvestigations > 0 ? "#FCA5A5" : "#4ADE80", letterSpacing: "-0.02em" }}>{blockedInvestigations}</div>
              <div style={{ fontSize: "0.6rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#64748B", marginTop: 3 }}>Blocked Investigations</div>
            </div>
            <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 4, padding: "0.75rem 1rem" }}>
              <div style={{ fontSize: "1.25rem", fontWeight: 700, color: avgCompleteness !== null ? (avgCompleteness >= 70 ? "#4ADE80" : avgCompleteness >= 40 ? "#FCD34D" : "#FCA5A5") : "#64748B", letterSpacing: "-0.02em", fontFamily: "ui-monospace, monospace" }}>
                {avgCompleteness !== null ? `${avgCompleteness}%` : "—"}
              </div>
              <div style={{ fontSize: "0.6rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#64748B", marginTop: 3 }}>Avg Evidence Completeness</div>
            </div>
          </div>
        </div>
      )}

      {/* Live incoming */}
      {liveQueue.length > 0 && (
        <div style={{ marginBottom: "1.25rem" }}>
          <div style={{ fontSize: "0.65rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em", color: "#64748B", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            Incoming Submissions
            {liveQueue.filter(e => e.status === "analyzing").length > 0 && (
              <span style={{ background: "#FFFBEB", color: "#92400E", border: "1px solid #FDE68A", borderRadius: 3, padding: "0.1rem 0.5rem", fontSize: "0.65rem", fontWeight: 600 }}>
                {liveQueue.filter(e => e.status === "analyzing").length} processing
              </span>
            )}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
            {liveQueue.map((entry) => <LiveEntryRow key={entry.case_id} entry={entry} />)}
          </div>
          <div style={{ height: 1, backgroundColor: "#334155", margin: "1rem 0" }} />
        </div>
      )}

      {/* Filter bar */}
      <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 4, padding: "0.875rem 1rem", marginBottom: "1rem", display: "flex", flexDirection: "column", gap: "0.625rem" }}>
        <div style={{ position: "relative" }}>
          <Search style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", width: 14, height: 14, color: "#64748B" }} />
          <input value={search} onChange={(e) => setSearch(e.target.value)} className="bfsi-input" style={{ paddingLeft: 32 }} placeholder="Search by case ID, customer, merchant…" />
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.375rem" }}>
          <span style={{ fontSize: "0.6rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#64748B", width: 52, flexShrink: 0 }}>Priority</span>
          {["", ...PRIORITIES].map((p) => (
            <button key={p} onClick={() => setFilterPriority(p === filterPriority ? "" : p)}
              style={{ fontSize: "0.7rem", padding: "0.2rem 0.625rem", borderRadius: 3, border: "1px solid", cursor: "pointer", fontWeight: filterPriority === p ? 600 : 400, backgroundColor: filterPriority === p ? "#2563EB" : "transparent", borderColor: filterPriority === p ? "#2563EB" : "#334155", color: filterPriority === p ? "#FFFFFF" : "#94A3B8", transition: "all 0.15s" }}>
              {p || "All"}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.375rem" }}>
          <span style={{ fontSize: "0.6rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#64748B", width: 52, flexShrink: 0 }}>Status</span>
          {["", ...STATUSES].map((s) => (
            <button key={s} onClick={() => setFilterStatus(s === filterStatus ? "" : s)}
              style={{ fontSize: "0.7rem", padding: "0.2rem 0.625rem", borderRadius: 3, border: "1px solid", cursor: "pointer", fontWeight: filterStatus === s ? 600 : 400, backgroundColor: filterStatus === s ? "#2563EB" : "transparent", borderColor: filterStatus === s ? "#2563EB" : "#334155", color: filterStatus === s ? "#FFFFFF" : "#94A3B8", transition: "all 0.15s" }}>
              {s || "All"}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
          <span style={{ fontSize: "0.6rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#64748B", width: 52, flexShrink: 0 }}>Flags</span>
          <button onClick={() => setFraudOnly(!fraudOnly)}
            style={{ fontSize: "0.7rem", padding: "0.2rem 0.625rem", borderRadius: 3, border: "1px solid", cursor: "pointer", fontWeight: fraudOnly ? 600 : 400, backgroundColor: fraudOnly ? "#FEF2F2" : "transparent", borderColor: fraudOnly ? "#FECACA" : "#334155", color: fraudOnly ? "#991B1B" : "#94A3B8", display: "flex", alignItems: "center", gap: "0.25rem", transition: "all 0.15s" }}>
            <AlertTriangle style={{ width: 11, height: 11 }} /> Fraud Only
          </button>
        </div>

        {hasFilter && (
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", paddingTop: "0.25rem", borderTop: "1px solid #334155" }}>
            <Filter style={{ width: 12, height: 12, color: "#64748B" }} />
            <span style={{ fontSize: "0.7rem", color: "#94A3B8" }}>{filtered.length} of {total} cases</span>
            <button onClick={clearAll} style={{ marginLeft: "auto", fontSize: "0.7rem", color: "#64748B", background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: "0.25rem" }}>
              <X style={{ width: 11, height: 11 }} /> Clear filters
            </button>
          </div>
        )}
      </div>

      {/* Case table */}
      <div style={{ fontSize: "0.7rem", color: "#64748B", marginBottom: "0.5rem", fontWeight: 600 }}>
        {hasFilter ? `${filtered.length} of ${total} cases` : `${total} cases`}
      </div>

      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
          {[...Array(6)].map((_, i) => (
            <div key={i} style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 4, padding: "0.875rem 1rem", height: 60, opacity: 0.5 }} />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 4, padding: "3rem", textAlign: "center" }}>
          <p style={{ fontSize: "0.8rem", color: "#64748B" }}>
            {hasFilter ? "No cases match the selected filters." : "No cases submitted yet."}
          </p>
          {hasFilter && <button onClick={clearAll} style={{ marginTop: 8, fontSize: "0.7rem", color: "#2563EB", background: "none", border: "none", cursor: "pointer" }}>Clear filters</button>}
        </div>
      ) : (
        <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 4, overflow: "hidden" }}>
          {/* Table header */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 0.8fr 0.8fr 0.9fr 0.5fr", padding: "0.5rem 1rem", borderBottom: "1px solid #334155", backgroundColor: "#111827" }}>
            {["Case ID", "Customer", "Merchant", "Amount", "Priority", "Status", "Filed"].map(h => (
              <div key={h} style={{ fontSize: "0.6rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em", color: "#64748B" }}>{h}</div>
            ))}
          </div>
          {filtered.map((c) => <CaseRow key={c.case_id} c={c} />)}
        </div>
      )}
    </div>
  );
}

function LiveEntryRow({ entry }: { entry: LiveEntry }) {
  const statusStyle: Record<string, React.CSSProperties> = {
    analyzing: { borderLeft: "3px solid #B45309", backgroundColor: "#1E293B" },
    complete:  { borderLeft: "3px solid #15803D", backgroundColor: "#1E293B" },
    failed:    { borderLeft: "3px solid #B91C1C", backgroundColor: "#1E293B" },
  };
  return (
    <div style={{ ...statusStyle[entry.status], border: "1px solid #334155", borderRadius: 4, padding: "0.625rem 1rem", display: "flex", alignItems: "center", gap: "0.75rem" }}>
      {entry.status === "analyzing" && <Loader2 style={{ width: 14, height: 14, color: "#FCD34D", flexShrink: 0 }} className="animate-spin" />}
      {entry.status === "complete"  && <div style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: "#15803D", flexShrink: 0 }} />}
      {entry.status === "failed"    && <div style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: "#B91C1C", flexShrink: 0 }} />}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span style={{ fontFamily: "ui-monospace, monospace", fontSize: "0.72rem", color: "#94A3B8" }}>{entry.case_id}</span>
          <span style={{ fontSize: "0.7rem", color: entry.status === "analyzing" ? "#FCD34D" : entry.status === "complete" ? "#4ADE80" : "#FCA5A5" }}>
            {entry.status === "analyzing" ? "Processing…" : entry.status === "complete" ? "Ready for review" : "Submission failed"}
          </span>
        </div>
        {(entry.merchant || entry.customer_name) && (
          <p style={{ fontSize: "0.7rem", color: "#64748B", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {entry.customer_name}{entry.merchant ? ` — ${entry.merchant}` : ""}
            {entry.amount != null ? ` — ${formatCurrency(entry.amount, entry.currency)}` : ""}
          </p>
        )}
      </div>
      {entry.status === "complete" && (
        <Link href={`/internal-review/${entry.case_id}`} style={{ fontSize: "0.7rem", color: "#2563EB", textDecoration: "none", flexShrink: 0 }}>
          Open →
        </Link>
      )}
    </div>
  );
}

function CaseRow({ c }: { c: DisputeCase }) {
  return (
    <Link href={`/internal-review/${c.case_id}`} style={{ display: "block", textDecoration: "none" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 0.8fr 0.8fr 0.9fr 0.5fr", padding: "0.625rem 1rem", borderBottom: "1px solid #1E293B", alignItems: "center", cursor: "pointer", transition: "background-color 0.1s" }} className="hover:bg-slate-800">
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {c.fraud_suspicion && <div style={{ width: 5, height: 5, borderRadius: "50%", backgroundColor: "#B91C1C", flexShrink: 0 }} title="Fraud indicator" />}
          <span style={{ fontFamily: "ui-monospace, monospace", fontSize: "0.72rem", color: "#94A3B8" }}>{c.case_id}</span>
        </div>
        <div style={{ fontSize: "0.75rem", color: "#F8FAFC", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", paddingRight: "0.5rem" }}>
          {c.customer_name || c.customer_id}
        </div>
        <div style={{ fontSize: "0.75rem", color: "#94A3B8", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", paddingRight: "0.5rem" }}>
          {c.merchant}
        </div>
        <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "#F8FAFC", fontFamily: "ui-monospace, monospace" }}>
          {formatCurrency(c.amount, c.currency)}
        </div>
        <div>
          <span className={getPriorityColor(c.priority as never)}>{c.priority}</span>
        </div>
        <div>
          <span className={getStatusColor(c.status as never)}>{c.status}</span>
        </div>
        <div style={{ fontSize: "0.65rem", color: "#64748B" }}>{formatDate(c.created_at)}</div>
      </div>
    </Link>
  );
}
