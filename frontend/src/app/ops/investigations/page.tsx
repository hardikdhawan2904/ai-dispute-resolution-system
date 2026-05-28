"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Search, Clock, ChevronRight, RefreshCw, CheckCircle, AlertTriangle, Loader2 } from "lucide-react";
import { listCases, updateCaseStatus } from "@/lib/api";
import type { DisputeCase } from "@/types";
import { cn, getPriorityColor, formatCurrency, formatDate, formatConfidence, getConfidenceColor } from "@/lib/utils";
import toast from "react-hot-toast";

const INV_STATUSES = ["Dispute Raised","Under Investigation","Pending Documents","Escalated"];

export default function OpsInvestigationsPage() {
  const [cases, setCases]     = useState<DisputeCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState("Under Investigation");
  const [refreshKey, setRefreshKey]     = useState(0);

  useEffect(() => {
    setLoading(true);
    listCases({ limit: 200, status: filterStatus || undefined })
      .then((r) => setCases(r.cases))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [refreshKey, filterStatus]);

  async function moveToInvestigation(c: DisputeCase) {
    setUpdating(c.case_id);
    try {
      await updateCaseStatus(c.case_id, "Under Investigation", "investigator");
      toast.success("Case moved to Under Investigation");
      setRefreshKey((k) => k + 1);
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setUpdating(null);
    }
  }

  const byPriority = (a: DisputeCase, b: DisputeCase) => {
    const o = { CRITICAL:0,HIGH:1,MEDIUM:2,LOW:3 };
    return (o[a.priority as keyof typeof o] ?? 4) - (o[b.priority as keyof typeof o] ?? 4);
  };

  return (
    <>
      <div className="flex items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1 h-5 bg-blue-500 rounded-full" />
            <span className="text-xs text-blue-400 font-semibold tracking-widest uppercase">Investigation Queue</span>
          </div>
          <h1 className="text-2xl font-bold text-bfsi-text">Active Investigations</h1>
          <p className="text-bfsi-text-dim text-sm mt-1">Cases requiring investigator attention and active dispute resolution</p>
        </div>
        <button onClick={() => setRefreshKey((k) => k + 1)} className="btn-ghost flex items-center gap-2">
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} /> Refresh
        </button>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {INV_STATUSES.slice(0, 3).map((s) => {
          const count = cases.filter((c) => c.status === s).length;
          return (
            <button key={s} onClick={() => setFilterStatus(s === filterStatus ? "" : s)}
              className={cn("bfsi-card p-4 text-left transition-all", s === filterStatus && "ring-1 ring-bfsi-gold")}>
              <p className="text-xs text-bfsi-text-dim mb-1">{s}</p>
              <p className="text-2xl font-bold font-mono text-bfsi-text">{count}</p>
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-3 mb-5">
        <div className="flex gap-2">
          {["", ...INV_STATUSES].map((s) => (
            <button key={s} onClick={() => setFilterStatus(s)}
              className={cn("px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
                filterStatus === s ? "bg-bfsi-gold text-bfsi-black" : "bg-bfsi-muted text-bfsi-text-muted hover:text-bfsi-text")}>
              {s || "All Active"}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="space-y-2">{[...Array(4)].map((_, i) => <div key={i} className="bfsi-card p-4 animate-pulse h-24" />)}</div>
      ) : cases.length === 0 ? (
        <div className="bfsi-card p-12 text-center">
          <CheckCircle className="w-10 h-10 text-green-400 mx-auto mb-3" />
          <p className="text-bfsi-text-muted font-medium">No cases in this queue</p>
          <p className="text-bfsi-text-dim text-sm">All investigations are up to date.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {[...cases].sort(byPriority).map((c) => (
            <div key={c.case_id} className="bfsi-card p-5">
              <div className="flex items-start gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span className="text-xs font-mono text-bfsi-text-dim">{c.case_id.slice(-12)}</span>
                    <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full border", getPriorityColor(c.priority as any))}>
                      {c.priority}
                    </span>
                    {c.fraud_suspicion && (
                      <span className="flex items-center gap-1 text-[10px] text-red-400 bg-red-400/10 border border-red-400/30 px-1.5 py-0.5 rounded-full">
                        <AlertTriangle className="w-2.5 h-2.5" /> Fraud
                      </span>
                    )}
                  </div>
                  <p className="font-semibold text-bfsi-text">{c.merchant}</p>
                  <p className="text-xs text-bfsi-text-dim">{c.customer_name} · {c.dispute_category || "Unclassified"}</p>
                  <div className="flex items-center gap-4 mt-2">
                    <span className="font-mono text-sm font-bold text-bfsi-text">{formatCurrency(c.amount, c.currency)}</span>
                    <span className={cn("text-xs font-semibold", getConfidenceColor(c.confidence_score))}>
                      {formatConfidence(c.confidence_score)} AI confidence
                    </span>
                    <span className="text-xs text-bfsi-text-dim flex items-center gap-1">
                      <Clock className="w-3 h-3" /> {formatDate(c.created_at)}
                    </span>
                  </div>
                </div>
                <div className="flex flex-col gap-2 shrink-0">
                  {c.status !== "Under Investigation" && (
                    <button onClick={() => moveToInvestigation(c)} disabled={updating === c.case_id}
                      className="text-xs px-3 py-1.5 bg-blue-500/10 border border-blue-500/30 text-blue-400 rounded-lg hover:bg-blue-500/20 transition-all flex items-center gap-1.5">
                      {updating === c.case_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
                      Start Investigation
                    </button>
                  )}
                  <Link href={`/ops/case/${c.case_id}`}
                    className="text-xs px-3 py-1.5 bg-bfsi-muted border border-bfsi-border text-bfsi-text-muted rounded-lg hover:text-bfsi-text transition-all flex items-center gap-1.5">
                    <ChevronRight className="w-3 h-3" /> View Case
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
