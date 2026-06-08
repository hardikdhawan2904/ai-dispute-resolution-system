"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import toast from "react-hot-toast";
import {
  ArrowLeft, AlertTriangle, Brain, Shield, CreditCard,
  FileText, CheckCircle, Loader2, Activity, RefreshCw,
  ImageIcon, X, ZoomIn, Search, ListChecks, Lightbulb,
  BarChart2, ChevronDown, ChevronUp, AlertCircle, Eye,
} from "lucide-react";
import { cn, formatCurrency, formatDate, getPriorityColor, getStatusColor, formatConfidence } from "@/lib/utils";
import { getCase, getAuditLogs, getWorkflowStates, updateCaseStatus, reanalyseCase, getCaseUploads } from "@/lib/api";
import type { CaseUploadFile } from "@/lib/api";
import type { DisputeCase, AuditLog, WorkflowState, CaseStatus } from "@/types";
import RiskTags from "@/components/dispute/RiskTags";
import ConfidenceScore from "@/components/dispute/ConfidenceScore";
import WorkflowStatus from "@/components/dispute/WorkflowStatus";
import { useDisputeSocket, type DisputeSocketEvent } from "@/hooks/useDisputeSocket";

const CASE_STATUSES: CaseStatus[] = [
  "Dispute Raised", "Under Investigation", "Pending Documents",
  "Escalated", "Resolved", "Rejected", "Closed",
];

function InfoRow({ label, value, mono = false }: { label: string; value?: string | number | boolean | null; mono?: boolean }) {
  const display = value === true ? "Yes" : value === false ? "No" : value ?? "—";
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 border-b border-bfsi-border last:border-0">
      <span className="text-xs text-bfsi-text-dim flex-shrink-0 w-40">{label}</span>
      <span className={cn("text-xs text-bfsi-text text-right break-all", mono && "font-mono")}>{String(display)}</span>
    </div>
  );
}

export default function InternalReviewCaseDetail() {
  const { caseId } = useParams<{ caseId: string }>();
  const router = useRouter();

  const [caseData, setCaseData]             = useState<DisputeCase | null>(null);
  const [auditLogs, setAuditLogs]           = useState<AuditLog[]>([]);
  const [workflowStates, setWorkflowStates] = useState<WorkflowState[]>([]);
  const [loading, setLoading]               = useState(true);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [reanalysing, setReanalysing]       = useState(false);
  const [elapsed, setElapsed]               = useState(0);
  const [uploads, setUploads]               = useState<CaseUploadFile[]>([]);
  const [lightbox, setLightbox]             = useState<string | null>(null);

  async function handleReanalyse() {
    if (!caseData || reanalysing) return;
    setReanalysing(true);
    setElapsed(0);
    const timer = setInterval(() => setElapsed(s => s + 1), 1000);
    try {
      const updated = await reanalyseCase(caseData.case_id);
      setCaseData(updated);
      toast.success(`Re-analysis complete — confidence: ${(updated.confidence_score * 100).toFixed(0)}%`);
    } catch (err: unknown) {
      toast.error((err instanceof Error ? err.message : null) || "Re-analysis failed");
    } finally {
      clearInterval(timer);
      setReanalysing(false);
    }
  }
  const [activeTab, setActiveTab]           = useState<"overview" | "ai" | "investigation" | "evidence" | "audit" | "workflow">("overview");
  const [liveUpdate, setLiveUpdate]         = useState(false);
  const [whyPlanOpen, setWhyPlanOpen]       = useState(false);

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    Promise.all([getCase(caseId), getAuditLogs(caseId), getWorkflowStates(caseId), getCaseUploads(caseId)])
      .then(([c, a, w, up]) => {
        setCaseData(c);
        setAuditLogs(a.audit_logs);
        setWorkflowStates(w.workflow_states);
        setUploads(up);
      })
      .catch(() => {
        toast.error("Case not found");
        router.push("/internal-review");
      })
      .finally(() => setLoading(false));
  }, [caseId, router]);

  // Live update: if ANALYSIS_COMPLETE arrives for this case, refresh data
  useDisputeSocket((event: DisputeSocketEvent) => {
    if (event.type === "ANALYSIS_COMPLETE" && event.case_id === caseId) {
      setCaseData(event.case as unknown as DisputeCase);
      setLiveUpdate(true);
      setTimeout(() => setLiveUpdate(false), 3_000);
    }
  });

  async function handleStatusUpdate(newStatus: string) {
    if (!caseData || updatingStatus) return;
    setUpdatingStatus(true);
    try {
      const updated = await updateCaseStatus(caseData.case_id, newStatus);
      setCaseData(updated);
      toast.success(`Status updated to "${newStatus}"`);
    } catch (err: unknown) {
      toast.error((err as Error).message || "Status update failed");
    } finally {
      setUpdatingStatus(false);
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center py-24">
      <div className="flex items-center gap-3 text-bfsi-text-muted">
        <Loader2 className="w-5 h-5 animate-spin text-bfsi-gold" />
        Loading case intelligence…
      </div>
    </div>
  );

  if (!caseData) return null;

  const tabs = [
    { key: "overview",      label: "Transaction",              icon: CreditCard },
    { key: "ai",            label: "Analysis",                 icon: Brain },
    { key: "investigation", label: "Investigation",            icon: Search },
    { key: "evidence",      label: `Evidence (${uploads.length})`, icon: ImageIcon },
    { key: "audit",         label: "Audit Trail",              icon: FileText },
    { key: "workflow",      label: "Workflow",                 icon: Activity },
  ] as const;

  return (
    <>
      {/* Re-analysis loading overlay */}
      {reanalysing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bfsi-card p-8 max-w-sm w-full mx-4 text-center space-y-5">
            <div className="flex justify-center">
              <div className="relative">
                <Loader2 className="w-12 h-12 text-bfsi-gold animate-spin" />
                <Brain className="w-5 h-5 text-bfsi-gold absolute inset-0 m-auto" />
              </div>
            </div>
            <div>
              <p className="text-base font-semibold text-bfsi-text mb-1">Re-analysing Case</p>
              <p className="text-xs text-bfsi-text-dim">Running Agent 1 → Agent 2 pipeline</p>
            </div>
            <div className="space-y-2 text-left">
              <div className={cn("flex items-center gap-2 text-xs px-3 py-2 rounded border",
                elapsed < 20 ? "border-bfsi-gold/40 text-bfsi-gold bg-bfsi-gold/5" : "border-bfsi-border text-bfsi-text-dim")}>
                <Loader2 className={cn("w-3 h-3 flex-shrink-0", elapsed < 20 ? "animate-spin" : "")} />
                {elapsed < 20 ? "Agent 1: Classifying dispute…" : "Agent 1: Complete"}
              </div>
              <div className={cn("flex items-center gap-2 text-xs px-3 py-2 rounded border",
                elapsed >= 20 ? "border-bfsi-gold/40 text-bfsi-gold bg-bfsi-gold/5" : "border-bfsi-border text-bfsi-text-dim")}>
                <Loader2 className={cn("w-3 h-3 flex-shrink-0", elapsed >= 20 ? "animate-spin" : "")} />
                {elapsed >= 20 ? "Agent 2: Building investigation plan…" : "Agent 2: Waiting…"}
              </div>
            </div>
            <p className="text-xs text-bfsi-text-dim font-mono">{elapsed}s elapsed · typically 45–90s</p>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 mb-6 text-sm">
        <Link href="/internal-review" className="text-bfsi-text-dim hover:text-bfsi-text transition-colors flex items-center gap-1">
          <ArrowLeft className="w-4 h-4" /> Internal Review
        </Link>
        <span className="text-bfsi-border">/</span>
        <span className="text-bfsi-text font-mono text-xs">{caseData.case_id}</span>
        {liveUpdate && (
          <span className="ml-2 text-xs text-green-400 bg-green-400/10 border border-green-400/30 px-2 py-0.5 rounded-full animate-pulse">
            Live updated
          </span>
        )}
      </div>

      {/* Case header */}
      <div className="bfsi-card bfsi-card-accent p-6 mb-6">
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-6">
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <span className="text-xs font-mono text-bfsi-text-dim">{caseData.case_id}</span>
              <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full border", getPriorityColor(caseData.priority as any))}>
                {caseData.priority}
              </span>
              <span className={cn("text-xs px-2 py-0.5 rounded-full border", getStatusColor(caseData.status as any))}>
                {caseData.status}
              </span>
              {caseData.fraud_suspicion && (
                <span className="flex items-center gap-1 text-xs text-red-400 bg-red-400/10 border border-red-400/30 px-2 py-0.5 rounded-full">
                  <AlertTriangle className="w-3 h-3" /> Fraud Suspected
                </span>
              )}
              {caseData.requires_manual_review && (
                <span className="flex items-center gap-1 text-xs text-amber-400 bg-amber-400/10 border border-amber-400/30 px-2 py-0.5 rounded-full">
                  <CheckCircle className="w-3 h-3" /> Human Review Required
                </span>
              )}
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
                <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-1">Category</p>
                <p className="text-sm font-medium text-bfsi-text">{caseData.dispute_category || "—"}</p>
              </div>
              <div>
                <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-1">Filed On</p>
                <p className="text-xs text-bfsi-text">{formatDate(caseData.created_at)}</p>
              </div>
            </div>
          </div>
          <div className="lg:w-64 bfsi-card p-4">
            <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-3">Confidence Score</p>
            <ConfidenceScore score={caseData.confidence_score} size="lg" />
            {caseData.requires_manual_review && caseData.manual_review_reason && (
              <p className="mt-3 text-[11px] text-amber-400 bg-amber-400/10 border border-amber-400/30 rounded px-2 py-1.5 leading-relaxed">
                {caseData.manual_review_reason}
              </p>
            )}
          </div>
        </div>
        {caseData.risk_tags?.length > 0 && (
          <div className="mt-4 pt-4 border-t border-bfsi-border">
            <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-2">Risk Signals</p>
            <RiskTags tags={caseData.risk_tags} />
          </div>
        )}
      </div>

      {/* ── Agent 1 Fallback Banner (Change 9) ───────────────────────────── */}
      {caseData.fallback_mode && (
        <div className="mb-6 p-4 rounded-xl border border-amber-400/40 bg-amber-400/5">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-amber-400 mb-1">AI Processing Unavailable at Submission</p>
              <p className="text-xs text-amber-300/80 leading-relaxed">
                AI processing was unavailable when this case was submitted. A fallback analysis was generated
                automatically and <strong className="text-amber-300">manual review is required</strong> before
                any resolution decision can be made.
              </p>
              <div className="flex flex-wrap gap-4 mt-3 text-xs text-amber-300/70">
                <span>
                  <span className="text-amber-400/60 uppercase tracking-wider text-[10px]">Failure Reason</span>
                  <span className="ml-2 font-mono font-semibold text-amber-300">{caseData.failure_reason ?? "UNKNOWN"}</span>
                </span>
                <span>
                  <span className="text-amber-400/60 uppercase tracking-wider text-[10px]">Confidence</span>
                  <span className="ml-2 font-mono font-semibold text-amber-300">
                    {Math.round((caseData.confidence_score ?? 0) * 100)}%
                  </span>
                </span>
                <span>
                  <span className="text-amber-400/60 uppercase tracking-wider text-[10px]">Fallback Mode</span>
                  <span className="ml-2 font-mono font-semibold text-amber-300">ACTIVE</span>
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Status control */}
      <div className="bfsi-card p-4 mb-6 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-bfsi-gold" />
          <span className="text-xs text-bfsi-text-dim uppercase tracking-wider font-semibold">Case Status</span>
        </div>
        <div className="flex items-center gap-3 ml-auto">
          <button onClick={handleReanalyse} disabled={reanalysing}
            className="btn-ghost flex items-center gap-1.5 text-xs text-bfsi-gold border border-bfsi-gold/30 disabled:opacity-50">
            {reanalysing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Re-analyse
          </button>
          <select
            className="bfsi-select text-sm py-1.5 pr-8 w-auto"
            value={caseData.status}
            onChange={(e) => handleStatusUpdate(e.target.value)}
            disabled={updatingStatus}
          >
            {CASE_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          {updatingStatus && <Loader2 className="w-4 h-4 animate-spin text-bfsi-gold" />}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-bfsi-border mb-6 overflow-x-auto">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={cn(
              "flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-all whitespace-nowrap",
              activeTab === key
                ? "border-bfsi-gold text-bfsi-gold"
                : "border-transparent text-bfsi-text-dim hover:text-bfsi-text"
            )}
          >
            <Icon className="w-4 h-4" />{label}
          </button>
        ))}
      </div>

      {activeTab === "overview" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bfsi-card p-5">
            <p className="section-header">Customer Information</p>
            <InfoRow label="Customer Name" value={caseData.customer_name} />
            <InfoRow label="Customer ID"   value={caseData.customer_id} mono />
            <InfoRow label="Email"         value={caseData.email ?? "—"} />
            <InfoRow label="Phone"         value={caseData.phone ?? "—"} />
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
            <InfoRow label="Dispute Reason"            value={caseData.dispute_reason} />
            <InfoRow label="Fraud Flagged by Customer" value={caseData.fraud_selected} />
            <div className="pt-3">
              <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-2">Customer Statement</p>
              <div className="bg-bfsi-muted rounded-lg p-4 text-sm text-bfsi-text-muted leading-relaxed">
                {caseData.customer_comment}
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === "ai" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bfsi-card p-5">
            <p className="section-header">Classification</p>
            <InfoRow label="Dispute Category" value={caseData.dispute_category} />
            <InfoRow label="Priority"         value={caseData.priority} />
            <InfoRow label="Fraud Suspicion"  value={caseData.fraud_suspicion} />
            <InfoRow label="Confidence Score" value={formatConfidence(caseData.confidence_score)} />
            <InfoRow label="Workflow Ready"   value={caseData.workflow_ready} />
          </div>
          <div className="bfsi-card p-5">
            <p className="section-header">Customer Intent Summary</p>
            <div className="text-sm text-bfsi-text-muted leading-relaxed">
              {caseData.customer_intent_summary || "No summary available"}
            </div>
          </div>

          {/* Evidence verification verdict */}
          <div className="bfsi-card p-5 lg:col-span-2">
            <div className="flex items-center gap-2 mb-4">
              <Shield className="w-4 h-4 text-bfsi-gold" />
              <p className="section-header mb-0">Evidence Verification</p>
            </div>
            {(caseData as any).evidence_match === null || (caseData as any).evidence_match === undefined ? (
              <div className="flex items-center gap-3 p-3 rounded-lg bg-bfsi-muted border border-bfsi-border">
                <span className="text-xs text-bfsi-text-dim">
                  {uploads.length > 0
                    ? "Document submitted — automatic verification unavailable. Please review the attached file manually."
                    : "No documents were submitted with this dispute."}
                </span>
              </div>
            ) : (caseData as any).evidence_match === true ? (
              <div className="flex items-start gap-3 p-4 rounded-lg bg-green-500/10 border border-green-500/30">
                <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-green-400 mb-1">Evidence Matches Claim</p>
                  <p className="text-sm text-bfsi-text-muted leading-relaxed">
                    {(caseData as any).evidence_match_note || "The submitted documents corroborate the customer's dispute."}
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-3 p-4 rounded-lg bg-red-500/10 border border-red-500/30">
                <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-red-400 mb-1">Evidence Does Not Match Claim</p>
                  <p className="text-sm text-bfsi-text-muted leading-relaxed">
                    {(caseData as any).evidence_match_note || "The submitted documents do not support the customer's dispute."}
                  </p>
                </div>
              </div>
            )}
          </div>
          <div className="bfsi-card p-5 lg:col-span-2">
            <div className="flex items-center gap-2 mb-4">
              <Brain className="w-4 h-4 text-bfsi-gold" />
              <p className="section-header mb-0">Structured Reasoning</p>
            </div>
            <div className="ai-reasoning">{caseData.structured_reasoning || "No reasoning available"}</div>
            <p className="text-[10px] text-bfsi-text-dim mt-3">
              Generated by LangGraph dispute workflow. For investigation guidance only — not a legal conclusion.
            </p>
          </div>
          <div className="bfsi-card p-5 lg:col-span-2">
            <p className="section-header">Risk Signal Analysis</p>
            {caseData.risk_tags?.length > 0
              ? <RiskTags tags={caseData.risk_tags} />
              : <p className="text-sm text-bfsi-text-dim">No risk signals detected.</p>
            }
          </div>

          {/* Required Documents — shown here so analysts see what evidence is needed alongside the AI analysis */}
          {(() => {
            const docs: string[] = caseData.investigation_plan?.required_documents ?? [];
            return docs.length > 0 ? (
              <div className="bfsi-card p-5 lg:col-span-2">
                <div className="flex items-center gap-2 mb-4">
                  <FileText className="w-4 h-4 text-bfsi-gold" />
                  <p className="section-header mb-0">Required Documents Checklist</p>
                  <span className="ml-auto text-[10px] text-bfsi-text-dim bg-bfsi-muted px-2 py-0.5 rounded-full border border-bfsi-border">
                    {docs.length} document{docs.length > 1 ? "s" : ""}
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {docs.map((doc: string, i: number) => (
                    <div key={i} className="flex items-center gap-2 p-2.5 bg-bfsi-muted rounded-lg border border-bfsi-border">
                      <CheckCircle className="w-3.5 h-3.5 text-bfsi-gold flex-shrink-0" />
                      <span className="text-xs text-bfsi-text-muted">{doc}</span>
                    </div>
                  ))}
                </div>
                <p className="text-[10px] text-bfsi-text-dim mt-3 pt-3 border-t border-bfsi-border">
                  Computed deterministically from dispute category, fraud signals, and transaction amount. Not LLM-generated.
                </p>
              </div>
            ) : null;
          })()}

        </div>
      )}

      {/* ── Investigation Workbench tab ──────────────────────────────────── */}
      {activeTab === "investigation" && (() => {
        const plan = caseData.investigation_plan;
        if (!plan) return (
          <div className="bfsi-card p-10 text-center">
            <Search className="w-10 h-10 text-bfsi-text-dim mx-auto mb-3" />
            <p className="text-sm text-bfsi-text-dim">Investigation plan not yet generated for this case.</p>
            <p className="text-xs text-bfsi-text-dim mt-1">Re-submit or re-analyse to trigger Agent 2.</p>
          </div>
        );

        // Colour helpers
        const complexityColor: Record<string, string> = {
          CRITICAL: "text-red-400 bg-red-400/10 border-red-400/30",
          HIGH:     "text-orange-400 bg-orange-400/10 border-orange-400/30",
          MEDIUM:   "text-yellow-400 bg-yellow-400/10 border-yellow-400/30",
          LOW:      "text-green-400 bg-green-400/10 border-green-400/30",
        };
        const queueColor: Record<string, string> = {
          FRAUD_OPS:         "text-red-400 bg-red-400/10 border-red-400/30",
          UPI_FRAUD:         "text-orange-400 bg-orange-400/10 border-orange-400/30",
          CHARGEBACK_TEAM:   "text-yellow-400 bg-yellow-400/10 border-yellow-400/30",
          ATM_INVESTIGATION: "text-purple-400 bg-purple-400/10 border-purple-400/30",
          COMPLIANCE_REVIEW: "text-pink-400 bg-pink-400/10 border-pink-400/30",
          SENIOR_ANALYST:    "text-amber-400 bg-amber-400/10 border-amber-400/30",
          MERCHANT_DISPUTES: "text-blue-400 bg-blue-400/10 border-blue-400/30",
          GENERAL:           "text-bfsi-text-dim bg-bfsi-muted border-bfsi-border",
        };
        const queueConf      = plan.queue_confidence ?? null;
        const queueConfPct   = queueConf != null ? Math.round(queueConf * 100) : null;
        const queueLabel     = queueConfPct == null ? "" : queueConfPct >= 90 ? "Very High" : queueConfPct >= 75 ? "High" : queueConfPct >= 60 ? "Moderate" : "Low";
        const queueConfColor = queueConfPct == null ? "" : queueConfPct >= 90 ? "text-green-400" : queueConfPct >= 75 ? "text-bfsi-gold" : queueConfPct >= 60 ? "text-yellow-400" : "text-red-400";
        const dqPct          = plan.data_quality_score != null ? Math.round(plan.data_quality_score * 100) : null;
        const dqColor        = dqPct == null ? "" : dqPct >= 90 ? "text-green-400" : dqPct >= 75 ? "text-bfsi-gold" : dqPct >= 60 ? "text-yellow-400" : "text-red-400";
        const invConf        = plan.investigation_confidence;
        const invConfPct     = invConf != null ? Math.round(invConf * 100) : null;
        const invConfColor   = invConfPct == null ? "" : invConfPct >= 90 ? "text-green-400" : invConfPct >= 75 ? "text-bfsi-gold" : invConfPct >= 60 ? "text-yellow-400" : "text-red-400";
        const invConfTier    = invConfPct == null ? "" : invConfPct >= 90 ? "Very High Confidence" : invConfPct >= 75 ? "High Confidence" : invConfPct >= 60 ? "Moderate Confidence" : "Requires Review";
        const invConfTierColor = invConfPct == null ? "" : invConfPct >= 90 ? "text-green-400 bg-green-400/10 border-green-400/30" : invConfPct >= 75 ? "text-bfsi-gold bg-bfsi-gold/10 border-bfsi-gold/30" : invConfPct >= 60 ? "text-yellow-400 bg-yellow-400/10 border-yellow-400/30" : "text-red-400 bg-red-400/10 border-red-400/30";

        return (
          <div className="space-y-5">

            {/* ── Change 8: Enhanced Summary Header ───────────────────────── */}
            <div className="bfsi-card bfsi-card-accent p-5">
              <div className="flex flex-wrap items-center gap-3 mb-3">
                <div className="flex items-center gap-1.5">
                  <span className={cn("text-xs font-semibold px-2.5 py-1 rounded-full border", queueColor[plan.recommended_queue] ?? "text-bfsi-text bg-bfsi-muted border-bfsi-border")}>
                    {plan.recommended_queue?.replace(/_/g, " ")}
                  </span>
                  {queueConfPct != null && (
                    <span className={cn("text-xs font-mono font-semibold", queueConfColor)} title={`Queue routing confidence — ${queueLabel}`}>
                      {queueConfPct}% <span className="text-[10px] opacity-70">({queueLabel})</span>
                    </span>
                  )}
                </div>
                <span className={cn("text-xs font-semibold px-2.5 py-1 rounded-full border", complexityColor[plan.investigation_complexity] ?? "")}>
                  {plan.investigation_complexity} COMPLEXITY
                </span>
                {plan.duplicate_found && (
                  <span className="text-xs font-semibold px-2.5 py-1 rounded-full border text-red-400 bg-red-400/10 border-red-400/30">
                    DUPLICATE DETECTED
                  </span>
                )}
                {plan.manual_review_required && (
                  <span className="text-xs font-semibold px-2.5 py-1 rounded-full border text-amber-400 bg-amber-400/10 border-amber-400/30">
                    MANUAL REVIEW
                  </span>
                )}
                {invConfTier && (
                  <span className={cn("text-[10px] font-semibold px-2.5 py-1 rounded-full border", invConfTierColor)}>
                    {invConfTier}
                  </span>
                )}
              </div>
              <p className="text-sm text-bfsi-text-muted leading-relaxed">{plan.investigation_summary}</p>
              <div className="flex flex-wrap items-center gap-6 mt-3 pt-3 border-t border-bfsi-border">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-bfsi-text-dim uppercase tracking-wider">IIA Confidence</span>
                  <span className="text-sm font-mono font-semibold text-bfsi-gold">{((plan.confidence_score ?? 0) * 100).toFixed(0)}%</span>
                </div>
                {queueConfPct != null && (
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-bfsi-text-dim uppercase tracking-wider">Queue</span>
                    <span className={cn("text-sm font-mono font-semibold", queueConfColor)}>{queueConfPct}%</span>
                  </div>
                )}
                {dqPct != null && (
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-bfsi-text-dim uppercase tracking-wider">Data Quality</span>
                    <span className={cn("text-sm font-mono font-semibold", dqColor)}>{dqPct}%</span>
                  </div>
                )}
                {invConfPct != null && (
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-bfsi-text-dim uppercase tracking-wider">Plan Confidence</span>
                    <span className={cn("text-sm font-mono font-semibold", invConfColor)}>{invConfPct}%</span>
                  </div>
                )}
              </div>
            </div>

            {/* ── Change 3: Manual Review Reasons Card ────────────────────── */}
            {plan.manual_review_required && (plan.manual_review_reason ?? []).length > 0 && (
              <div className="bfsi-card p-5 border-amber-400/30 bg-amber-400/5">
                <div className="flex items-center gap-2 mb-3">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  <p className="text-xs font-semibold text-amber-400 uppercase tracking-wider">Manual Review Required — Reasons</p>
                </div>
                <ul className="space-y-2">
                  {(plan.manual_review_reason ?? []).map((r: string, i: number) => (
                    <li key={i} className="flex items-start gap-2.5 text-xs text-amber-300/90 leading-relaxed">
                      <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* ── Change 6: Investigation Confidence Card ──────────────────── */}
            {invConf != null && (
              <div className="bfsi-card p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <BarChart2 className="w-4 h-4 text-bfsi-gold" />
                    <p className="section-header mb-0">Investigation Plan Confidence</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={cn("text-2xl font-mono font-bold", invConfColor)}>{invConfPct}%</span>
                    {invConfTier && (
                      <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full border", invConfTierColor)}>
                        {invConfTier}
                      </span>
                    )}
                  </div>
                </div>
                {/* Progress bar */}
                <div className="h-2 bg-bfsi-muted rounded-full overflow-hidden mb-4">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all",
                      (invConfPct ?? 0) >= 90 ? "bg-green-500" :
                      (invConfPct ?? 0) >= 75 ? "bg-bfsi-gold" :
                      (invConfPct ?? 0) >= 60 ? "bg-yellow-500" : "bg-red-500"
                    )}
                    style={{ width: `${invConfPct ?? 0}%` }}
                  />
                </div>
                <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-2 font-semibold">Confidence Factors</p>
                {(plan.investigation_confidence_factors ?? []).length > 0 ? (
                  <ul className="space-y-1.5">
                    {(plan.investigation_confidence_factors ?? []).map((f: string, i: number) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-bfsi-text-muted">
                        <CheckCircle className="w-3 h-3 text-bfsi-gold flex-shrink-0 mt-0.5" />
                        {f}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-bfsi-text-dim">No factors available.</p>
                )}
                <p className="text-[10px] text-bfsi-text-dim mt-3 pt-3 border-t border-bfsi-border">
                  Computed deterministically: 35% queue confidence + 30% data quality + 20% historical precedent + 10% fraud signal alignment + 5% coverage. Not LLM-generated.
                </p>
              </div>
            )}

            {/* ── Change 4: Enhanced Investigation Coverage ────────────────── */}
            {plan.investigation_coverage && (
              <div className="bfsi-card p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Eye className="w-3.5 h-3.5 text-bfsi-text-dim" />
                  <p className="text-[10px] font-semibold text-bfsi-text-dim uppercase tracking-wider">Investigation Coverage</p>
                  <span className="ml-auto text-[10px] text-bfsi-text-dim">
                    {[
                      plan.investigation_coverage.customer_history_checked,
                      plan.investigation_coverage.merchant_history_checked,
                      plan.investigation_coverage.duplicate_check_performed,
                      plan.investigation_coverage.related_cases_reviewed,
                    ].filter(Boolean).length} / 4 areas covered
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  {(
                    [
                      { key: "customer_history_checked",  label: "Customer History" },
                      { key: "merchant_history_checked",  label: "Merchant Risk"    },
                      { key: "duplicate_check_performed", label: "Duplicate Check"  },
                      { key: "related_cases_reviewed",    label: "Related Cases"    },
                    ] as const
                  ).map(({ key, label }) => {
                    const checked = plan.investigation_coverage?.[key];
                    return (
                      <div key={key} className={cn(
                        "flex flex-col items-center gap-1.5 p-2.5 rounded-lg border text-center",
                        checked
                          ? "text-green-400 bg-green-400/5 border-green-400/25"
                          : "text-bfsi-text-dim bg-bfsi-muted border-bfsi-border opacity-50"
                      )}>
                        {checked
                          ? <CheckCircle className="w-4 h-4" />
                          : <span className="w-4 h-4 rounded-full border border-current flex-shrink-0" />}
                        <span className="text-[10px] font-medium leading-tight">{label}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ── Key Investigation Findings ───────────────────────────────── */}
            {(plan.investigation_reasoning ?? []).length > 0 && (
              <div className="bfsi-card p-5">
                <div className="flex items-center gap-2 mb-4">
                  <Lightbulb className="w-4 h-4 text-bfsi-gold" />
                  <p className="section-header mb-0">Key Investigation Findings</p>
                </div>
                <ol className="space-y-2">
                  {(plan.investigation_reasoning ?? []).map((finding: string, i: number) => (
                    <li key={i} className="flex gap-3 text-xs text-bfsi-text-muted">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-bfsi-accent/20 text-bfsi-accent text-[10px] font-bold flex items-center justify-center border border-bfsi-accent/30">
                        {i + 1}
                      </span>
                      <span className="leading-relaxed pt-0.5">{finding}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {/* ── Change 2: Investigation Gaps with empty state ────────────── */}
            {(plan.investigation_gaps ?? []).length > 0 ? (
              <div className="bfsi-card p-5 border-amber-400/20">
                <div className="flex items-center gap-2 mb-3">
                  <AlertCircle className="w-4 h-4 text-amber-400" />
                  <p className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
                    Investigation Gaps ({(plan.investigation_gaps ?? []).length})
                  </p>
                </div>
                <ul className="space-y-2">
                  {(plan.investigation_gaps ?? []).map((gap: string, i: number) => (
                    <li key={i} className="flex items-start gap-2.5 text-xs text-amber-300/80">
                      <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                      {gap}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="bfsi-card p-4 border-green-400/20 bg-green-400/5 flex items-center gap-3">
                <CheckCircle className="w-4 h-4 text-green-400 flex-shrink-0" />
                <p className="text-xs text-green-400 font-medium">No investigation gaps identified — all areas have been covered.</p>
              </div>
            )}

            {/* ── Change 7: "Why This Plan?" collapsible panel ─────────────── */}
            {(plan.queue_confidence_factors ?? []).length > 0 && (
              <div className="bfsi-card overflow-hidden">
                <button
                  onClick={() => setWhyPlanOpen((v) => !v)}
                  className="w-full flex items-center justify-between p-4 hover:bg-bfsi-muted/40 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Lightbulb className="w-4 h-4 text-bfsi-gold" />
                    <span className="text-xs font-semibold text-bfsi-text uppercase tracking-wider">Why This Plan?</span>
                    <span className="text-[10px] text-bfsi-text-dim ml-1">Queue routing rationale from Agent 2</span>
                  </div>
                  {whyPlanOpen
                    ? <ChevronUp className="w-4 h-4 text-bfsi-text-dim" />
                    : <ChevronDown className="w-4 h-4 text-bfsi-text-dim" />}
                </button>
                {whyPlanOpen && (
                  <div className="px-4 pb-4 border-t border-bfsi-border">
                    <ul className="space-y-2 pt-3">
                      {(plan.queue_confidence_factors ?? []).map((f: string, i: number) => (
                        <li key={i} className="flex items-start gap-2.5 text-xs text-bfsi-text-muted leading-relaxed">
                          <span className="mt-1.5 w-1 h-1 rounded-full bg-bfsi-gold flex-shrink-0" />
                          {f}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* ── Risk Profiles grid ───────────────────────────────────────── */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <div className="bfsi-card p-5">
                <p className="section-header">Customer Risk Profile</p>
                <InfoRow label="Previous Disputes"    value={plan.customer_risk_profile?.previous_disputes ?? "—"} />
                <InfoRow label="Fraud Claims"         value={plan.customer_risk_profile?.fraud_claims ?? "—"} />
                <InfoRow label="Last Dispute (days)"  value={plan.customer_risk_profile?.last_dispute_days_ago ?? "—"} />
                <InfoRow label="Risk Level"           value={plan.customer_risk_profile?.risk_level} />
                {plan.customer_risk_profile?.assessment && (
                  <div className="mt-3 text-xs text-bfsi-text-muted bg-bfsi-muted rounded px-3 py-2 leading-relaxed">
                    {plan.customer_risk_profile.assessment}
                  </div>
                )}
              </div>

              <div className="bfsi-card p-5">
                <p className="section-header">Merchant Risk Profile</p>
                <InfoRow label="Merchant Risk"       value={plan.merchant_risk_profile?.merchant_risk} />
                <InfoRow label="Prior Complaints"    value={plan.merchant_risk_profile?.prior_complaints ?? "—"} />
                <InfoRow label="Fraud Rate"          value={plan.merchant_risk_profile?.fraud_rate != null ? `${(plan.merchant_risk_profile.fraud_rate * 100).toFixed(0)}%` : "—"} />
                {plan.merchant_risk_profile?.assessment && (
                  <div className="mt-3 text-xs text-bfsi-text-muted bg-bfsi-muted rounded px-3 py-2 leading-relaxed">
                    {plan.merchant_risk_profile.assessment}
                  </div>
                )}
              </div>

              <div className="bfsi-card p-5">
                <p className="section-header">Historical Precedent</p>
                <InfoRow label="Similar Cases"        value={plan.related_cases?.similar_cases ?? "—"} />
                <InfoRow label="Resolved in Favour"   value={plan.related_cases?.resolved_in_favor ?? "—"} />
                <InfoRow label="Resolved Against"     value={plan.related_cases?.resolved_against ?? "—"} />
                <InfoRow label="Resolution Rate"      value={plan.related_cases?.resolution_rate != null ? `${(plan.related_cases.resolution_rate * 100).toFixed(0)}%` : "—"} />
                {plan.duplicate_found && plan.related_case_id && (
                  <InfoRow label="Duplicate Of" value={plan.related_case_id} mono />
                )}
              </div>

              <div className="bfsi-card p-5">
                <div className="flex items-center gap-2 mb-4">
                  <ListChecks className="w-4 h-4 text-bfsi-gold" />
                  <p className="section-header mb-0">Recommended Steps</p>
                </div>
                {plan.recommended_steps?.length > 0 ? (
                  <ol className="space-y-2">
                    {plan.recommended_steps.map((step: string, i: number) => (
                      <li key={i} className="flex gap-3 text-xs text-bfsi-text-muted">
                        <span className="flex-shrink-0 w-5 h-5 rounded-full bg-bfsi-gold/20 text-bfsi-gold text-[10px] font-bold flex items-center justify-center">{i + 1}</span>
                        <span className="leading-relaxed pt-0.5">{step}</span>
                      </li>
                    ))}
                  </ol>
                ) : <p className="text-xs text-bfsi-text-dim">No steps available.</p>}
              </div>
            </div>

            {/* ── Data Quality Assessment ──────────────────────────────────── */}
            {(plan.data_quality_score != null || (plan.data_quality_factors ?? []).length > 0) && (
              <div className="bfsi-card p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <BarChart2 className="w-4 h-4 text-bfsi-gold" />
                    <p className="section-header mb-0">Data Quality Assessment</p>
                  </div>
                  {dqPct != null && (
                    <div className="flex items-center gap-2">
                      <span className={cn("text-xl font-mono font-bold", dqColor)}>{dqPct}%</span>
                      <span className="text-[10px] text-bfsi-text-dim">
                        {dqPct >= 90 ? "Excellent" : dqPct >= 75 ? "Good" : dqPct >= 60 ? "Moderate" : "Limited"}
                      </span>
                    </div>
                  )}
                </div>
                {(plan.data_quality_factors ?? []).length > 0 && (
                  <ul className="space-y-1.5">
                    {(plan.data_quality_factors ?? []).map((f: string, i: number) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-bfsi-text-muted">
                        <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-bfsi-text-dim flex-shrink-0" />
                        {f}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

          </div>
        );
      })()}

      {/* ── Evidence tab ──────────────────────────────────────────────────── */}
      {activeTab === "evidence" && (
        <div className="space-y-4">
          {uploads.length === 0 ? (
            <div className="bfsi-card p-10 text-center">
              <ImageIcon className="w-10 h-10 text-bfsi-text-dim mx-auto mb-3" />
              <p className="text-sm text-bfsi-text-dim">No evidence files uploaded for this case</p>
            </div>
          ) : (
            uploads.map((file) => (
              <div key={file.name} className="bfsi-card p-5">
                <div className="flex items-start gap-5">
                  {file.is_image ? (
                    <div
                      className="relative w-40 h-28 flex-shrink-0 rounded-lg overflow-hidden border border-bfsi-border cursor-pointer group"
                      onClick={() => setLightbox(`http://localhost:8000${file.url}`)}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={`http://localhost:8000${file.url}`} alt={file.name} className="w-full h-full object-cover" />
                      <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                        <ZoomIn className="w-6 h-6 text-white" />
                      </div>
                    </div>
                  ) : (
                    <div className="w-40 h-28 flex-shrink-0 rounded-lg border border-bfsi-border bg-bfsi-muted flex items-center justify-center">
                      <FileText className="w-8 h-8 text-bfsi-text-dim" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-bfsi-text mb-2 truncate">{file.name}</p>
                    <p className="text-xs text-bfsi-text-dim mt-1">
                      {file.is_image ? "Image" : "Document"} — text extracted and included in case analysis
                    </p>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* ── Lightbox ──────────────────────────────────────────────────────────── */}
      {lightbox && (
        <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4" onClick={() => setLightbox(null)}>
          <button className="absolute top-4 right-4 text-white hover:text-gray-300" onClick={() => setLightbox(null)}>
            <X className="w-7 h-7" />
          </button>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={lightbox} alt="Evidence" className="max-w-full max-h-[90vh] object-contain rounded-lg shadow-2xl" onClick={(e) => e.stopPropagation()} />
        </div>
      )}

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
                      {log.stage && (
                        <span className="text-[10px] text-bfsi-text-dim bg-bfsi-muted px-1.5 py-0.5 rounded">{log.stage}</span>
                      )}
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

      {activeTab === "workflow" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bfsi-card p-5">
            <p className="section-header">Workflow Stage</p>
            <WorkflowStatus status={caseData.status as CaseStatus} workflowReady={caseData.workflow_ready} />
          </div>
          <div className="bfsi-card p-5">
            <p className="section-header">LangGraph Node Execution</p>
            {workflowStates.length === 0 ? (
              <p className="text-sm text-bfsi-text-dim">No workflow state data available</p>
            ) : (
              <div className="space-y-2">
                {workflowStates.map((ws) => (
                  <div key={ws.id} className="flex items-center justify-between p-3 bg-bfsi-muted rounded-lg">
                    <div className="flex items-center gap-2">
                      {ws.success
                        ? <CheckCircle className="w-4 h-4 text-green-400" />
                        : <AlertTriangle className="w-4 h-4 text-red-400" />}
                      <span className="text-xs font-mono text-bfsi-text">{ws.node_name}</span>
                    </div>
                    {ws.execution_time_ms != null && (
                      <span className="text-[10px] text-bfsi-text-dim font-mono">
                        {ws.execution_time_ms.toFixed(0)}ms
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
