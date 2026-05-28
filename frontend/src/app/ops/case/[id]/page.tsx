"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import toast from "react-hot-toast";
import {
  ArrowLeft, AlertTriangle, Shield, CreditCard,
  FileText, CheckCircle, Loader2, Activity, User,
  Lock, Clock, MessageSquare, Upload, GitBranch,
  Flag, Copy, Send, RefreshCw, BarChart2, Users,
} from "lucide-react";
import { cn, formatCurrency, formatDate, getPriorityColor, getStatusColor, formatConfidence } from "@/lib/utils";
import {
  getCase, getAuditLogs, getWorkflowStates,
  getCaseNotes, addCaseNote,
  getDocumentRequests, createDocumentRequest, fulfillDocumentRequest,
  acquireCaseLock, releaseCaseLock, checkCaseLock,
  performAnalystAction,
  getCaseTimeline, getCaseRiskExplanation,
} from "@/lib/api";
import type { DisputeCase, AuditLog, WorkflowState, CaseNote, DocumentRequest, TimelineEntry, RiskIndicator } from "@/types";
import RiskTags from "@/components/dispute/RiskTags";
import ConfidenceScore from "@/components/dispute/ConfidenceScore";

const ANALYST_ID = "analyst_ops"; // In production this comes from auth context

// ── SLA Countdown ──────────────────────────────────────────────────────────────

function SlaCountdown({ deadline, breached }: { deadline?: string; breached: boolean }) {
  const [remaining, setRemaining] = useState("");

  useEffect(() => {
    if (!deadline) return;
    const tick = () => {
      const diff = new Date(deadline).getTime() - Date.now();
      if (diff <= 0) { setRemaining("SLA BREACHED"); return; }
      const h = Math.floor(diff / 3_600_000);
      const m = Math.floor((diff % 3_600_000) / 60_000);
      setRemaining(`${h}h ${m}m remaining`);
    };
    tick();
    const id = setInterval(tick, 30_000);
    return () => clearInterval(id);
  }, [deadline]);

  if (!deadline) return null;
  return (
    <div className={cn("flex items-center gap-1.5 text-xs font-mono px-2 py-1 rounded border",
      breached ? "text-red-400 border-red-400/30 bg-red-400/10" : "text-amber-400 border-amber-400/30 bg-amber-400/10"
    )}>
      <Clock className="w-3 h-3" />
      {remaining || "Calculating…"}
    </div>
  );
}

// ── Info row ──────────────────────────────────────────────────────────────────

function InfoRow({ label, value, mono = false }: { label: string; value?: string | number | boolean | null; mono?: boolean }) {
  const display = value === true ? "Yes" : value === false ? "No" : (value ?? "—");
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 border-b border-bfsi-border last:border-0">
      <span className="text-xs text-bfsi-text-dim flex-shrink-0 w-44">{label}</span>
      <span className={cn("text-xs text-bfsi-text text-right break-all", mono && "font-mono")}>{String(display)}</span>
    </div>
  );
}

// ── Queue display name ─────────────────────────────────────────────────────────

const QUEUE_DISPLAY: Record<string, string> = {
  FRAUD_OPS: "Fraud Operations",
  ATM_INVESTIGATION: "ATM Investigation",
  CHARGEBACK_TEAM: "Chargeback Team",
  COMPLIANCE_REVIEW: "Compliance Review",
  HIGH_PRIORITY: "High Priority",
  GENERAL: "General",
};

// ── Main page ──────────────────────────────────────────────────────────────────

export default function OpsCaseDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [caseData, setCaseData]           = useState<DisputeCase | null>(null);
  const [auditLogs, setAuditLogs]         = useState<AuditLog[]>([]);
  const [workflowStates, setWorkflowStates] = useState<WorkflowState[]>([]);
  const [notes, setNotes]                 = useState<CaseNote[]>([]);
  const [docRequests, setDocRequests]     = useState<DocumentRequest[]>([]);
  const [timeline, setTimeline]           = useState<TimelineEntry[]>([]);
  const [riskData, setRiskData]           = useState<{ risk_indicators: RiskIndicator[]; investigation_summary: string } | null>(null);
  const [loading, setLoading]             = useState(true);
  const [lockInfo, setLockInfo]           = useState<{ locked: boolean; locked_by?: string; expires_at?: string } | null>(null);
  const [activeTab, setActiveTab]         = useState<"overview"|"investigation"|"notes"|"documents"|"timeline"|"audit">("overview");

  // Note form
  const [noteText, setNoteText]           = useState("");
  const [noteInternal, setNoteInternal]   = useState(true);
  const [savingNote, setSavingNote]       = useState(false);

  // Doc request form
  const [docType, setDocType]             = useState("");
  const [docDesc, setDocDesc]             = useState("");
  const [savingDoc, setSavingDoc]         = useState(false);

  // Analyst action
  const [actionLoading, setActionLoading] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [c, a, w, n, dr, tl, rx, lk] = await Promise.all([
        getCase(id),
        getAuditLogs(id),
        getWorkflowStates(id),
        getCaseNotes(id),
        getDocumentRequests(id),
        getCaseTimeline(id),
        getCaseRiskExplanation(id),
        checkCaseLock(id),
      ]);
      setCaseData(c);
      setAuditLogs(a.audit_logs);
      setWorkflowStates(w.workflow_states);
      setNotes(n);
      setDocRequests(dr);
      setTimeline(tl);
      setRiskData(rx);
      setLockInfo(lk);
    } catch {
      toast.error("Case not found");
      router.push("/ops/disputes");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // Acquire lock on mount
  useEffect(() => {
    if (!id) return;
    acquireCaseLock(id, ANALYST_ID).then((r) => {
      if (!r.acquired) toast(`Case is locked by ${r.locked_by}`, { icon: "🔒" });
    });
    return () => { releaseCaseLock(id, ANALYST_ID).catch(() => {}); };
  }, [id]);

  async function handleAction(action: string, opts?: { note?: string; new_assignee?: string; new_queue?: string }) {
    if (!caseData || actionLoading) return;
    setActionLoading(true);
    try {
      const updated = await performAnalystAction(caseData.case_id, action, ANALYST_ID, opts);
      setCaseData(updated);
      toast.success(`Action "${action}" completed`);
      load();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Action failed");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleAddNote() {
    if (!caseData || !noteText.trim() || savingNote) return;
    setSavingNote(true);
    try {
      const n = await addCaseNote(caseData.case_id, ANALYST_ID, noteText.trim(), noteInternal);
      setNotes((prev) => [...prev, n]);
      setNoteText("");
      toast.success("Note added");
    } catch {
      toast.error("Failed to add note");
    } finally {
      setSavingNote(false);
    }
  }

  async function handleDocRequest() {
    if (!caseData || !docType.trim() || savingDoc) return;
    setSavingDoc(true);
    try {
      const dr = await createDocumentRequest(caseData.case_id, ANALYST_ID, docType.trim(), docDesc.trim());
      setDocRequests((prev) => [...prev, dr]);
      setCaseData((c) => c ? { ...c, status: "Pending Documents" } : c);
      setDocType("");
      setDocDesc("");
      toast.success("Document request sent");
    } catch {
      toast.error("Failed to create document request");
    } finally {
      setSavingDoc(false);
    }
  }

  async function handleFulfill(reqId: number) {
    try {
      const updated = await fulfillDocumentRequest(reqId);
      setDocRequests((prev) => prev.map((r) => r.id === reqId ? updated : r));
      toast.success("Request marked fulfilled");
    } catch {
      toast.error("Failed to fulfill request");
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center py-24">
      <div className="flex items-center gap-3 text-bfsi-text-muted">
        <Loader2 className="w-5 h-5 animate-spin text-bfsi-gold" />
        Loading case workspace…
      </div>
    </div>
  );

  if (!caseData) return null;

  const tabs = [
    { key: "overview",      label: "Transaction",   icon: CreditCard },
    { key: "investigation", label: "Investigation",  icon: BarChart2 },
    { key: "notes",         label: `Notes (${notes.length})`, icon: MessageSquare },
    { key: "documents",     label: `Documents (${docRequests.length})`, icon: Upload },
    { key: "timeline",      label: "Timeline",       icon: GitBranch },
    { key: "audit",         label: "Audit Trail",    icon: FileText },
  ] as const;

  return (
    <>
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 mb-6 text-sm">
        <Link href="/ops/disputes" className="text-bfsi-text-dim hover:text-bfsi-text transition-colors flex items-center gap-1">
          <ArrowLeft className="w-4 h-4" /> Cases
        </Link>
        <span className="text-bfsi-border">/</span>
        <span className="text-bfsi-text font-mono text-xs">{caseData.case_id}</span>
      </div>

      {/* Case header */}
      <div className="bfsi-card bfsi-card-accent p-6 mb-4">
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-6">
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <span className="text-xs font-mono text-bfsi-text-dim">{caseData.case_id}</span>
              <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full border", getPriorityColor(caseData.priority as never))}>
                {caseData.priority}
              </span>
              <span className={cn("text-xs px-2 py-0.5 rounded-full border", getStatusColor(caseData.status as never))}>
                {caseData.status}
              </span>
              {caseData.fraud_suspicion && (
                <span className="flex items-center gap-1 text-xs text-red-400 bg-red-400/10 border border-red-400/30 px-2 py-0.5 rounded-full">
                  <AlertTriangle className="w-3 h-3" /> Fraud Indicator
                </span>
              )}
              {caseData.requires_manual_review && (
                <span className="flex items-center gap-1 text-xs text-amber-400 bg-amber-400/10 border border-amber-400/30 px-2 py-0.5 rounded-full">
                  <Flag className="w-3 h-3" /> Manual Review Required
                </span>
              )}
              {caseData.duplicate_of && (
                <span className="flex items-center gap-1 text-xs text-purple-400 bg-purple-400/10 border border-purple-400/30 px-2 py-0.5 rounded-full">
                  <Copy className="w-3 h-3" /> Duplicate of {caseData.duplicate_of}
                </span>
              )}
              {lockInfo?.locked && lockInfo.locked_by !== ANALYST_ID && (
                <span className="flex items-center gap-1 text-xs text-gray-400 bg-gray-400/10 border border-gray-400/30 px-2 py-0.5 rounded-full">
                  <Lock className="w-3 h-3" /> Locked by {lockInfo.locked_by}
                </span>
              )}
              <SlaCountdown deadline={caseData.sla_deadline} breached={caseData.sla_breached} />
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-1">Customer</p>
                <p className="text-sm font-semibold text-bfsi-text">{caseData.customer_name || "—"}</p>
                <p className="text-xs text-bfsi-text-dim font-mono">{caseData.customer_id}</p>
              </div>
              <div>
                <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-1">Amount</p>
                <p className="text-lg font-bold text-bfsi-text font-mono">{formatCurrency(caseData.amount, caseData.currency)}</p>
                <p className="text-xs text-bfsi-text-dim">{caseData.transaction_type}</p>
              </div>
              <div>
                <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-1">Queue</p>
                <p className="text-sm font-medium text-bfsi-text">{QUEUE_DISPLAY[caseData.assigned_queue || ""] || caseData.assigned_queue || "—"}</p>
                <p className="text-xs text-bfsi-text-dim">Analyst: {caseData.assigned_analyst || "Unassigned"}</p>
              </div>
              <div>
                <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-1">Filed On</p>
                <p className="text-xs text-bfsi-text">{formatDate(caseData.created_at)}</p>
                <p className="text-xs text-bfsi-text-dim">Score: {caseData.priority_score}</p>
              </div>
            </div>
          </div>
          <div className="lg:w-56 bfsi-card p-4">
            <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-3">Review Confidence</p>
            <ConfidenceScore score={caseData.confidence_score} size="lg" />
          </div>
        </div>
        {caseData.risk_tags?.length > 0 && (
          <div className="mt-4 pt-4 border-t border-bfsi-border">
            <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-2">Risk Indicators</p>
            <RiskTags tags={caseData.risk_tags} />
          </div>
        )}
      </div>

      {/* Analyst action bar */}
      <div className="bfsi-card p-4 mb-4 flex flex-wrap items-center gap-2">
        <Shield className="w-4 h-4 text-bfsi-gold flex-shrink-0" />
        <span className="text-sm text-bfsi-text-muted mr-2">Actions:</span>
        {[
          { action: "under_investigation", label: "Investigate", color: "btn-ghost" },
          { action: "approve",   label: "Approve",   color: "btn-gold" },
          { action: "reject",    label: "Reject",    color: "bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded text-sm font-medium transition-colors" },
          { action: "escalate",  label: "Escalate",  color: "bg-amber-600 hover:bg-amber-700 text-white px-4 py-2 rounded text-sm font-medium transition-colors" },
          { action: "mark_sla_breach", label: "Mark SLA Breach", color: "btn-ghost text-red-400" },
        ].map(({ action, label, color }) => (
          <button key={action} onClick={() => handleAction(action)}
            disabled={actionLoading}
            className={cn(color, "flex items-center gap-1 text-xs disabled:opacity-50")}>
            {actionLoading && <Loader2 className="w-3 h-3 animate-spin" />}
            {label}
          </button>
        ))}
        <button onClick={load} className="btn-ghost ml-auto flex items-center gap-1 text-xs">
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-bfsi-border mb-6 overflow-x-auto">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setActiveTab(key as never)}
            className={cn("flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all whitespace-nowrap",
              activeTab === key ? "border-bfsi-gold text-bfsi-gold" : "border-transparent text-bfsi-text-dim hover:text-bfsi-text"
            )}>
            <Icon className="w-4 h-4" />{label}
          </button>
        ))}
      </div>

      {/* ── Tab: Transaction overview ───────────────────────────────────────────── */}
      {activeTab === "overview" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bfsi-card p-5">
            <p className="section-header">Customer Information</p>
            <InfoRow label="Customer Name"  value={caseData.customer_name} />
            <InfoRow label="Customer ID"    value={caseData.customer_id} mono />
            <InfoRow label="Email"          value={caseData.email} />
            <InfoRow label="Phone"          value={caseData.phone} />
          </div>
          <div className="bfsi-card p-5">
            <p className="section-header">Transaction Details</p>
            <InfoRow label="Transaction ID"   value={caseData.transaction_id} mono />
            <InfoRow label="Transaction Type" value={caseData.transaction_type} />
            <InfoRow label="Merchant"         value={caseData.merchant} />
            <InfoRow label="Amount"           value={formatCurrency(caseData.amount, caseData.currency)} />
            <InfoRow label="Date"             value={caseData.transaction_date} />
            <InfoRow label="Time"             value={caseData.transaction_time || "—"} />
          </div>
          <div className="bfsi-card p-5 lg:col-span-2">
            <p className="section-header">Dispute Submission</p>
            <InfoRow label="Dispute Reason"             value={caseData.dispute_reason} />
            <InfoRow label="Fraud Flagged by Customer"  value={caseData.fraud_selected} />
            <div className="pt-3">
              <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-2">Customer Statement</p>
              <div className="bg-bfsi-muted rounded-lg p-4 text-sm text-bfsi-text-muted leading-relaxed">
                {caseData.customer_comment || "No statement provided"}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Tab: Investigation ─────────────────────────────────────────────────── */}
      {activeTab === "investigation" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bfsi-card p-5">
            <p className="section-header">Transaction Review</p>
            <InfoRow label="Transaction Category" value={caseData.dispute_category} />
            <InfoRow label="Priority Level"       value={caseData.priority} />
            <InfoRow label="Priority Score"       value={caseData.priority_score?.toFixed(1)} />
            <InfoRow label="Fraud Indicator"      value={caseData.fraud_suspicion} />
            <InfoRow label="Review Confidence"    value={formatConfidence(caseData.confidence_score)} />
            <InfoRow label="Manual Review"        value={caseData.requires_manual_review} />
            {caseData.manual_review_reason && (
              <div className="pt-3">
                <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-1">Review Flag Reason</p>
                <p className="text-xs text-amber-400 bg-amber-400/10 px-3 py-2 rounded">{caseData.manual_review_reason}</p>
              </div>
            )}
          </div>
          <div className="bfsi-card p-5">
            <p className="section-header">Investigation Summary</p>
            <div className="text-sm text-bfsi-text-muted leading-relaxed">
              {riskData?.investigation_summary || caseData.customer_intent_summary || "No summary available"}
            </div>
          </div>
          <div className="bfsi-card p-5 lg:col-span-2">
            <p className="section-header">Investigation Notes</p>
            <div className="bg-bfsi-muted rounded-lg p-4 text-sm text-bfsi-text-muted leading-relaxed font-mono whitespace-pre-wrap">
              {caseData.structured_reasoning || "No investigation notes available"}
            </div>
            <p className="text-[10px] text-bfsi-text-dim mt-3">
              Auto-generated during intake analysis. Analysts may add supplementary notes in the Notes tab.
            </p>
          </div>
          {riskData && riskData.risk_indicators.length > 0 && (
            <div className="bfsi-card p-5 lg:col-span-2">
              <p className="section-header">Risk Indicator Explanations</p>
              <div className="space-y-3">
                {riskData.risk_indicators.map((ri) => (
                  <div key={ri.tag} className="flex gap-3 p-3 bg-bfsi-muted rounded-lg">
                    <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-xs font-mono font-semibold text-amber-400 mb-0.5">{ri.tag}</p>
                      <p className="text-xs text-bfsi-text-muted">{ri.explanation}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Tab: Notes ─────────────────────────────────────────────────────────── */}
      {activeTab === "notes" && (
        <div className="space-y-4">
          <div className="bfsi-card p-5">
            <p className="section-header">Add Note</p>
            <textarea
              className="bfsi-select w-full h-24 text-sm resize-none mb-3"
              placeholder="Enter analyst note…"
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
            />
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 text-xs text-bfsi-text-muted cursor-pointer">
                <input type="checkbox" checked={noteInternal} onChange={(e) => setNoteInternal(e.target.checked)} className="rounded" />
                Internal only (not visible to customer)
              </label>
              <button onClick={handleAddNote} disabled={!noteText.trim() || savingNote}
                className="btn-gold flex items-center gap-2 text-xs disabled:opacity-50">
                {savingNote ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                Add Note
              </button>
            </div>
          </div>
          <div className="bfsi-card p-5">
            <p className="section-header">Case Notes ({notes.length})</p>
            {notes.length === 0 ? (
              <p className="text-sm text-bfsi-text-dim">No notes yet</p>
            ) : (
              <div className="space-y-4">
                {notes.map((n) => (
                  <div key={n.id} className="border-b border-bfsi-border pb-4 last:border-0 last:pb-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <User className="w-3 h-3 text-bfsi-gold" />
                      <span className="text-xs font-semibold text-bfsi-text">{n.analyst}</span>
                      {n.is_internal && (
                        <span className="text-[10px] text-bfsi-text-dim bg-bfsi-muted px-1.5 py-0.5 rounded">Internal</span>
                      )}
                      <span className="text-[10px] text-bfsi-text-dim ml-auto">{formatDate(n.created_at)}</span>
                    </div>
                    <p className="text-sm text-bfsi-text-muted leading-relaxed">{n.note}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Tab: Documents ─────────────────────────────────────────────────────── */}
      {activeTab === "documents" && (
        <div className="space-y-4">
          <div className="bfsi-card p-5">
            <p className="section-header">Request Document</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
              <input
                className="bfsi-select text-sm"
                placeholder="Document type (e.g. Bank Statement, Police FIR)"
                value={docType}
                onChange={(e) => setDocType(e.target.value)}
              />
              <input
                className="bfsi-select text-sm"
                placeholder="Additional description (optional)"
                value={docDesc}
                onChange={(e) => setDocDesc(e.target.value)}
              />
            </div>
            <div className="flex justify-end">
              <button onClick={handleDocRequest} disabled={!docType.trim() || savingDoc}
                className="btn-gold flex items-center gap-2 text-xs disabled:opacity-50">
                {savingDoc ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                Send Request
              </button>
            </div>
          </div>
          <div className="bfsi-card p-5">
            <p className="section-header">Document Requests ({docRequests.length})</p>
            {docRequests.length === 0 ? (
              <p className="text-sm text-bfsi-text-dim">No document requests yet</p>
            ) : (
              <div className="space-y-3">
                {docRequests.map((dr) => (
                  <div key={dr.id} className="flex items-start justify-between gap-4 p-4 bg-bfsi-muted rounded-lg">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <p className="text-sm font-semibold text-bfsi-text">{dr.document_type}</p>
                        <span className={cn("text-[10px] px-1.5 py-0.5 rounded font-medium",
                          dr.fulfilled ? "bg-green-400/20 text-green-400" : "bg-amber-400/20 text-amber-400"
                        )}>
                          {dr.fulfilled ? "Fulfilled" : "Pending"}
                        </span>
                      </div>
                      {dr.description && <p className="text-xs text-bfsi-text-dim mb-1">{dr.description}</p>}
                      <p className="text-[10px] text-bfsi-text-dim">Requested by {dr.requested_by} · {formatDate(dr.created_at)}</p>
                    </div>
                    {!dr.fulfilled && (
                      <button onClick={() => handleFulfill(dr.id)}
                        className="flex items-center gap-1 text-xs text-green-400 hover:text-green-300 transition-colors">
                        <CheckCircle className="w-4 h-4" /> Mark Fulfilled
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Tab: Timeline ──────────────────────────────────────────────────────── */}
      {activeTab === "timeline" && (
        <div className="bfsi-card p-5">
          <p className="section-header">Investigation Timeline</p>
          {timeline.length === 0 ? (
            <p className="text-sm text-bfsi-text-dim">No timeline events</p>
          ) : (
            <div className="relative pl-6 space-y-0">
              <div className="absolute left-2 top-0 bottom-0 w-px bg-bfsi-border" />
              {timeline.map((entry, idx) => (
                <div key={entry.id} className="relative flex gap-4 pb-5 last:pb-0">
                  <div className="absolute -left-4 w-5 h-5 rounded-full border-2 border-bfsi-border bg-bfsi-surface flex items-center justify-center">
                    <div className={cn("w-2 h-2 rounded-full",
                      entry.actor_type === "customer" ? "bg-blue-400"
                      : entry.actor_type === "analyst" ? "bg-amber-400"
                      : "bg-bfsi-gold"
                    )} />
                  </div>
                  <div className="flex-1 ml-2">
                    <div className="flex flex-wrap items-center gap-2 mb-0.5">
                      <span className="text-xs font-semibold text-bfsi-text">{entry.label}</span>
                      <span className={cn("text-[10px] px-1.5 py-0.5 rounded font-mono",
                        entry.actor_type === "customer" ? "bg-blue-400/20 text-blue-400"
                        : entry.actor_type === "analyst" ? "bg-amber-400/20 text-amber-400"
                        : "bg-bfsi-muted text-bfsi-text-dim"
                      )}>
                        {entry.actor}
                      </span>
                      <span className="text-[10px] text-bfsi-text-dim ml-auto">{formatDate(entry.timestamp)}</span>
                    </div>
                    {entry.message && <p className="text-xs text-bfsi-text-muted">{entry.message}</p>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Tab: Audit ─────────────────────────────────────────────────────────── */}
      {activeTab === "audit" && (
        <div className="bfsi-card p-5">
          <p className="section-header">Immutable Audit Log</p>
          {auditLogs.length === 0 ? (
            <p className="text-sm text-bfsi-text-dim">No audit events recorded</p>
          ) : (
            <div className="space-y-3">
              {auditLogs.map((log) => (
                <div key={log.id} className="flex gap-4 py-3 border-b border-bfsi-border last:border-0">
                  <div className="flex-shrink-0"><div className="w-2 h-2 rounded-full bg-bfsi-gold mt-1.5" /></div>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <span className="text-xs font-mono font-semibold text-bfsi-gold">{log.event_type}</span>
                      {log.stage && <span className="text-[10px] text-bfsi-text-dim bg-bfsi-muted px-1.5 py-0.5 rounded">{log.stage}</span>}
                      <span className="text-[10px] text-bfsi-text-dim ml-auto">{formatDate(log.created_at)}</span>
                    </div>
                    <p className="text-xs text-bfsi-text-muted">{log.message}</p>
                    <p className="text-[10px] text-bfsi-text-dim mt-0.5">Actor: {log.actor}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}
