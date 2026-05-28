"use client";

import { useEffect, useState } from "react";
import { BookOpen, RefreshCw, Search } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";

interface AuditEntry { id: number; case_id: string; event_type: string; stage?: string; actor: string; message?: string; created_at: string; }

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function OpsAuditPage() {
  const [logs, setLogs]         = useState<AuditEntry[]>([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    setLoading(true);
    const token = typeof window !== "undefined" ? localStorage.getItem("bfsi_token") : null;
    fetch(`${BASE_URL}/api/disputes/audit-logs?limit=200`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => r.json())
      .then((d) => setLogs(d.audit_logs ?? []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [refreshKey]);

  const EVENT_COLORS: Record<string, string> = {
    CASE_CREATED: "text-blue-400",
    STATUS_UPDATED: "text-yellow-400",
    WORKFLOW_COMPLETED: "text-green-400",
    CASE_ESCALATED: "text-red-400",
  };

  const filtered = logs.filter((l) =>
    !search ||
    l.case_id.toLowerCase().includes(search.toLowerCase()) ||
    l.event_type.toLowerCase().includes(search.toLowerCase()) ||
    l.actor.toLowerCase().includes(search.toLowerCase()) ||
    (l.message ?? "").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      <div className="flex items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1 h-5 bg-indigo-500 rounded-full" />
            <span className="text-xs text-indigo-400 font-semibold tracking-widest uppercase">Immutable Audit</span>
          </div>
          <h1 className="text-2xl font-bold text-bfsi-text">Audit Trail</h1>
          <p className="text-bfsi-text-dim text-sm mt-1">Complete immutable audit log across all dispute cases</p>
        </div>
        <button onClick={() => setRefreshKey((k) => k + 1)} className="btn-ghost flex items-center gap-2">
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} /> Refresh
        </button>
      </div>

      <div className="flex items-center gap-3 mb-5">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-bfsi-text-dim" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            className="bfsi-input pl-9 text-sm" placeholder="Filter by case ID, event type, actor..." />
        </div>
        <span className="text-bfsi-text-dim text-xs shrink-0">{filtered.length} entries</span>
      </div>

      {loading ? (
        <div className="space-y-2">{[...Array(6)].map((_, i) => <div key={i} className="bfsi-card p-4 animate-pulse h-14" />)}</div>
      ) : filtered.length === 0 ? (
        <div className="bfsi-card p-12 text-center">
          <BookOpen className="w-10 h-10 text-bfsi-text-dim mx-auto mb-3" />
          <p className="text-bfsi-text-muted">No audit entries found</p>
        </div>
      ) : (
        <div className="bfsi-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-bfsi-border">
                  {["#","Case ID","Event","Stage","Actor","Message","Timestamp"].map((h) => (
                    <th key={h} className="text-left text-[10px] text-bfsi-text-dim font-medium px-4 py-3 uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-bfsi-border">
                {filtered.map((log) => (
                  <tr key={log.id} className="hover:bg-bfsi-muted/30 transition-colors">
                    <td className="px-4 py-3 text-bfsi-text-dim font-mono">{log.id}</td>
                    <td className="px-4 py-3 font-mono text-bfsi-gold">{log.case_id.slice(-10)}</td>
                    <td className="px-4 py-3">
                      <span className={cn("font-mono font-semibold", EVENT_COLORS[log.event_type] ?? "text-bfsi-text-muted")}>
                        {log.event_type}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {log.stage && (
                        <span className="text-[10px] bg-bfsi-muted text-bfsi-text-dim px-1.5 py-0.5 rounded font-mono">
                          {log.stage}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-bfsi-text-muted">{log.actor}</td>
                    <td className="px-4 py-3 text-bfsi-text-dim max-w-xs truncate">{log.message ?? "—"}</td>
                    <td className="px-4 py-3 text-bfsi-text-dim font-mono whitespace-nowrap">{formatDate(log.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
