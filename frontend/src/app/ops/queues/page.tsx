"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Layers, AlertTriangle, Clock, Loader2, RefreshCw, ChevronRight } from "lucide-react";
import { cn, formatCurrency, formatDate, getPriorityColor, getStatusColor } from "@/lib/utils";
import { listQueues, getQueueCases } from "@/lib/api";
import type { QueueSummary, DisputeCase } from "@/types";

const QUEUE_ICONS: Record<string, string> = {
  FRAUD_OPS: "🛡️",
  ATM_INVESTIGATION: "🏧",
  CHARGEBACK_TEAM: "💳",
  COMPLIANCE_REVIEW: "📋",
  HIGH_PRIORITY: "🔴",
  GENERAL: "📂",
};

export default function QueuesPage() {
  const [queues, setQueues]         = useState<QueueSummary[]>([]);
  const [selectedQueue, setSelected] = useState<string | null>(null);
  const [cases, setCases]           = useState<DisputeCase[]>([]);
  const [qTotal, setQTotal]         = useState(0);
  const [loading, setLoading]       = useState(true);
  const [casesLoading, setCasesLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    listQueues()
      .then((q) => {
        setQueues(q);
        if (q.length > 0 && !selectedQueue) setSelected(q[0].queue);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [refreshKey]);

  useEffect(() => {
    if (!selectedQueue) return;
    setCasesLoading(true);
    getQueueCases(selectedQueue)
      .then((r) => { setCases(r.cases); setQTotal(r.total); })
      .catch(console.error)
      .finally(() => setCasesLoading(false));
  }, [selectedQueue, refreshKey]);

  if (loading) return (
    <div className="flex items-center justify-center py-24">
      <Loader2 className="w-5 h-5 animate-spin text-bfsi-gold" />
    </div>
  );

  const activeQueue = queues.find((q) => q.queue === selectedQueue);

  return (
    <>
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-1 h-5 bg-bfsi-gold rounded-full" />
            <span className="text-xs text-bfsi-gold font-semibold tracking-widest uppercase">Queue Management</span>
          </div>
          <h1 className="text-xl font-bold text-bfsi-text">Operations Queues</h1>
        </div>
        <button onClick={() => setRefreshKey((k) => k + 1)} className="btn-ghost flex items-center gap-2 text-sm">
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Queue list */}
        <div className="space-y-2">
          {queues.map((q) => (
            <button key={q.queue} onClick={() => setSelected(q.queue)}
              className={cn("w-full text-left p-4 rounded-lg border transition-all",
                selectedQueue === q.queue
                  ? "border-bfsi-gold bg-bfsi-gold/10"
                  : "border-bfsi-border bg-bfsi-card hover:border-bfsi-gold/40"
              )}>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-base">{QUEUE_ICONS[q.queue] || "📁"}</span>
                <span className="text-sm font-semibold text-bfsi-text">{q.display}</span>
              </div>
              <div className="flex items-center gap-3 text-xs">
                <span className="text-bfsi-text-muted">{q.count} cases</span>
                {q.critical > 0 && (
                  <span className="flex items-center gap-1 text-red-400">
                    <AlertTriangle className="w-3 h-3" /> {q.critical} critical
                  </span>
                )}
                {q.sla_breached > 0 && (
                  <span className="flex items-center gap-1 text-amber-400">
                    <Clock className="w-3 h-3" /> {q.sla_breached} SLA
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>

        {/* Cases list */}
        <div className="lg:col-span-3">
          {activeQueue && (
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-bfsi-text">
                {QUEUE_ICONS[activeQueue.queue]} {activeQueue.display}
                <span className="text-bfsi-text-dim text-sm font-normal ml-2">({qTotal} cases)</span>
              </h2>
            </div>
          )}
          {casesLoading ? (
            <div className="space-y-2">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="bfsi-card p-4 animate-pulse">
                  <div className="h-4 bg-bfsi-muted rounded w-40 mb-2" />
                  <div className="h-3 bg-bfsi-muted rounded w-24" />
                </div>
              ))}
            </div>
          ) : cases.length === 0 ? (
            <div className="bfsi-card p-12 text-center">
              <Layers className="w-10 h-10 text-bfsi-text-dim mx-auto mb-3" />
              <p className="text-bfsi-text-muted text-sm">No cases in this queue</p>
            </div>
          ) : (
            <div className="space-y-2">
              {cases.map((c) => (
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
                        <span className="text-[10px] text-red-400 bg-red-400/10 px-1.5 py-0.5 rounded border border-red-400/30">SLA Breached</span>
                      )}
                      {c.requires_manual_review && (
                        <span className="text-[10px] text-amber-400 bg-amber-400/10 px-1.5 py-0.5 rounded border border-amber-400/30">Manual Review</span>
                      )}
                    </div>
                    <div className="flex items-center gap-4 text-xs text-bfsi-text-muted">
                      <span>{c.customer_name || c.customer_id}</span>
                      <span className="font-mono font-semibold">{formatCurrency(c.amount, c.currency)}</span>
                      <span>{c.merchant}</span>
                      <span className="text-bfsi-text-dim">{formatDate(c.created_at)}</span>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-bfsi-text-dim group-hover:text-bfsi-gold transition-colors flex-shrink-0" />
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
