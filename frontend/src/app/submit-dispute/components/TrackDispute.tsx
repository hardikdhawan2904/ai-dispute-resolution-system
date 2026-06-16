"use client";

import { useState, useEffect, useRef, useCallback, type ChangeEvent, type DragEvent, type FormEvent } from "react";
import { Search, RefreshCw, AlertCircle, CheckCircle2, FileText, Upload, X, CheckCircle } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────────

interface TimelineEvent {
  description: string;
  timestamp:   string | null;
}

interface TrackingData {
  case_id:              string;
  status:               string;
  dispute_reason:       string | null;
  merchant:             string;
  amount:               number;
  currency:             string;
  transaction_type:     string;
  submission_date:      string;
  last_updated:         string | null;
  estimated_resolution: string;
  document_requested:   boolean;
  required_documents:   string[];
  pending_documents:    string[];
  documents_received:   number;
  timeline:             TimelineEvent[];
}

// ── Constants ──────────────────────────────────────────────────────────────────

// Fixed progress steps always shown in order
const PROGRESS_STEPS = [
  "Dispute Submitted",
  "Under Review",
  "Investigation In Progress",
  "Resolved",
] as const;

// Maps customer-visible status to which progress step is "current"
const STATUS_TO_STEP: Record<string, number> = {
  "Dispute Submitted":         0,
  "Under Review":              1,
  "Documents Requested":       1,
  "Investigation In Progress": 2,
  "Resolved":                  3,
};

const STATUS_BADGE: Record<string, string> = {
  "Dispute Submitted":         "text-blue-700 bg-blue-50 border-blue-200",
  "Under Review":              "text-amber-700 bg-amber-50 border-amber-200",
  "Documents Requested":       "text-amber-700 bg-amber-50 border-amber-200",
  "Investigation In Progress": "text-blue-700 bg-blue-50 border-blue-200",
  "Resolved":                  "text-green-700 bg-green-50 border-green-200",
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-IN", {
      day: "numeric", month: "short", year: "numeric",
    });
  } catch { return iso; }
}

function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      day: "numeric", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

function fmtAmount(amount: number, currency: string): string {
  return `${currency} ${amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`;
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function DataRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value?: string | null;
  mono?: boolean;
}) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-gray-50 last:border-0">
      <span className="text-[11px] text-gray-400 w-32 shrink-0 font-medium pt-0.5">
        {label}
      </span>
      <span className={`text-xs text-gray-800 font-medium leading-relaxed ${mono ? "font-mono" : ""}`}>
        {value}
      </span>
    </div>
  );
}

// ── DocumentUploadSection ──────────────────────────────────────────────────────

const ALLOWED_EXTS = [".pdf", ".jpg", ".jpeg", ".png", ".xlsx", ".csv"];

function DocumentUploadSection({
  caseId,
  requiredDocuments,
  pendingDocuments,
  documentsReceived,
}: {
  caseId: string;
  requiredDocuments: string[];
  pendingDocuments: string[];
  documentsReceived: number;
}) {
  const fileRef                     = useRef<HTMLInputElement>(null);
  const [files, setFiles]           = useState<File[]>([]);
  const [uploading, setUploading]   = useState(false);
  const [uploaded, setUploaded]     = useState(false);
  const [uploadError, setUploadError] = useState("");

  function handleFiles(selected: FileList | null) {
    if (!selected) return;
    const valid = Array.from(selected).filter(f =>
      ALLOWED_EXTS.some(ext => f.name.toLowerCase().endsWith(ext))
    );
    setFiles(prev => {
      const names = new Set(prev.map(f => f.name));
      return [...prev, ...valid.filter(f => !names.has(f.name))];
    });
    setUploadError("");
  }

  function removeFile(name: string) {
    setFiles(prev => prev.filter(f => f.name !== name));
  }

  async function handleUpload() {
    if (!files.length || uploading) return;
    setUploading(true);
    setUploadError("");
    try {
      const form = new FormData();
      files.forEach(f => form.append("files", f));
      const res = await fetch(`${API_BASE}/api/disputes/cases/${caseId}/documents`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Upload failed");
      }
      setUploaded(true);
      setFiles([]);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="border border-amber-200 rounded overflow-hidden">
      {/* Header */}
      <div className="bg-amber-50 px-4 py-3 border-b border-amber-200">
        <p className="text-xs font-semibold text-amber-800">Documents Required</p>
        <p className="text-[11px] text-amber-700 mt-0.5 leading-relaxed">
          Please upload the documents listed below to proceed with your dispute.
        </p>
      </div>

      {/* Pending document list — only remaining ones */}
      {pendingDocuments.length > 0 && (
        <div className="bg-white px-4 pt-3 pb-2">
          <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-2">
            {documentsReceived > 0
              ? `Remaining (${pendingDocuments.length} of ${requiredDocuments.length})`
              : `Required (${pendingDocuments.length})`}
          </p>
          <div className="space-y-1.5">
            {pendingDocuments.map((doc, i) => (
              <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 bg-gray-50 border border-gray-100 rounded">
                <FileText className="w-3 h-3 text-blue-500 shrink-0" />
                <span className="text-xs text-gray-700">{doc}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Upload area */}
      <div className="bg-white px-4 pb-4 pt-3 border-t border-gray-100">
        {uploaded ? (
          <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded">
            <CheckCircle className="w-4 h-4 text-green-600 shrink-0" />
            <div>
              <p className="text-xs font-semibold text-green-800">Documents uploaded successfully</p>
              <p className="text-[11px] text-green-700 mt-0.5">Our team will review and update your case status.</p>
            </div>
          </div>
        ) : (
          <>
            {/* Drop zone */}
            <div
              onClick={() => fileRef.current?.click()}
              onDragOver={e => e.preventDefault()}
              onDrop={e => { e.preventDefault(); handleFiles(e.dataTransfer.files); }}
              className="border-2 border-dashed border-gray-200 rounded-lg p-4 text-center cursor-pointer hover:border-blue-300 hover:bg-blue-50 transition-colors"
            >
              <Upload className="w-5 h-5 text-gray-400 mx-auto mb-1.5" />
              <p className="text-xs font-medium text-gray-600">Click to upload or drag & drop</p>
              <p className="text-[11px] text-gray-400 mt-0.5">PDF, JPG, PNG, XLSX — max 10 MB each</p>
              <input
                ref={fileRef}
                type="file"
                multiple
                accept=".pdf,.jpg,.jpeg,.png,.xlsx,.csv"
                className="hidden"
                onChange={e => handleFiles(e.target.files)}
              />
            </div>

            {/* Selected files */}
            {files.length > 0 && (
              <div className="mt-2 space-y-1.5">
                {files.map(f => (
                  <div key={f.name} className="flex items-center justify-between px-2.5 py-1.5 bg-blue-50 border border-blue-100 rounded">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="w-3 h-3 text-blue-500 shrink-0" />
                      <span className="text-xs text-blue-800 truncate">{f.name}</span>
                      <span className="text-[10px] text-blue-400 shrink-0">{(f.size / 1024).toFixed(0)} KB</span>
                    </div>
                    <button onClick={() => removeFile(f.name)} className="ml-2 text-blue-400 hover:text-blue-600 shrink-0">
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {uploadError && (
              <p className="mt-2 flex items-center gap-1.5 text-xs text-red-600">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                {uploadError}
              </p>
            )}

            <button
              onClick={handleUpload}
              disabled={!files.length || uploading}
              className="mt-3 w-full py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-100 disabled:text-gray-400 text-white text-xs font-semibold rounded transition-colors flex items-center justify-center gap-2"
            >
              {uploading
                ? <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Uploading…</>
                : <><Upload className="w-3.5 h-3.5" /> Upload Documents</>
              }
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ── TrackDispute ───────────────────────────────────────────────────────────────

interface TrackDisputeProps {
  initialCaseId?: string;
}

export default function TrackDispute({ initialCaseId }: TrackDisputeProps) {
  const [caseInput, setCaseInput]   = useState(initialCaseId || "");
  const [loading, setLoading]       = useState(false);
  const [data, setData]             = useState<TrackingData | null>(null);
  const [error, setError]           = useState("");
  const sseRef                      = useRef<EventSource | null>(null);

  const fetchCase = useCallback(async (id: string) => {
    // Normalise: "CASE-527" or "CASE-00527" → "CASE-000527" (always 6-digit suffix)
    const raw = id.trim().toUpperCase();
    const match = raw.match(/^(CASE-)(\d+)$/);
    const caseId = match ? `CASE-${match[2].padStart(6, "0")}` : raw;
    if (!caseId) return;

    setLoading(true);
    setError("");
    setData(null);

    try {
      const res = await fetch(`${API_BASE}/api/disputes/track/${caseId}`);
      if (res.status === 404) {
        setError("Case not found. Please check your case reference and try again.");
        return;
      }
      if (!res.ok) throw new Error("Unable to retrieve case. Please try again later.");
      const json: TrackingData = await res.json();
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to retrieve case.");
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-fetch when component mounts with an initialCaseId
  useEffect(() => {
    if (initialCaseId) {
      setCaseInput(initialCaseId);
      fetchCase(initialCaseId);
    }
  }, [initialCaseId, fetchCase]);

  // Open SSE stream whenever a case is successfully loaded
  useEffect(() => {
    if (!data?.case_id) return;

    // Close any existing stream
    sseRef.current?.close();

    const es = new EventSource(
      `${API_BASE}/api/disputes/track/${data.case_id}/events`
    );

    es.onmessage = (e) => {
      try {
        const updated: TrackingData = JSON.parse(e.data);
        if (updated?.case_id) {
          setData(updated);
        }
      } catch {
        // ignore parse errors from keepalive comments
      }
    };

    // Close stream gracefully on error (will reconnect on next fetch)
    es.onerror = () => es.close();

    sseRef.current = es;

    return () => {
      es.close();
      sseRef.current = null;
    };
  }, [data?.case_id]);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    fetchCase(caseInput);
  }

  const currentStepIdx = data ? (STATUS_TO_STEP[data.status] ?? 0) : -1;

  return (
    <div className="space-y-4">

      {/* ── Search ──────────────────────────────────────────────────── */}
      <div className="bg-white border border-gray-200 rounded">
        <div className="px-4 py-3 border-b border-gray-100">
          <p className="text-xs font-semibold text-gray-700">Track Your Dispute</p>
          <p className="text-[11px] text-gray-400 mt-0.5">
            Enter your case reference number to view the current status
          </p>
        </div>
        <div className="p-4">
          <form onSubmit={handleSearch} className="flex gap-2">
            <input
              type="text"
              value={caseInput}
              onChange={(e) => setCaseInput(e.target.value.toUpperCase())}
              placeholder="e.g. CASE-000527"
              spellCheck={false}
              className="flex-1 border border-gray-200 rounded px-3 py-2 text-sm font-mono text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 transition-colors"
            />
            <button
              type="submit"
              disabled={loading || !caseInput.trim()}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-200 disabled:text-gray-400 text-white text-sm font-medium rounded transition-colors flex items-center gap-2 shrink-0"
            >
              {loading
                ? <RefreshCw className="w-4 h-4 animate-spin" />
                : <Search className="w-4 h-4" />
              }
              <span className="hidden sm:inline">View Case</span>
            </button>
          </form>

          {error && (
            <p className="mt-3 flex items-center gap-1.5 text-xs text-red-600">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              {error}
            </p>
          )}
        </div>
      </div>

      {/* ── No case yet ─────────────────────────────────────────────── */}
      {!data && !loading && !error && (
        <div className="bg-white border border-gray-200 rounded px-4 py-10 text-center">
          <p className="text-sm text-gray-500">
            Enter your case reference above to view dispute status.
          </p>
          <p className="text-[11px] text-gray-400 mt-1.5">
            Your case reference was provided when you submitted your dispute.
          </p>
        </div>
      )}

      {/* ── Case loaded ─────────────────────────────────────────────── */}
      {data && (
        <>

          {/* Case overview */}
          <div className="bg-white border border-gray-200 rounded">
            <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
              <p className="text-xs font-semibold text-gray-700">Case Overview</p>
              <span className={`text-[11px] font-semibold px-2.5 py-1 rounded border ${
                STATUS_BADGE[data.status] || "text-gray-600 bg-gray-100 border-gray-200"
              }`}>
                {data.status}
              </span>
            </div>
            <div className="px-4 py-3">
              <DataRow label="Case Reference"   value={data.case_id} mono />
              <DataRow label="Dispute Reason"   value={data.dispute_reason} />
              <DataRow label="Merchant"         value={data.merchant} />
              <DataRow label="Amount"           value={fmtAmount(data.amount, data.currency)} />
              <DataRow label="Transaction Type" value={data.transaction_type} />
              <DataRow label="Submitted"        value={fmtDate(data.submission_date)} />
              <DataRow label="Last Updated"     value={fmtDateTime(data.last_updated)} />
              <DataRow label="Est. Resolution"  value={data.estimated_resolution} />
            </div>
          </div>

          {/* Documents — only show upload when actually waiting for them */}
          {data.status === "Documents Requested" ? (
            <DocumentUploadSection
              caseId={data.case_id}
              requiredDocuments={data.required_documents ?? []}
              pendingDocuments={data.pending_documents ?? data.required_documents ?? []}
              documentsReceived={data.documents_received ?? 0}
            />
          ) : data.required_documents && data.required_documents.length > 0 && (
            <div className="border border-green-200 bg-green-50 rounded px-4 py-3 flex items-start gap-2.5">
              <CheckCircle2 className="w-4 h-4 text-green-600 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-semibold text-green-800">Documents Received</p>
                <p className="text-[11px] text-green-700 mt-0.5 leading-relaxed">
                  Your documents have been submitted and are under review by our disputes team.
                </p>
              </div>
            </div>
          )}

          {/* Case progress */}
          <div className="bg-white border border-gray-200 rounded">
            <div className="px-4 py-3 border-b border-gray-100">
              <p className="text-xs font-semibold text-gray-700">Case Progress</p>
            </div>
            <div className="px-4 py-4">

              {/* Fixed progress steps */}
              <div>
                {PROGRESS_STEPS.map((step, i) => {
                  const isCompleted = i < currentStepIdx;
                  const isCurrent   = i === currentStepIdx;
                  const isLast      = i === PROGRESS_STEPS.length - 1;

                  return (
                    <div key={step} className="flex items-start gap-3">
                      {/* Circle + connector line */}
                      <div className="flex flex-col items-center shrink-0">
                        <div className={[
                          "w-5 h-5 rounded-full flex items-center justify-center mt-0.5",
                          isCompleted
                            ? "bg-blue-600"
                            : isCurrent
                            ? "bg-amber-500"
                            : "bg-white border-2 border-gray-200",
                        ].join(" ")}>
                          {isCompleted && (
                            <CheckCircle2 className="w-3 h-3 text-white" />
                          )}
                          {isCurrent && (
                            <div className="w-2 h-2 rounded-full bg-white" />
                          )}
                        </div>
                        {!isLast && (
                          <div className={`w-px h-8 ${isCompleted ? "bg-blue-200" : "bg-gray-100"}`} />
                        )}
                      </div>

                      {/* Label */}
                      <div className={`pb-8 last:pb-0 ${isLast ? "pb-0" : ""}`}>
                        <p className={`text-sm ${
                          isCompleted
                            ? "text-gray-700 font-medium"
                            : isCurrent
                            ? "text-gray-900 font-semibold"
                            : "text-gray-400"
                        }`}>
                          {step}
                        </p>
                        {i === 0 && (
                          <p className="text-[11px] text-gray-400 mt-0.5">
                            {fmtDateTime(data.submission_date)}
                          </p>
                        )}
                        {isCurrent && i > 0 && data.last_updated && (
                          <p className="text-[11px] text-gray-400 mt-0.5">
                            {fmtDateTime(data.last_updated)}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Activity log from backend audit trail */}
              {data.timeline.length > 0 && (
                <div className="mt-5 pt-4 border-t border-gray-100">
                  <p className="text-xs font-semibold text-gray-600 mb-3">Activity Log</p>
                  <div className="space-y-3">
                    {data.timeline.map((event, i) => (
                      <div key={i} className="flex items-start gap-2.5">
                        <div className="w-1.5 h-1.5 rounded-full bg-gray-300 shrink-0 mt-1.5" />
                        <div>
                          <p className="text-xs text-gray-700">{event.description}</p>
                          {event.timestamp && (
                            <p className="text-[11px] text-gray-400 mt-0.5">
                              {fmtDateTime(event.timestamp)}
                            </p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          <p className="text-center text-[11px] text-gray-400">
            Status updates automatically — no need to refresh this page.
          </p>
        </>
      )}
    </div>
  );
}
