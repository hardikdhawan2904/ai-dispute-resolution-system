"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import toast from "react-hot-toast";
import {
  ArrowLeft, AlertTriangle, Brain, Shield, CreditCard,
  FileText, CheckCircle, Loader2, Activity,
} from "lucide-react";
import { cn, formatCurrency, formatDate, getPriorityColor, getStatusColor, formatConfidence } from "@/lib/utils";
import { getCase, getAuditLogs, getWorkflowStates, updateCaseStatus } from "@/lib/api";
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
  const [activeTab, setActiveTab]           = useState<"overview" | "ai" | "audit" | "workflow">("overview");
  const [liveUpdate, setLiveUpdate]         = useState(false);

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    Promise.all([getCase(caseId), getAuditLogs(caseId), getWorkflowStates(caseId)])
      .then(([c, a, w]) => {
        setCaseData(c);
        setAuditLogs(a.audit_logs);
        setWorkflowStates(w.workflow_states);
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
    { key: "overview", label: "Transaction", icon: CreditCard },
    { key: "ai",       label: "AI Analysis", icon: Brain },
    { key: "audit",    label: "Audit Trail", icon: FileText },
    { key: "workflow", label: "Workflow",     icon: Activity },
  ] as const;

  return (
    <>
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
            <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-3">AI Confidence Score</p>
            <ConfidenceScore score={caseData.confidence_score} size="lg" />
          </div>
        </div>
        {caseData.risk_tags?.length > 0 && (
          <div className="mt-4 pt-4 border-t border-bfsi-border">
            <p className="text-[10px] text-bfsi-text-dim uppercase tracking-wider mb-2">Risk Signals</p>
            <RiskTags tags={caseData.risk_tags} />
          </div>
        )}
      </div>

      {/* Status control */}
      <div className="bfsi-card p-4 mb-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Shield className="w-4 h-4 text-bfsi-gold" />
          <span className="text-sm text-bfsi-text-muted">Update investigation status:</span>
        </div>
        <div className="flex items-center gap-2">
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
            <p className="section-header">AI Classification</p>
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
          <div className="bfsi-card p-5 lg:col-span-2">
            <div className="flex items-center gap-2 mb-4">
              <Brain className="w-4 h-4 text-bfsi-gold" />
              <p className="section-header mb-0">AI Structured Reasoning</p>
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
