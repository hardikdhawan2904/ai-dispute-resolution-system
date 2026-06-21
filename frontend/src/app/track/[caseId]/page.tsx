"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

interface TimelineEvent {
  description: string;
  timestamp: string | null;
}

interface DocumentRequestItem {
  id: number;
  document_type: string;
  description: string;
  fulfilled: boolean;
  due_date: string | null;
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
  document_requests: DocumentRequestItem[];
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

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function formatDateShort(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
  });
}

function formatAmount(amount: number, currency: string): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency", currency: currency || "INR", minimumFractionDigits: 2,
  }).format(amount);
}

// Map internal status → progress stage (1–4)
function getStage(status: string): number {
  if (["Resolved", "Rejected", "Closed"].includes(status)) return 4;
  if (["Under Investigation", "Escalated"].includes(status)) return 2;
  if (["Pending Documents"].includes(status)) return 3;
  return 1; // Dispute Raised / default
}

const STAGES = [
  { label: "Received",      icon: "📥" },
  { label: "Investigation", icon: "🔍" },
  { label: "Review",        icon: "📋" },
  { label: "Resolution",    icon: "✅" },
];

// ── Component ─────────────────────────────────────────────────────────────────

export default function TrackDisputePage() {
  const { caseId } = useParams<{ caseId: string }>();

  const [data, setData]               = useState<TrackingData | null>(null);
  const [comms, setComms]             = useState<CommLog[]>([]);
  const [expandedComm, setExpandedComm] = useState<number | null>(null);
  const [loading, setLoading]         = useState(true);
  const [error, setError]             = useState<string | null>(null);
  const [uploading, setUploading]     = useState(false);
  const [uploadDone, setUploadDone]   = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const fetchData = () => {
    if (!caseId) return;
    Promise.all([
      fetch(`${API_BASE}/api/disputes/track/${caseId}`).then(r => {
        if (!r.ok) throw new Error("Case not found");
        return r.json();
      }),
      fetch(`${API_BASE}/api/communications/${caseId}`)
        .then(r => r.ok ? r.json() : { communications: [] })
        .catch(() => ({ communications: [] })),
    ])
      .then(([tracking, commData]) => {
        setData(tracking);
        setComms((commData.communications || []).filter((c: CommLog) => c.status === "SENT"));
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchData(); }, [caseId]);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploading(true); setUploadError(null); setUploadDone(false);
    try {
      const formData = new FormData();
      Array.from(files).forEach(f => formData.append("files", f));
      const res = await fetch(`${API_BASE}/api/disputes/${caseId}/upload-documents`, {
        method: "POST", body: formData,
      });
      if (!res.ok) throw new Error("Upload failed");
      setUploadDone(true);
      setTimeout(() => { fetchData(); setUploadDone(false); }, 1500);
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  // ── Loading / Error ────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", backgroundColor: "#0F172A", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ color: "#64748B", fontSize: "0.85rem" }}>Loading your dispute…</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{ minHeight: "100vh", backgroundColor: "#0F172A", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "0.75rem" }}>
        <div style={{ fontSize: "1rem", color: "#F87171", fontWeight: 600 }}>Case Not Found</div>
        <div style={{ fontSize: "0.8rem", color: "#64748B" }}>Please check your case reference and try again.</div>
        <a href="/track" style={{ marginTop: "0.5rem", fontSize: "0.78rem", color: "#2563EB" }}>← Back to search</a>
      </div>
    );
  }

  const stage         = getStage(data.status);
  const isTerminal    = ["Resolved", "Rejected", "Closed"].includes(data.status);
  const hasPendingDocs = data.document_requests && data.document_requests.filter(d => !d.fulfilled).length > 0;
  const nextDueDate   = data.document_requests?.find(d => !d.fulfilled && d.due_date)?.due_date ?? null;

  // Deduplicate timeline
  const seen = new Set<string>();
  const dedupedTimeline = (data.timeline || []).filter(e => {
    const key = e.description.trim().toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key); return true;
  });

  // Merge comms into timeline for communication history
  const commTimeline = comms.map(c => ({
    subject: c.subject,
    timestamp: c.sent_at || c.created_at,
    type: c.notification_type,
  }));

  // Est. resolution — don't show past dates
  const resolvedEst = (() => {
    const est = data.estimated_resolution;
    const d = new Date(est);
    if (!isNaN(d.getTime()) && d < new Date() && !isTerminal) return "Under active review";
    return est;
  })();

  return (
    <div style={{ minHeight: "100vh", backgroundColor: "#0F172A", color: "#F8FAFC", fontFamily: "system-ui, sans-serif" }}>
      <div style={{ maxWidth: 680, margin: "0 auto", padding: "2rem 1rem 4rem" }}>

        {/* Header */}
        <div style={{ marginBottom: "1.75rem" }}>
          <div style={{ fontSize: "0.62rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.12em", color: "#2563EB", marginBottom: "0.5rem" }}>
            SecureBank Dispute Portal
          </div>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "0.5rem" }}>
            <div>
              <h1 style={{ margin: 0, fontSize: "1.35rem", fontWeight: 700, color: "#F8FAFC" }}>Dispute Status</h1>
              <div style={{ fontSize: "0.72rem", color: "#64748B", marginTop: 3, fontFamily: "monospace" }}>
                Case Reference: {data.case_id}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: "0.62rem", color: "#64748B", textTransform: "uppercase", letterSpacing: "0.07em" }}>Est. Resolution</div>
              <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "#CBD5E1", marginTop: 2 }}>{resolvedEst}</div>
            </div>
          </div>
        </div>

        {/* ── 1. PROGRESS BAR ──────────────────────────────────────────────── */}
        <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 10, padding: "1.25rem 1.5rem", marginBottom: "1rem" }}>
          <div style={{ fontSize: "0.62rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748B", marginBottom: "1rem" }}>
            Case Progress
          </div>
          <div style={{ display: "flex", alignItems: "center" }}>
            {STAGES.map((s, i) => {
              const stageNum  = i + 1;
              const isDone    = stageNum < stage || (stageNum === stage && isTerminal);
              const isCurrent = stageNum === stage && !isTerminal;
              const isFuture  = stageNum > stage;

              const dotColor  = isDone ? "#4ADE80" : isCurrent ? "#2563EB" : "#334155";
              const dotBg     = isDone ? "#0D2414" : isCurrent ? "#1E3A5F" : "#0F172A";
              const textColor = isDone ? "#4ADE80" : isCurrent ? "#93C5FD" : "#475569";

              return (
                <div key={s.label} style={{ display: "flex", alignItems: "center", flex: i < STAGES.length - 1 ? "1" : "none" }}>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.375rem" }}>
                    <div style={{
                      width: 36, height: 36, borderRadius: "50%",
                      backgroundColor: dotBg, border: `2px solid ${dotColor}`,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: "0.85rem",
                    }}>
                      {isDone ? "✓" : isCurrent ? <span style={{ fontSize: "0.65rem", color: "#93C5FD", fontWeight: 700 }}>{stageNum}</span> : <span style={{ fontSize: "0.65rem", color: "#475569" }}>{stageNum}</span>}
                    </div>
                    <div style={{ fontSize: "0.62rem", fontWeight: isCurrent ? 700 : 500, color: textColor, whiteSpace: "nowrap", textAlign: "center" }}>
                      {s.label}
                    </div>
                  </div>
                  {i < STAGES.length - 1 && (
                    <div style={{
                      flex: 1, height: 2, marginBottom: "1.1rem", marginLeft: 4, marginRight: 4,
                      backgroundColor: stageNum < stage ? "#166534" : "#334155",
                    }} />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* ── 2. NEXT ACTION REQUIRED ──────────────────────────────────────── */}
        {hasPendingDocs && (
          <div style={{ backgroundColor: "#1C1209", border: "1px solid #92400E", borderRadius: 10, padding: "1.25rem 1.5rem", marginBottom: "1rem" }}>
            <div style={{ fontSize: "0.62rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#D97706", marginBottom: "0.625rem" }}>
              ⚡ Next Action Required
            </div>
            <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "#FCD34D", marginBottom: "0.75rem" }}>
              Please upload the following documents:
            </div>

            {/* Pending document list */}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", marginBottom: "0.875rem" }}>
              {data.document_requests.filter(d => !d.fulfilled).map(doc => (
                <div key={doc.id} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span style={{ color: "#F59E0B", fontSize: "0.8rem" }}>•</span>
                  <div>
                    <div style={{ fontSize: "0.78rem", color: "#FCD34D", fontWeight: 500 }}>{doc.document_type}</div>
                    {doc.description && <div style={{ fontSize: "0.65rem", color: "#78350F", marginTop: 1 }}>{doc.description}</div>}
                  </div>
                </div>
              ))}
            </div>

            {/* Deadline */}
            {nextDueDate && (
              <div style={{ fontSize: "0.7rem", color: "#92400E", marginBottom: "0.875rem" }}>
                <span style={{ fontWeight: 600, color: "#F59E0B" }}>Deadline: </span>
                {formatDateShort(nextDueDate)}
              </div>
            )}

            {/* Upload button */}
            <label style={{
              display: "inline-flex", alignItems: "center", gap: "0.5rem",
              padding: "0.625rem 1.25rem",
              backgroundColor: uploading ? "#1E293B" : "#1a5f9e",
              color: "#fff", borderRadius: 6,
              fontSize: "0.78rem", fontWeight: 600,
              cursor: uploading ? "not-allowed" : "pointer",
            }}>
              {uploading ? "⏳ Uploading…" : uploadDone ? "✅ Uploaded!" : "📎 Upload Documents"}
              <input
                type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.xlsx,.csv"
                style={{ display: "none" }} disabled={uploading}
                onChange={handleUpload}
              />
            </label>
            {uploadError && <div style={{ marginTop: "0.5rem", fontSize: "0.7rem", color: "#F87171" }}>{uploadError}</div>}
            <div style={{ marginTop: "0.375rem", fontSize: "0.62rem", color: "#78350F" }}>
              Accepted: PDF, JPG, PNG, XLSX, CSV · Max 10 MB per file
            </div>
          </div>
        )}

        {/* All document requests (full list with status) */}
        {data.document_requests && data.document_requests.length > 0 && (
          <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 10, padding: "1.25rem 1.5rem", marginBottom: "1rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
              <div style={{ fontSize: "0.62rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748B" }}>
                Required Documents
              </div>
              <div style={{ fontSize: "0.65rem", color: "#64748B" }}>
                {data.documents_received} of {data.document_requests.length} received
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              {data.document_requests.map(doc => (
                <div key={doc.id} style={{
                  display: "flex", alignItems: "center", gap: "0.75rem",
                  padding: "0.6rem 0.875rem",
                  backgroundColor: doc.fulfilled ? "#0D2414" : "#0F172A",
                  border: `1px solid ${doc.fulfilled ? "#166534" : "#334155"}`,
                  borderRadius: 6,
                }}>
                  <span style={{ fontSize: "1rem", flexShrink: 0 }}>{doc.fulfilled ? "✅" : "📄"}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: "0.78rem", fontWeight: 500, color: doc.fulfilled ? "#4ADE80" : "#CBD5E1" }}>
                      {doc.document_type}
                    </div>
                  </div>
                  <span style={{
                    fontSize: "0.6rem", fontWeight: 700, padding: "2px 8px", borderRadius: 20,
                    backgroundColor: doc.fulfilled ? "#0D2414" : "#1C1209",
                    color: doc.fulfilled ? "#4ADE80" : "#F59E0B",
                    border: `1px solid ${doc.fulfilled ? "#166534" : "#78350F"}`,
                  }}>
                    {doc.fulfilled ? "RECEIVED" : "PENDING"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Dispute Details */}
        <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 10, padding: "1.25rem 1.5rem", marginBottom: "1rem" }}>
          <div style={{ fontSize: "0.62rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748B", marginBottom: "0.875rem" }}>
            Dispute Details
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            {([
              ["Merchant",         data.merchant || "—"],
              ["Amount",           formatAmount(data.amount, data.currency)],
              ["Transaction Type", data.transaction_type || "—"],
              ["Submitted",        formatDate(data.submission_date)],
              ["Last Updated",     formatDate(data.last_updated)],
              ["Dispute Reason",   data.dispute_reason || "—"],
            ] as [string, string][]).map(([label, value]) => (
              <div key={label}>
                <div style={{ fontSize: "0.6rem", color: "#64748B", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 2 }}>{label}</div>
                <div style={{ fontSize: "0.8rem", color: "#CBD5E1", fontWeight: 500 }}>{value}</div>
              </div>
            ))}
          </div>
        </div>

        {/* ── 3. CASE TIMELINE ─────────────────────────────────────────────── */}
        {dedupedTimeline.length > 0 && (
          <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 10, padding: "1.25rem 1.5rem", marginBottom: "1rem" }}>
            <div style={{ fontSize: "0.62rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748B", marginBottom: "0.875rem" }}>
              Case Timeline
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              {dedupedTimeline.map((event, i) => (
                <div key={i} style={{ display: "flex", gap: "0.875rem" }}>
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
                    <div style={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: "#2563EB", border: "2px solid #1E40AF", flexShrink: 0, marginTop: 3 }} />
                    {i < dedupedTimeline.length - 1 && (
                      <div style={{ width: 1, backgroundColor: "#334155", flex: 1, minHeight: 20, marginTop: 2 }} />
                    )}
                  </div>
                  <div style={{ paddingBottom: i < dedupedTimeline.length - 1 ? "0.875rem" : 0 }}>
                    <div style={{ fontSize: "0.78rem", color: "#CBD5E1", fontWeight: 500 }}>{event.description}</div>
                    {event.timestamp && (
                      <div style={{ fontSize: "0.65rem", color: "#64748B", marginTop: 2 }}>{formatDate(event.timestamp)}</div>
                    )}
                  </div>
                </div>
              ))}
              {!isTerminal && (
                <div style={{ display: "flex", gap: "0.875rem" }}>
                  <div style={{ flexShrink: 0, display: "flex", alignItems: "flex-start" }}>
                    <div style={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: "#D97706", border: "2px solid #92400E", marginTop: 3 }} />
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

        {/* ── 3b. MESSAGES FROM SECUREBANK ─────────────────────────────────── */}
        {comms.length > 0 && (
          <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 10, padding: "1.25rem 1.5rem", marginBottom: "1rem" }}>
            <div style={{ fontSize: "0.62rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748B", marginBottom: "0.875rem" }}>
              Messages from SecureBank
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {comms.map(comm => (
                <div key={comm.id} style={{ border: "1px solid #334155", borderRadius: 6, overflow: "hidden" }}>
                  <button
                    onClick={() => setExpandedComm(expandedComm === comm.id ? null : comm.id)}
                    style={{
                      width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "0.75rem 0.875rem", backgroundColor: "#0F172A",
                      border: "none", cursor: "pointer", textAlign: "left",
                    }}
                  >
                    <div>
                      <div style={{ fontSize: "0.78rem", fontWeight: 600, color: "#F8FAFC" }}>{comm.subject}</div>
                      <div style={{ fontSize: "0.65rem", color: "#64748B", marginTop: 2 }}>
                        {formatDate(comm.sent_at || comm.created_at)}
                      </div>
                    </div>
                    <span style={{ fontSize: "0.65rem", color: "#475569", flexShrink: 0, marginLeft: "0.5rem" }}>
                      {expandedComm === comm.id ? "▲" : "▼"}
                    </span>
                  </button>
                  {expandedComm === comm.id && (
                    <div
                      style={{ padding: "1rem 0.875rem", backgroundColor: "#1E293B", borderTop: "1px solid #334155", fontSize: "0.8rem" }}
                      dangerouslySetInnerHTML={{ __html: comm.body }}
                    />
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        <div style={{ textAlign: "center", marginTop: "2rem", fontSize: "0.62rem", color: "#334155" }}>
          <div>SecureBank Dispute Resolution Centre</div>
          <div style={{ marginTop: 4 }}>For assistance, contact us at 1800-XXX-XXXX (toll free)</div>
          <a href="/track" style={{ display: "block", marginTop: "0.75rem", color: "#475569", textDecoration: "none" }}>
            ← Track another dispute
          </a>
        </div>

      </div>
    </div>
  );
}
