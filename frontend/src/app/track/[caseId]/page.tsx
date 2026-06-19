"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface TimelineEvent {
  description: string;
  timestamp: string | null;
}

interface TrackingData {
  case_id: string;
  status: string;
  dispute_reason: string | null;
  merchant: string;
  amount: number;
  currency: string;
  transaction_type: string;
  submission_date: string;
  last_updated: string | null;
  estimated_resolution: string;
  document_requested: boolean;
  required_documents: string[];
  pending_documents: string[];
  documents_received: number;
  timeline: TimelineEvent[];
}

interface CommLog {
  id: number;
  subject: string;
  body: string;
  status: string;
  sent_at: string | null;
  created_at: string;
  notification_type: string;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function formatAmount(amount: number, currency: string): string {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: currency || "INR", minimumFractionDigits: 2 }).format(amount);
}

const STATUS_COLOR: Record<string, string> = {
  "Dispute Received":    "#2563EB",
  "Under Review":        "#D97706",
  "Documents Required":  "#DC2626",
  "Escalated":           "#7C3AED",
  "Resolved":            "#16A34A",
  "Rejected":            "#DC2626",
  "Closed":              "#6B7280",
};

export default function TrackDisputePage() {
  const { caseId } = useParams<{ caseId: string }>();
  const [data, setData]         = useState<TrackingData | null>(null);
  const [comms, setComms]       = useState<CommLog[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);

  useEffect(() => {
    if (!caseId) return;
    Promise.all([
      fetch(`${API_BASE}/api/disputes/track/${caseId}`).then(r => {
        if (!r.ok) throw new Error("Case not found");
        return r.json();
      }),
      fetch(`${API_BASE}/api/communications/${caseId}`).then(r => r.ok ? r.json() : { communications: [] }).catch(() => ({ communications: [] })),
    ])
      .then(([tracking, commData]) => {
        setData(tracking);
        setComms((commData.communications || []).filter((c: CommLog) => c.status === "SENT"));
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [caseId]);

  const statusColor = data ? (STATUS_COLOR[data.status] || "#64748B") : "#64748B";

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", backgroundColor: "#0F172A", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ color: "#64748B", fontSize: "0.9rem" }}>Loading your dispute…</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{ minHeight: "100vh", backgroundColor: "#0F172A", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "0.75rem" }}>
        <div style={{ fontSize: "1rem", color: "#F87171", fontWeight: 600 }}>Case Not Found</div>
        <div style={{ fontSize: "0.8rem", color: "#64748B" }}>Please check your case reference and try again.</div>
        <div style={{ fontSize: "0.75rem", color: "#334155", fontFamily: "monospace" }}>{caseId}</div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#0F172A", color: "#F8FAFC", fontFamily: "system-ui, sans-serif", padding: "2rem 1rem" }}>
      <div style={{ maxWidth: 700, margin: "0 auto" }}>

        {/* Header */}
        <div style={{ marginBottom: "1.5rem" }}>
          <div style={{ fontSize: "0.65rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "#2563EB", marginBottom: "0.5rem" }}>
            SecureBank Dispute Portal
          </div>
          <h1 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#F8FAFC", margin: 0 }}>Dispute Status</h1>
          <div style={{ fontSize: "0.75rem", color: "#64748B", marginTop: 4, fontFamily: "monospace" }}>Case Reference: {data.case_id}</div>
        </div>

        {/* Status card */}
        <div style={{ backgroundColor: "#1E293B", border: `1px solid ${statusColor}40`, borderRadius: 8, padding: "1.25rem 1.5rem", marginBottom: "1rem" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem" }}>
            <div>
              <div style={{ fontSize: "0.65rem", color: "#64748B", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Current Status</div>
              <div style={{ fontSize: "1.15rem", fontWeight: 700, color: statusColor }}>{data.status}</div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: "0.65rem", color: "#64748B", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>Est. Resolution</div>
              <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "#CBD5E1" }}>{data.estimated_resolution}</div>
            </div>
          </div>
        </div>

        {/* Transaction details */}
        <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 8, padding: "1.25rem 1.5rem", marginBottom: "1rem" }}>
          <div style={{ fontSize: "0.65rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748B", marginBottom: "0.875rem" }}>Dispute Details</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            {[
              ["Merchant",         data.merchant || "—"],
              ["Amount",           formatAmount(data.amount, data.currency)],
              ["Transaction Type", data.transaction_type || "—"],
              ["Submitted",        formatDate(data.submission_date)],
              ["Last Updated",     formatDate(data.last_updated)],
              ["Dispute Reason",   data.dispute_reason || "—"],
            ].map(([label, value]) => (
              <div key={label}>
                <div style={{ fontSize: "0.6rem", color: "#64748B", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: "0.8rem", color: "#CBD5E1", fontWeight: 500 }}>{value}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Timeline */}
        {data.timeline.length > 0 && (
          <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 8, padding: "1.25rem 1.5rem", marginBottom: "1rem" }}>
            <div style={{ fontSize: "0.65rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748B", marginBottom: "0.875rem" }}>Case Timeline</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0" }}>
              {data.timeline.map((event, i) => (
                <div key={i} style={{ display: "flex", gap: "0.875rem", position: "relative" }}>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
                    <div style={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: "#2563EB", border: "2px solid #1E40AF", flexShrink: 0, marginTop: 2 }} />
                    {i < data.timeline.length - 1 && <div style={{ width: 1, backgroundColor: "#334155", flex: 1, minHeight: 20, marginTop: 2 }} />}
                  </div>
                  <div style={{ paddingBottom: i < data.timeline.length - 1 ? "0.875rem" : 0 }}>
                    <div style={{ fontSize: "0.78rem", color: "#CBD5E1", fontWeight: 500 }}>{event.description}</div>
                    {event.timestamp && <div style={{ fontSize: "0.65rem", color: "#64748B", marginTop: 2 }}>{formatDate(event.timestamp)}</div>}
                  </div>
                </div>
              ))}
              {/* Current status placeholder */}
              {!["Resolved", "Rejected", "Closed"].includes(data.status) && (
                <div style={{ display: "flex", gap: "0.875rem" }}>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
                    <div style={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: "#D97706", border: "2px solid #92400E", flexShrink: 0, marginTop: 2 }} />
                  </div>
                  <div>
                    <div style={{ fontSize: "0.78rem", color: "#FCD34D", fontWeight: 500 }}>⏳ Resolution Pending</div>
                    <div style={{ fontSize: "0.65rem", color: "#64748B", marginTop: 2 }}>Your case is actively being reviewed</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Documents */}
        {data.document_requested && data.pending_documents.length > 0 && (
          <div style={{ backgroundColor: "#1C1209", border: "1px solid #92400E", borderRadius: 8, padding: "1.25rem 1.5rem", marginBottom: "1rem" }}>
            <div style={{ fontSize: "0.65rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#D97706", marginBottom: "0.875rem" }}>
              ⚠ Documents Required
            </div>
            <div style={{ fontSize: "0.78rem", color: "#CBD5E1", marginBottom: "0.75rem" }}>
              Please submit the following documents to proceed with your dispute:
            </div>
            <ul style={{ margin: 0, paddingLeft: "1.25rem", display: "flex", flexDirection: "column", gap: "0.375rem" }}>
              {data.pending_documents.map((doc, i) => (
                <li key={i} style={{ fontSize: "0.78rem", color: "#FCD34D" }}>{doc}</li>
              ))}
            </ul>
            <div style={{ marginTop: "0.875rem", fontSize: "0.7rem", color: "#64748B" }}>
              Documents received so far: {data.documents_received} of {data.required_documents.length}
            </div>
          </div>
        )}

        {/* Messages from the bank */}
        {comms.length > 0 && (
          <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 8, padding: "1.25rem 1.5rem", marginBottom: "1rem" }}>
            <div style={{ fontSize: "0.65rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748B", marginBottom: "0.875rem" }}>
              Messages from SecureBank
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {comms.map((comm) => (
                <div key={comm.id} style={{ border: "1px solid #334155", borderRadius: 6, overflow: "hidden" }}>
                  <button
                    onClick={() => setExpanded(expanded === comm.id ? null : comm.id)}
                    style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.625rem 0.875rem", backgroundColor: "#0F172A", border: "none", cursor: "pointer", textAlign: "left" }}
                  >
                    <div>
                      <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "#F8FAFC" }}>{comm.subject}</div>
                      <div style={{ fontSize: "0.65rem", color: "#64748B", marginTop: 2 }}>
                        {comm.sent_at ? formatDate(comm.sent_at) : formatDate(comm.created_at)}
                      </div>
                    </div>
                    <span style={{ fontSize: "0.65rem", color: "#475569" }}>{expanded === comm.id ? "▲" : "▼"}</span>
                  </button>
                  {expanded === comm.id && (
                    <div
                      style={{ padding: "1rem 0.875rem", fontSize: "0.8rem", backgroundColor: "#1E293B", borderTop: "1px solid #334155" }}
                      dangerouslySetInnerHTML={{ __html: comm.body }}
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        <div style={{ textAlign: "center", marginTop: "2rem", fontSize: "0.65rem", color: "#334155" }}>
          <div>SecureBank Dispute Resolution Centre</div>
          <div style={{ marginTop: 4 }}>For assistance, contact us at 1800-XXX-XXXX (toll free)</div>
          <div style={{ marginTop: 8, fontFamily: "monospace", color: "#1E293B" }}>ref: {caseId}</div>
        </div>

      </div>
    </div>
  );
}
