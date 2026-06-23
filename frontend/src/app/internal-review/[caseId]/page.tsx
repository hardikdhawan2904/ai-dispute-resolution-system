"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import toast from "react-hot-toast";
import {
  ArrowLeft, AlertTriangle, FileText, CheckCircle, Loader2,
  RefreshCw, X, ZoomIn, ChevronDown, ChevronUp,
} from "lucide-react";
import { cn, formatCurrency, formatDate, getPriorityColor } from "@/lib/utils";
import { getCase, getAuditLogs, getWorkflowStates, updateCaseStatus, reanalyseCase, getCaseUploads, createDocumentRequest, getCommunications, sendCommunication } from "@/lib/api";
import type { CommunicationLog } from "@/lib/api";
import type { CaseUploadFile } from "@/lib/api";
import type { DisputeCase, AuditLog, WorkflowState, CaseStatus, EvidenceAssessment } from "@/types";
import RiskTags from "@/components/dispute/RiskTags";
import WorkflowStatus from "@/components/dispute/WorkflowStatus";
import { useDisputeSocket, type DisputeSocketEvent } from "@/hooks/useDisputeSocket";

const CASE_STATUSES: CaseStatus[] = [
  "Dispute Raised", "Under Investigation", "Pending Documents",
  "Escalated", "Resolved", "Rejected", "Closed",
];

// Documents the bank/merchant obtains internally — never request from the customer.
// Mirrors backend services/document_rules.py BANK_OBTAINABLE set.
const BANK_OBTAINABLE = new Set([
  "Merchant order confirmation",
  "Payment gateway reference numbers",
  "CCTV request form (if applicable)",
  "Device or IP access logs",
  "OTP transaction logs",
  "Account activity report",
  "ATM reference number",
  "Merchant delivery confirmation",
  "Proof of transaction authorisation",
  "Any communication with customer",
  "Menu or price list at time of transaction",
  "KYC verification documents",
]);

// ── Helpers ──────────────────────────────────────────────────────────────────

function getReliabilityLabel(score: number): string {
  if (score >= 0.85) return "High Strength";
  if (score >= 0.70) return "Good Strength";
  if (score >= 0.55) return "Moderate Strength";
  if (score >= 0.40) return "Limited Strength";
  return "Low Strength";
}

function parseFindings(text: string): { bullets: string[]; conclusion: string } {
  if (!text) return { bullets: [], conclusion: "" };
  const lines = text.split(/\n+/).map(l => l.trim().replace(/^[-•*\d.]\s*/, "")).filter(l => l.length > 10);
  if (lines.length > 1) {
    const last = lines[lines.length - 1];
    const isConcl = /therefore|conclude|evidence support|recommend|overall|based on|in (summary|conclusion)/i.test(last);
    if (isConcl) return { bullets: lines.slice(0, -1), conclusion: last };
    return { bullets: lines, conclusion: "" };
  }
  const sentences = (text.match(/[^.!?]+[.!?]+/g) ?? [text]).map(s => s.trim()).filter(s => s.length > 15);
  if (sentences.length <= 1) return { bullets: [], conclusion: text };
  const last = sentences[sentences.length - 1];
  const isConcl = /therefore|conclude|evidence support|recommend|overall|based on|in (summary|conclusion)/i.test(last);
  if (isConcl) return { bullets: sentences.slice(0, -1), conclusion: last };
  return { bullets: sentences.slice(0, -1), conclusion: sentences[sentences.length - 1] };
}

// ── Primitives ────────────────────────────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">{children}</div>;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="text-[10.5px] font-bold uppercase tracking-wider text-slate-400 pb-2 border-b border-slate-700 mb-3">{children}</div>;
}

function InfoRow({ label, value, mono = false }: { label: string; value?: string | number | boolean | null; mono?: boolean }) {
  const display = value === true ? "Yes" : value === false ? "No" : (value ?? "—");
  return (
    <div className="grid grid-cols-[90px_1fr] gap-2 py-1.5 border-b border-[#1E293B]">
      <span className="text-[11px] text-slate-500 truncate">{label}</span>
      <span className={cn("text-[11.5px] text-slate-50 truncate min-w-0", mono && "font-mono")}>{String(display)}</span>
    </div>
  );
}


function Panel({ children, style, className, onClick }: { children: React.ReactNode; style?: React.CSSProperties; className?: string; onClick?: () => void }) {
  return (
    <div style={style} className={cn("ops-panel p-4", className)} onClick={onClick}>
      {children}
    </div>
  );
}

function CollapsibleSection({ title, open, onToggle, children }: {
  title: string; open: boolean; onToggle: () => void; children: React.ReactNode;
}) {
  return (
    <Panel className="p-3">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between bg-transparent border-none cursor-pointer p-0"
      >
        <span className={cn("text-[10.5px] font-bold uppercase tracking-wider", open ? "text-slate-400" : "text-slate-500")}>
          {title}
        </span>
        {open
          ? <ChevronUp className="w-3 h-3 text-slate-500" />
          : <ChevronDown className="w-3 h-3 text-slate-500" />
        }
      </button>
      {open && (
        <div className="mt-2.5 pt-2.5 border-t border-[#1E293B]">
          {children}
        </div>
      )}
    </Panel>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function CaseWorkspace() {
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
  const [activeTab, setActiveTab]           = useState<"analysis" | "fraud_review" | "investigation" | "evidence_review" | "evidence" | "audit" | "orchestration" | "advanced" | "communications">("analysis");
  const [communications, setCommunications] = useState<CommunicationLog[]>([]);
  const [expandedComm, setExpandedComm]     = useState<number | null>(null);
  const [showAdvanced, setShowAdvanced]     = useState(false);
  const [whyPlanOpen, setWhyPlanOpen]       = useState(false);
  const [liveUpdate, setLiveUpdate]         = useState(false);
  const [sidebarOpen, setSidebarOpen]       = useState<Record<string, boolean>>({
    summary: true, customer: false, transaction: false, dispute: false,
  });

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    Promise.all([getCase(caseId), getAuditLogs(caseId), getWorkflowStates(caseId), getCaseUploads(caseId), getCommunications(caseId).catch(() => ({ communications: [] }))])
      .then(([c, a, w, up, comms]) => { setCaseData(c); setAuditLogs(a.audit_logs); setWorkflowStates(w.workflow_states); setUploads(up); setCommunications(comms.communications || []); })
      .catch(() => { toast.error("Case not found"); router.push("/internal-review"); })
      .finally(() => setLoading(false));
  }, [caseId, router]);

  useEffect(() => {
    if (loading) {
      document.title = "Loading Case... | BFSI Dispute Resolution Platform";
    } else if (caseData) {
      document.title = `Case ${caseData.case_id} - ${caseData.customer_name || 'Investigation'} | BFSI Dispute Resolution Platform`;
    } else {
      document.title = "Case Not Found | BFSI Dispute Resolution Platform";
    }
  }, [loading, caseData]);

  // Navigate away from fraud tab only if no fraud data exists at all
  useEffect(() => {
    if (activeTab === "fraud_review" && caseData) {
      const path: string[] = (caseData.workflow_plan as any)?.workflow_path ?? [];
      const hasFraudData = path.includes("FRAUD_AGENT") || caseData.fraud_suspicion === true;
      if (!hasFraudData) setActiveTab("analysis");
    }
  }, [caseData, activeTab]);

  useDisputeSocket((event: DisputeSocketEvent) => {
    if (event.type === "ANALYSIS_COMPLETE" && event.case_id === caseId) {
      setCaseData(event.case as unknown as DisputeCase);
      setLiveUpdate(true);
      setTimeout(() => setLiveUpdate(false), 3000);
      // Refresh uploads so Evidence tab reflects newly submitted documents
      getCaseUploads(caseId).then(setUploads).catch(() => {});
    }
  });

  async function handleReanalyse() {
    if (!caseData || reanalysing) return;
    setReanalysing(true);
    setElapsed(0);
    const timer = setInterval(() => setElapsed(s => s + 1), 1000);
    try {
      const updated = await reanalyseCase(caseData.case_id);
      setCaseData(updated);
      toast.success("Re-analysis complete");
    } catch (err: unknown) {
      toast.error((err instanceof Error ? err.message : null) || "Re-analysis failed");
    } finally { clearInterval(timer); setReanalysing(false); }
  }

  async function handleStatusUpdate(newStatus: string) {
    if (!caseData || updatingStatus) return;
    setUpdatingStatus(true);
    try {
      const updated = await updateCaseStatus(caseData.case_id, newStatus);
      setCaseData(updated);
      toast.success(`Status → ${newStatus}`);
    } catch (err: unknown) {
      toast.error((err as Error).message || "Update failed");
    } finally { setUpdatingStatus(false); }
  }

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "4rem", gap: "0.75rem", color: "#64748B" }}>
      <Loader2 className="w-4 h-4 animate-spin" style={{ color: "#2563EB" }} />
      <span style={{ fontSize: "0.8rem" }}>Loading case…</span>
    </div>
  );
  if (!caseData) return null;

  const plan          = caseData.investigation_plan;
  const confidencePct = Math.round((caseData.confidence_score ?? 0) * 100);
  const confColor     = caseData.confidence_score >= 0.75 ? "#4ADE80" : caseData.confidence_score >= 0.55 ? "#FCD34D" : "#FCA5A5";
  const reliabilityLabel = getReliabilityLabel(caseData.confidence_score ?? 0);

  const { bullets: findingBullets, conclusion: findingConclusion } = parseFindings(caseData.structured_reasoning ?? "");

  const totalExecMs    = workflowStates.reduce((sum, ws) => sum + (ws.execution_time_ms ?? 0), 0);
  const execTimeSec    = totalExecMs > 0 ? (totalExecMs / 1000).toFixed(1) : null;
  const toolsUsed      = (caseData as any).tools_used ?? 0;
  const ariaVersion    = (caseData as any).agent_metadata?.agent_version ?? "ARIA v1.x";
  const iiaVersion     = (plan as any)?.agent_version ?? "IIA v1.x";

  const wfPlan = caseData.workflow_plan;

  const evidenceAssessment = caseData.evidence_assessment as EvidenceAssessment | null | undefined;

  // Show Fraud Review when WOA included FRAUD_AGENT, or when fraud data exists (e.g. reanalysis ran fraud agent outside WOA path)
  const showFraudTab = (wfPlan?.workflow_path ?? []).includes("FRAUD_AGENT")
    || caseData.fraud_suspicion === true;

  const tabs = [
    { key: "analysis",        label: "Case Analysis" },
    { key: "investigation",   label: "Investigation" },
    ...(showFraudTab ? [{ key: "fraud_review", label: "Fraud Review" }] : []),
    { key: "evidence_review", label: "Evidence Review" },
    { key: "orchestration",   label: "Case Coordination" },
    { key: "evidence",        label: `Evidence (${uploads.length})` },
    { key: "audit",           label: "Audit Trail" },
    { key: "communications",  label: `Communications (${communications.length})` },
    { key: "advanced",        label: "Advanced Diagnostics" },
  ] as const;

  return (
    <>
      {/* Re-analysis overlay */}
      {reanalysing && (
        <div style={{ position: "fixed", inset: 0, zIndex: 50, backgroundColor: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Panel style={{ maxWidth: 360, width: "100%", textAlign: "center" }}>
            <Loader2 className="w-8 h-8 animate-spin" style={{ color: "#2563EB", margin: "0 auto 1rem" }} />
            <p style={{ fontSize: "0.85rem", fontWeight: 600, color: "#F8FAFC", marginBottom: 4 }}>Re-analysing Case</p>
            <p style={{ fontSize: "0.72rem", color: "#64748B" }}>Running classification and investigation pipeline</p>
            <p style={{ fontSize: "0.65rem", color: "#475569", marginTop: "0.75rem", fontFamily: "ui-monospace, monospace" }}>{elapsed}s elapsed</p>
          </Panel>
        </div>
      )}

      {/* Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem", fontSize: "0.72rem", color: "#64748B" }}>
        <Link href="/internal-review" style={{ color: "#94A3B8", textDecoration: "none", display: "flex", alignItems: "center", gap: "0.25rem" }}>
          <ArrowLeft style={{ width: 13, height: 13 }} /> Case Queue
        </Link>
        <span>/</span>
        <span style={{ fontFamily: "ui-monospace, monospace", color: "#94A3B8" }}>{caseData.case_id}</span>
        {liveUpdate && <span style={{ marginLeft: 4, fontSize: "0.65rem", color: "#4ADE80", backgroundColor: "#052e16", border: "1px solid #166534", borderRadius: 3, padding: "0.1rem 0.5rem" }}>Updated</span>}
      </div>

      {/* Fallback warning */}
      {caseData.fallback_mode && (
        <div style={{ marginBottom: "1rem", padding: "0.75rem 1rem", backgroundColor: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: 4, display: "flex", alignItems: "flex-start", gap: "0.625rem" }}>
          <AlertTriangle style={{ width: 14, height: 14, color: "#B45309", flexShrink: 0, marginTop: 1 }} />
          <div>
            <p style={{ fontSize: "0.75rem", fontWeight: 600, color: "#92400E", marginBottom: 2 }}>Automated Processing Unavailable at Submission</p>
            <p style={{ fontSize: "0.7rem", color: "#92400E" }}>
              Classification service was unavailable when this case was submitted. Manual review is required before any resolution decision.
              <span style={{ marginLeft: 8, fontFamily: "ui-monospace, monospace", fontWeight: 600 }}>Reason: {caseData.failure_reason ?? "UNKNOWN"}</span>
            </p>
          </div>
        </div>
      )}

      {/* ── 3-Column workspace ─────────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "260px minmax(0,1fr) 220px", gap: "1rem", alignItems: "start", overflow: "hidden" }}>

        {/* ── LEFT PANEL — Collapsible metadata ──────────────────────────── */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>

          <CollapsibleSection
            title="Case Summary"
            open={sidebarOpen.summary}
            onToggle={() => setSidebarOpen(p => ({ ...p, summary: !p.summary }))}
          >
            <InfoRow label="Case Reference"  value={caseData.case_id} mono />
            <InfoRow label="Status"          value={caseData.status} />
            <InfoRow label="Priority"        value={caseData.priority} />
            <InfoRow label="Category"        value={caseData.dispute_category || "—"} />
            <InfoRow label="Filed On"        value={formatDate(caseData.created_at)} />
            <InfoRow label="Last Updated"    value={caseData.updated_at ? formatDate(caseData.updated_at) : "—"} />
            {caseData.assigned_queue && <InfoRow label="Assigned Queue" value={caseData.assigned_queue.replace(/_/g, " ")} />}
          </CollapsibleSection>

          <CollapsibleSection
            title="Customer Information"
            open={sidebarOpen.customer}
            onToggle={() => setSidebarOpen(p => ({ ...p, customer: !p.customer }))}
          >
            <InfoRow label="Full Name"    value={caseData.customer_name || "—"} />
            <InfoRow label="Customer ID"  value={caseData.customer_id} mono />
            <InfoRow label="Email"        value={caseData.email || "—"} />
            <InfoRow label="Phone"        value={caseData.phone || "—"} />
          </CollapsibleSection>

          <CollapsibleSection
            title="Transaction Information"
            open={sidebarOpen.transaction}
            onToggle={() => setSidebarOpen(p => ({ ...p, transaction: !p.transaction }))}
          >
            <InfoRow label="Transaction ID" value={caseData.transaction_id} mono />
            <InfoRow label="Type"           value={caseData.transaction_type} />
            <InfoRow label="Merchant"       value={caseData.merchant} />
            <InfoRow label="Amount"         value={formatCurrency(caseData.amount, caseData.currency)} />
            <InfoRow label="Date"           value={caseData.transaction_date || "—"} />
            <InfoRow label="Time"           value={caseData.transaction_time || "—"} />
          </CollapsibleSection>

          <CollapsibleSection
            title="Dispute Information"
            open={sidebarOpen.dispute}
            onToggle={() => setSidebarOpen(p => ({ ...p, dispute: !p.dispute }))}
          >
            <InfoRow label="Reason"        value={caseData.dispute_reason || "—"} />
            <InfoRow label="Fraud Claimed" value={caseData.fraud_selected} />
            <div style={{ paddingTop: "0.5rem" }}>
              <Label>Customer Statement</Label>
              <div style={{ fontSize: "0.72rem", color: "#94A3B8", lineHeight: 1.6, backgroundColor: "#111827", border: "1px solid #334155", borderRadius: 3, padding: "0.625rem 0.75rem" }}>
                {caseData.customer_comment || "—"}
              </div>
            </div>
          </CollapsibleSection>
        </div>

        {/* ── CENTER PANEL — Tabbed workspace ─────────────────────────────── */}
        <div>
          {/* Tab navigation */}
          <div style={{ display: "flex", borderBottom: "1px solid #334155", marginBottom: "1rem", overflowX: "auto" }}>
            {tabs.map(({ key, label }) => (
              <button key={key} onClick={() => setActiveTab(key as Parameters<typeof setActiveTab>[0])}
                style={{ fontSize: "0.75rem", fontWeight: activeTab === key ? 600 : 400, padding: "0.5rem 1rem", borderTop: "none", borderLeft: "none", borderRight: "none", borderBottom: activeTab === key ? "2px solid #2563EB" : "2px solid transparent", marginBottom: -1, color: activeTab === key ? "#F8FAFC" : "#64748B", background: "none", cursor: "pointer", whiteSpace: "nowrap", transition: "color 0.15s" }}>
                {label}
              </button>
            ))}
          </div>

          {/* ── Case Analysis tab ─────────────────────────────────────────── */}
          {activeTab === "analysis" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>

              {/* Classification */}
              <Panel>
                <SectionTitle>Classification</SectionTitle>
                <InfoRow label="Dispute Category"   value={caseData.dispute_category || "—"} />
                <InfoRow label="Fraud Indicator"    value={caseData.fraud_suspicion ? "Present" : "Not detected"} />
                <InfoRow label="Priority"           value={caseData.priority} />
                <InfoRow label="Evidence Verdict"   value={
                  (caseData as any).evidence_match === null ? "No documents submitted" :
                  (caseData as any).evidence_match === true ? "Documents support claim" : "Documents do not support claim"
                } />
              </Panel>

              {/* Evidence assessment */}
              {(caseData as any).evidence_match !== undefined && (
                <Panel>
                  <SectionTitle>Evidence Assessment</SectionTitle>
                  {(caseData as any).evidence_match === null ? (
                    <p style={{ fontSize: "0.75rem", color: "#64748B" }}>
                      {uploads.length > 0 ? "Document submitted — manual verification required." : "No documents were submitted with this dispute."}
                    </p>
                  ) : (caseData as any).evidence_match === true ? (
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "0.625rem", padding: "0.75rem", backgroundColor: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: 3 }}>
                      <CheckCircle style={{ width: 14, height: 14, color: "#15803D", flexShrink: 0, marginTop: 1 }} />
                      <div>
                        <p style={{ fontSize: "0.75rem", fontWeight: 600, color: "#166534", marginBottom: 2 }}>Documents Support Claim</p>
                        <p style={{ fontSize: "0.72rem", color: "#166534" }}>{(caseData as any).evidence_match_note || "Submitted documents corroborate the customer's dispute."}</p>
                      </div>
                    </div>
                  ) : (
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "0.625rem", padding: "0.75rem", backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 3 }}>
                      <AlertTriangle style={{ width: 14, height: 14, color: "#B91C1C", flexShrink: 0, marginTop: 1 }} />
                      <div>
                        <p style={{ fontSize: "0.75rem", fontWeight: 600, color: "#991B1B", marginBottom: 2 }}>Documents Do Not Support Claim</p>
                        <p style={{ fontSize: "0.72rem", color: "#991B1B" }}>{(caseData as any).evidence_match_note || "Submitted documents do not corroborate the dispute."}</p>
                      </div>
                    </div>
                  )}
                </Panel>
              )}

              {/* Key Findings — structured bullets + conclusion */}
              <Panel>
                <SectionTitle>Key Findings</SectionTitle>
                {findingBullets.length > 0 ? (
                  <ul style={{ display: "flex", flexDirection: "column", gap: "0.4rem", margin: 0, padding: 0, listStyle: "none", marginBottom: findingConclusion ? "0.75rem" : 0 }}>
                    {findingBullets.map((bullet, i) => (
                      <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.625rem", fontSize: "0.75rem", color: "#94A3B8", lineHeight: 1.55 }}>
                        <span style={{ flexShrink: 0, width: 5, height: 5, borderRadius: "50%", backgroundColor: "#2563EB", marginTop: 7 }} />
                        {bullet}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p style={{ fontSize: "0.75rem", color: "#94A3B8", lineHeight: 1.6, marginBottom: findingConclusion ? "0.75rem" : 0 }}>
                    {caseData.structured_reasoning || "No findings available."}
                  </p>
                )}
                {findingConclusion && (
                  <div style={{ borderTop: "1px solid #334155", paddingTop: "0.625rem" }}>
                    <div style={{ fontSize: "0.6rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "#475569", marginBottom: "0.375rem" }}>Conclusion</div>
                    <p style={{ fontSize: "0.75rem", color: "#CBD5E1", lineHeight: 1.55, fontWeight: 500 }}>{findingConclusion}</p>
                  </div>
                )}
                <p style={{ fontSize: "0.65rem", color: "#475569", marginTop: 10, borderTop: "1px solid #1E293B", paddingTop: 8 }}>For investigation reference only — not a legal or financial conclusion.</p>
              </Panel>

              {/* Case intent summary */}
              {caseData.customer_intent_summary && (
                <Panel>
                  <SectionTitle>Case Summary</SectionTitle>
                  <p style={{ fontSize: "0.75rem", color: "#94A3B8", lineHeight: 1.6 }}>{caseData.customer_intent_summary}</p>
                </Panel>
              )}

              {/* Risk indicators */}
              <Panel>
                <SectionTitle>Risk Indicators</SectionTitle>
                <RiskTags tags={caseData.risk_tags} />
              </Panel>

              {/* Required documents — smart pending view */}
              {(() => {
                const allDocs: string[] = caseData.investigation_plan?.required_documents ?? [];
                // Filter out passport doc unless transaction is genuinely International
                const isInternational = (caseData.transaction_type || "").toLowerCase() === "international";
                const docs: string[] = allDocs.filter((d: string) =>
                  !(d.toLowerCase().includes("passport") && !isInternational)
                );
                if (docs.length === 0) return null;

                // BANK_OBTAINABLE is defined at module level above

                const hasUploads = uploads.length > 0;

                const customerDocs = docs.filter(d => !BANK_OBTAINABLE.has(d));
                const bankDocs     = docs.filter(d => BANK_OBTAINABLE.has(d));

                // Only mark as many received as files actually uploaded
                const receivedCount = Math.min(uploads.length, customerDocs.length);
                const receivedDocs  = customerDocs.slice(0, receivedCount);
                const pendingCustomerDocs = customerDocs.slice(receivedCount);
                const pendingDocs   = [...pendingCustomerDocs, ...bankDocs];

                return (
                  <Panel>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
                      <SectionTitle>Required Documents</SectionTitle>
                      <div style={{ display: "flex", gap: "0.375rem" }}>
                        {receivedDocs.length > 0 && (
                          <span style={{ fontSize: "0.65rem", color: "#166534", backgroundColor: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: 3, padding: "0.1rem 0.5rem" }}>
                            {receivedDocs.length} received
                          </span>
                        )}
                        {(pendingCustomerDocs.length + bankDocs.length) > 0 && (
                          <span style={{ fontSize: "0.65rem", color: "#92400E", backgroundColor: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: 3, padding: "0.1rem 0.5rem" }}>
                            {pendingCustomerDocs.length + bankDocs.length} pending
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Received docs */}
                    {receivedDocs.length > 0 && (
                      <div style={{ marginBottom: "0.625rem" }}>
                        <div style={{ fontSize: "0.6rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "#166534", marginBottom: "0.375rem" }}>Received from Customer</div>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.375rem" }}>
                          {receivedDocs.map((doc, i) => (
                            <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.4rem 0.625rem", backgroundColor: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: 3 }}>
                              <CheckCircle style={{ width: 11, height: 11, color: "#15803D", flexShrink: 0 }} />
                              <span style={{ fontSize: "0.7rem", color: "#166534" }}>{doc}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Customer docs still needed */}
                    {pendingCustomerDocs.length > 0 && (
                      <div style={{ marginBottom: bankDocs.length > 0 ? "0.625rem" : 0 }}>
                        <div style={{ fontSize: "0.6rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "#1D4ED8", marginBottom: "0.375rem" }}>
                          {hasUploads ? "Still Required from Customer" : "Required from Customer"}
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.375rem" }}>
                          {pendingCustomerDocs.map((doc, i) => (
                            <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.4rem 0.625rem", backgroundColor: "#EFF6FF", border: "1px solid #BFDBFE", borderRadius: 3 }}>
                              <FileText style={{ width: 11, height: 11, color: "#2563EB", flexShrink: 0 }} />
                              <span style={{ fontSize: "0.7rem", color: "#1D4ED8" }}>{doc}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Bank / merchant obtainable docs */}
                    {bankDocs.length > 0 && (
                      <div>
                        <div style={{ fontSize: "0.6rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "#92400E", marginBottom: "0.375rem" }}>Pending — Bank to Obtain</div>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.375rem" }}>
                          {bankDocs.map((doc, i) => (
                            <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.4rem 0.625rem", backgroundColor: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: 3 }}>
                              <FileText style={{ width: 11, height: 11, color: "#B45309", flexShrink: 0 }} />
                              <span style={{ fontSize: "0.7rem", color: "#92400E" }}>{doc}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {pendingCustomerDocs.length === 0 && bankDocs.length === 0 && (
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.5rem 0.75rem", backgroundColor: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: 3 }}>
                        <CheckCircle style={{ width: 12, height: 12, color: "#15803D", flexShrink: 0 }} />
                        <span style={{ fontSize: "0.72rem", color: "#166534", fontWeight: 500 }}>All required documents received.</span>
                      </div>
                    )}

                    <p style={{ fontSize: "0.65rem", color: "#475569", marginTop: 8, borderTop: "1px solid #334155", paddingTop: 8 }}>
                      Requirements determined by dispute category, fraud indicators, and transaction value.
                    </p>
                  </Panel>
                );
              })()}
            </div>
          )}

          {/* ── Fraud Review tab (merged Fraud + Trust) ────────────────────── */}
          {activeTab === "fraud_review" && (() => {
            const fraudData = caseData.fraud_reasoning_brief;
            const trustData = caseData.trust_intelligence;

            if (!fraudData && !trustData) {
              return (
                <Panel style={{ padding: "3rem", textAlign: "center" }}>
                  <p style={{ fontSize: "0.8rem", color: "#64748B" }}>Fraud review not yet generated.</p>
                  <p style={{ fontSize: "0.72rem", color: "#475569", marginTop: 4 }}>Re-submit or re-analyse to trigger the fraud review agent.</p>
                </Panel>
              );
            }

            const fd = fraudData ?? {};
            const td = trustData ?? {};

            const fraudProbPct  = Math.round(((fd as any).fraud_probability ?? 0) * 100);
            const trustScorePct = Math.round(((td as any).user_trust_score  ?? 0) * 100);
            const behavRiskPct  = Math.round(((td as any).behavioral_risk_score ?? 0) * 100);

            const riskLevel  = (fd as any).fraud_risk_level ?? "LOW";
            const riskColor  = riskLevel === "CRITICAL" ? "#EF4444" : riskLevel === "HIGH" ? "#F97316" : riskLevel === "MEDIUM" ? "#FBBF24" : "#10B981";
            const riskBg     = riskLevel === "CRITICAL" ? "rgba(239,68,68,0.1)" : riskLevel === "HIGH" ? "rgba(249,115,22,0.1)" : riskLevel === "MEDIUM" ? "rgba(251,191,36,0.1)" : "rgba(16,185,129,0.1)";
            const riskBorder = riskLevel === "CRITICAL" ? "rgba(239,68,68,0.3)" : riskLevel === "HIGH" ? "rgba(249,115,22,0.3)" : riskLevel === "MEDIUM" ? "rgba(251,191,36,0.3)" : "rgba(16,185,129,0.3)";

            const trustColor = trustScorePct >= 80 ? "#4ADE80" : trustScorePct >= 50 ? "#FCD34D" : "#FCA5A5";
            const behavColor = behavRiskPct  >= 70 ? "#FCA5A5" : behavRiskPct  >= 40 ? "#FCD34D" : "#4ADE80";

            const idStatus      = (td as any).identity_verification ?? (fd as any).identity_verification ?? "PENDING";
            const idColor       = idStatus === "VERIFIED" ? "#4ADE80" : idStatus === "SUSPICIOUS" ? "#FCD34D" : "#FCA5A5";
            const idBg          = idStatus === "VERIFIED" ? "rgba(74,222,128,0.1)" : idStatus === "SUSPICIOUS" ? "rgba(252,211,77,0.1)" : "rgba(252,165,165,0.1)";
            const idBorder      = idStatus === "VERIFIED" ? "rgba(74,222,128,0.3)" : idStatus === "SUSPICIOUS" ? "rgba(252,211,77,0.3)" : "rgba(252,165,165,0.3)";

            const kycData      = (td as any).kyc_checks        ?? (fd as any).kyc_checks        ?? {};
            const devData      = (td as any).device_fingerprint ?? (fd as any).device_fingerprint ?? {};
            const behavData    = (td as any).dispute_behavior   ?? (fd as any).dispute_behavior   ?? {};
            const merchantRisk = (fd as any).merchant_risk      ?? {};
            const toolSignals  = (fd as any).tool_signals       ?? {};
            const channel      = (fd as any).channel            ?? "DIGITAL";

            const txnTypeLower      = (caseData.transaction_type || "").toLowerCase();
            const isUPI             = txnTypeLower.includes("upi");
            const isInternetBanking = ["net banking","internet banking","mobile banking","imps","neft","rtgs"].some(t => txnTypeLower.includes(t));
            const isDigital         = isUPI || isInternetBanking;
            const isCardPOS         = ["debit card","credit card"].some(t => txnTypeLower.includes(t)) && !txnTypeLower.includes("atm");
            const isATM             = txnTypeLower.includes("atm") || txnTypeLower.includes("cash withdrawal");

            const channelLabel = isCardPOS ? "Card POS" : isATM ? "ATM" : "UPI / Mobile / Internet";
            const channelColor = isCardPOS ? "#7C3AED" : isATM ? "#D97706" : "#2563EB";
            const channelBg    = isCardPOS ? "rgba(124,58,237,0.1)" : isATM ? "rgba(217,119,6,0.1)" : "rgba(37,99,235,0.1)";

            const mrLevel = merchantRisk.merchant_risk_level ?? "LOW";
            const mrColor = mrLevel === "CRITICAL" ? "#EF4444" : mrLevel === "HIGH" ? "#F97316" : mrLevel === "MEDIUM" ? "#FBBF24" : "#10B981";

            return (
              <div className="flex flex-col gap-3.5">

                {/* ── Header: Fraud Summary ─────────────────────────────── */}
                <Panel style={{ borderLeft: `4px solid ${riskColor}`, padding: "1.25rem" }}>
                  <div className="flex justify-between items-start flex-wrap gap-4 mb-3">
                    <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
                      <h3 style={{ fontSize: "1rem", fontWeight: 700, color: "#F8FAFC", margin: 0 }}>Fraud Review</h3>
                      <span style={{ fontSize: "0.6rem", fontWeight: 700, padding: "0.2rem 0.6rem", borderRadius: 20, backgroundColor: channelBg, color: channelColor, border: `1px solid ${channelColor}40` }}>
                        {channelLabel}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      {caseData.requires_manual_review ? (
                        <div style={{ backgroundColor: "rgba(251,191,36,0.1)", border: "1px solid rgba(251,191,36,0.3)" }} className="flex items-center gap-1.5 px-3 py-1.5 rounded">
                          <AlertTriangle style={{ width: 12, height: 12, color: "#FBBF24" }} />
                          <span style={{ color: "#FBBF24" }} className="text-xs font-bold tracking-wide">HUMAN REVIEW REQUIRED</span>
                        </div>
                      ) : (
                        <div style={{ backgroundColor: "rgba(74,222,128,0.1)", border: "1px solid rgba(74,222,128,0.3)" }} className="flex items-center gap-1.5 px-3 py-1.5 rounded">
                          <CheckCircle style={{ width: 12, height: 12, color: "#4ADE80" }} />
                          <span style={{ color: "#4ADE80" }} className="text-xs font-bold tracking-wide">NO HUMAN REVIEW NEEDED</span>
                        </div>
                      )}
                      <div style={{ backgroundColor: riskBg, border: `1px solid ${riskBorder}` }} className="flex items-center gap-2 px-3 py-1.5 rounded">
                        <AlertTriangle style={{ width: 13, height: 13, color: riskColor }} />
                        <span style={{ color: riskColor }} className="text-xs font-bold tracking-wide">FRAUD RISK: {riskLevel}</span>
                      </div>
                    </div>
                  </div>
                  <p style={{ fontSize: "0.75rem", color: "#94A3B8", lineHeight: 1.6, margin: 0 }}>
                    {(fd as any).fraud_summary || "No fraud summary available."}
                  </p>
                </Panel>

                {/* ── Score Row ─────────────────────────────────────────── */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.875rem" }}>
                  {/* Fraud Probability */}
                  <Panel>
                    <Label>Fraud Probability</Label>
                    <div style={{ fontSize: "1.5rem", fontWeight: 700, fontFamily: "ui-monospace, monospace", color: riskColor, lineHeight: 1 }}>{fraudProbPct}%</div>
                    <div style={{ height: 4, backgroundColor: "#334155", borderRadius: 2, overflow: "hidden", marginTop: 6 }}>
                      <div style={{ height: "100%", width: `${fraudProbPct}%`, backgroundColor: riskColor, borderRadius: 2 }} />
                    </div>
                  </Panel>
                  {/* Trust Score */}
                  <Panel>
                    <Label>Trust Score</Label>
                    <div style={{ fontSize: "1.5rem", fontWeight: 700, fontFamily: "ui-monospace, monospace", color: trustColor, lineHeight: 1 }}>{trustScorePct}%</div>
                    <div style={{ height: 4, backgroundColor: "#334155", borderRadius: 2, overflow: "hidden", marginTop: 6 }}>
                      <div style={{ height: "100%", width: `${trustScorePct}%`, backgroundColor: trustColor, borderRadius: 2 }} />
                    </div>
                  </Panel>
                  {/* Behavioral Risk */}
                  <Panel>
                    <Label>Behavioral Risk</Label>
                    <div style={{ fontSize: "1.5rem", fontWeight: 700, fontFamily: "ui-monospace, monospace", color: behavColor, lineHeight: 1 }}>
                      {behavRiskPct >= 70 ? "HIGH" : behavRiskPct >= 40 ? "MEDIUM" : "LOW"}
                    </div>
                    <div style={{ height: 4, backgroundColor: "#334155", borderRadius: 2, overflow: "hidden", marginTop: 6 }}>
                      <div style={{ height: "100%", width: `${behavRiskPct}%`, backgroundColor: behavColor, borderRadius: 2 }} />
                    </div>
                  </Panel>
                  {/* Identity Status */}
                  <Panel>
                    <Label>Identity Status</Label>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginTop: 2 }}>
                      <div style={{ padding: "0.25rem 0.625rem", backgroundColor: idBg, border: `1px solid ${idBorder}`, borderRadius: 3, display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                        {idStatus === "VERIFIED"
                          ? <CheckCircle style={{ width: 12, height: 12, color: idColor }} />
                          : <AlertTriangle style={{ width: 12, height: 12, color: idColor }} />}
                        <span style={{ fontSize: "0.72rem", fontWeight: 700, color: idColor }}>{idStatus}</span>
                      </div>
                    </div>
                  </Panel>
                </div>

                {/* ── Merchant Risk (all channels) ─────────────────────── */}
                <Panel>
                  <SectionTitle>Merchant Risk Intelligence</SectionTitle>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.875rem" }}>
                    <div>
                      <Label>Merchant Risk Level</Label>
                      <span style={{ fontSize: "0.72rem", fontWeight: 700, padding: "0.2rem 0.6rem", borderRadius: 3,
                        backgroundColor: `${mrColor}18`, color: mrColor, border: `1px solid ${mrColor}40` }}>
                        {mrLevel}
                      </span>
                    </div>
                    <div>
                      <Label>Blacklisted</Label>
                      <span style={{ fontSize: "0.72rem", fontWeight: 700, color: merchantRisk.merchant_blacklisted ? "#EF4444" : "#4ADE80" }}>
                        {merchantRisk.merchant_blacklisted ? "YES — BLOCKED" : "No"}
                      </span>
                    </div>
                    <div>
                      <Label>Data Source</Label>
                      <span style={{ fontSize: "0.72rem", color: "#94A3B8" }}>Bank Merchant Profiles</span>
                    </div>
                  </div>
                </Panel>

                {/* ── Channel-specific signal cards ────────────────────── */}
                {isCardPOS && (
                  <Panel>
                    <SectionTitle>Card POS Signals</SectionTitle>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.875rem" }}>
                      {[
                        { label: "Card Velocity Breach", flag: toolSignals.card_velocity_breach, desc: "3+ transactions in 5 min" },
                        { label: "ATM-POS Impossible Travel", flag: toolSignals.atm_pos_impossible_travel, desc: "Different city ATM + POS within 1h" },
                        { label: "Foreign Card Usage", flag: toolSignals.foreign_usage, desc: "International use on domestic card" },
                      ].map(({ label, flag, desc }) => (
                        <div key={label} style={{ padding: "0.625rem", backgroundColor: flag ? "rgba(239,68,68,0.07)" : "#0F172A", border: `1px solid ${flag ? "rgba(239,68,68,0.3)" : "#334155"}`, borderRadius: 6 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", marginBottom: 4 }}>
                            {flag
                              ? <AlertTriangle style={{ width: 12, height: 12, color: "#EF4444" }} />
                              : <CheckCircle style={{ width: 12, height: 12, color: "#4ADE80" }} />}
                            <span style={{ fontSize: "0.68rem", fontWeight: 600, color: flag ? "#FCA5A5" : "#4ADE80" }}>
                              {flag ? "ALERT" : "Clear"}
                            </span>
                          </div>
                          <div style={{ fontSize: "0.7rem", color: "#F8FAFC", fontWeight: 500 }}>{label}</div>
                          <div style={{ fontSize: "0.62rem", color: "#64748B", marginTop: 2 }}>{desc}</div>
                        </div>
                      ))}
                    </div>
                  </Panel>
                )}

                {/* ── Card Fraud Intelligence (Card POS only) ──────────── */}
                {isCardPOS && (() => {
                  const rows = [
                    { label: "Merchant Compromise Risk",      value: toolSignals.merchant_compromise_level ?? "LOW",    flag: toolSignals.merchant_compromise_level === "HIGH" || toolSignals.merchant_compromise_level === "CRITICAL", desc: "Abnormal dispute spike at this merchant in last 7 days" },
                    { label: "First-Time High-Value Merchant", value: toolSignals.first_time_high_value ? "Detected" : "Clear",   flag: !!toolSignals.first_time_high_value, desc: "Customer has never transacted here before at this amount" },
                    { label: "Merchant Favor Rate",           value: toolSignals.merchant_favor_rate != null ? `${toolSignals.merchant_favor_rate}%` : "N/A", flag: (toolSignals.merchant_favor_rate ?? 0) > 70, desc: "Rate at which disputes at this merchant are resolved for customers" },
                    { label: "Card Testing Pattern",          value: toolSignals.card_testing_detected ? "Detected" : "Clear",    flag: !!toolSignals.card_testing_detected, desc: "Multiple micro-transactions (≤₹50) before main transaction" },
                    { label: "Merchant Burst (Multi-Hop)",   value: toolSignals.merchant_burst_detected ? "Detected" : "Clear",  flag: !!toolSignals.merchant_burst_detected, desc: "4+ different merchants within 30 minutes" },
                    { label: "Merchant Category Risk",        value: toolSignals.mcc_risk_level ?? "LOW",                        flag: toolSignals.mcc_risk_level === "HIGH" || toolSignals.mcc_risk_level === "CRITICAL", desc: "Risk level of this merchant's business category" },
                    { label: "Decline-Then-Success Pattern", value: toolSignals.decline_success_pattern ? "Detected" : "Clear",  flag: !!toolSignals.decline_success_pattern, desc: "Multiple declined attempts before successful authorization" },
                    { label: "Refund Claim Verified",         value: toolSignals.refund_claim_unverified ? "Unverified" : "Verified", flag: !!toolSignals.refund_claim_unverified, desc: "Checks if corresponding reversal transaction exists" },
                  ];
                  const visible = rows.filter(r => r.flag);
                  if (visible.length === 0) return null;
                  return (
                    <Panel>
                      <SectionTitle>Card Fraud Intelligence</SectionTitle>
                      <div style={{ display: "flex", flexDirection: "column" }}>
                        {visible.map(({ label, value, flag, desc }) => (
                          <div key={label} style={{ display: "flex", flexDirection: "column", padding: "0.5rem 0", borderBottom: "1px solid #1E293B" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span style={{ fontSize: "0.7rem", color: "#64748B" }}>{label}</span>
                              <span style={{ fontSize: "0.68rem", fontWeight: 600, padding: "1px 8px", borderRadius: 3, backgroundColor: flag ? "rgba(239,68,68,0.1)" : "rgba(74,222,128,0.1)", color: flag ? "#FCA5A5" : "#4ADE80", border: `1px solid ${flag ? "rgba(239,68,68,0.3)" : "rgba(74,222,128,0.3)"}` }}>{value}</span>
                            </div>
                            <span style={{ fontSize: "0.62rem", color: "#334155", marginTop: 2 }}>{desc}</span>
                          </div>
                        ))}
                      </div>
                    </Panel>
                  );
                })()}

                {isATM && (
                  <Panel>
                    <SectionTitle>ATM Signals</SectionTitle>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.875rem" }}>
                      {[
                        { label: "ATM Velocity Breach", flag: toolSignals.atm_velocity_breach, desc: "3+ withdrawals in 1 hour" },
                        { label: "ATM Geovelocity Breach", flag: toolSignals.atm_geo_breach, desc: "Impossible ATM-to-ATM travel" },
                        { label: "Cash Withdrawal Anomaly", flag: toolSignals.cash_withdrawal_anomaly, desc: "Unusually large or repeated" },
                      ].map(({ label, flag, desc }) => (
                        <div key={label} style={{ padding: "0.625rem", backgroundColor: flag ? "rgba(239,68,68,0.07)" : "#0F172A", border: `1px solid ${flag ? "rgba(239,68,68,0.3)" : "#334155"}`, borderRadius: 6 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", marginBottom: 4 }}>
                            {flag
                              ? <AlertTriangle style={{ width: 12, height: 12, color: "#EF4444" }} />
                              : <CheckCircle style={{ width: 12, height: 12, color: "#4ADE80" }} />}
                            <span style={{ fontSize: "0.68rem", fontWeight: 600, color: flag ? "#FCA5A5" : "#4ADE80" }}>
                              {flag ? "ALERT" : "Clear"}
                            </span>
                          </div>
                          <div style={{ fontSize: "0.7rem", color: "#F8FAFC", fontWeight: 500 }}>{label}</div>
                          <div style={{ fontSize: "0.62rem", color: "#64748B", marginTop: 2 }}>{desc}</div>
                        </div>
                      ))}
                    </div>
                  </Panel>
                )}

                {/* ── UPI Fraud Intelligence ───────────────────────────── */}
                {isUPI && (() => {
                  const rows = [
                    { label: "New Beneficiary Risk",    value: toolSignals.new_beneficiary_risk ? "Detected" : "Clear",  flag: !!toolSignals.new_beneficiary_risk,  desc: "Large transfer to a first-time beneficiary" },
                    { label: "UPI Collect Request",     value: toolSignals.upi_collect_fraud    ? "Detected" : "Clear",  flag: !!toolSignals.upi_collect_fraud,     desc: "Customer approved a fraudulent collect request" },
                    { label: "Beneficiary Velocity",    value: toolSignals.beneficiary_vel_flag ? "Detected" : "Clear",  flag: !!toolSignals.beneficiary_vel_flag,  desc: "Multiple customers sending to this beneficiary" },
                    { label: "UPI Handle Reputation",   value: toolSignals.upi_handle_reputation ?? "LOW_RISK",          flag: toolSignals.upi_handle_reputation === "HIGH_RISK", desc: "Beneficiary appears in fraud dispute history" },
                    { label: "Dormant Beneficiary",     value: toolSignals.dormant_beneficiary  ? "Detected" : "Clear",  flag: !!toolSignals.dormant_beneficiary,   desc: "Beneficiary registered very recently before transfer" },
                  ];
                  const visible = rows.filter(r => r.flag);
                  if (visible.length === 0) return null;
                  return (
                    <Panel>
                      <SectionTitle>UPI Fraud Intelligence</SectionTitle>
                      <div style={{ display: "flex", flexDirection: "column" }}>
                        {visible.map(({ label, value, desc }) => (
                          <div key={label} style={{ display: "flex", flexDirection: "column", padding: "0.5rem 0", borderBottom: "1px solid #1E293B" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span style={{ fontSize: "0.7rem", color: "#64748B" }}>{label}</span>
                              <span style={{ fontSize: "0.68rem", fontWeight: 600, padding: "1px 8px", borderRadius: 3, backgroundColor: "rgba(239,68,68,0.1)", color: "#FCA5A5", border: "1px solid rgba(239,68,68,0.3)" }}>{value}</span>
                            </div>
                            <span style={{ fontSize: "0.62rem", color: "#334155", marginTop: 2 }}>{desc}</span>
                          </div>
                        ))}
                      </div>
                    </Panel>
                  );
                })()}

                {/* ── Internet Banking Intelligence ─────────────────────── */}
                {isInternetBanking && (() => {
                  const rows = [
                    { label: "Impossible Login Travel",        value: toolSignals.impossible_login_travel  ? "Detected" : "Clear", flag: !!toolSignals.impossible_login_travel,  desc: "Login from different city within 2 hours" },
                    { label: "Device Change + Large Transfer", value: toolSignals.device_change_transfer   ? "Detected" : "Clear", flag: !!toolSignals.device_change_transfer,   desc: "Large transfer immediately after new device login" },
                    { label: "Password Reset Pattern",         value: toolSignals.pwd_reset_pattern        ? "Detected" : "Clear", flag: !!toolSignals.pwd_reset_pattern,         desc: "Transfer made shortly after password reset" },
                    { label: "Mobile Number Change Risk",      value: toolSignals.mobile_change_risk       ? "Detected" : "Clear", flag: !!toolSignals.mobile_change_risk,        desc: "Mobile number changed before this transaction" },
                  ];
                  const visible = rows.filter(r => r.flag);
                  if (visible.length === 0) return null;
                  return (
                    <Panel>
                      <SectionTitle>Internet Banking Intelligence</SectionTitle>
                      <div style={{ display: "flex", flexDirection: "column" }}>
                        {visible.map(({ label, value, desc }) => (
                          <div key={label} style={{ display: "flex", flexDirection: "column", padding: "0.5rem 0", borderBottom: "1px solid #1E293B" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span style={{ fontSize: "0.7rem", color: "#64748B" }}>{label}</span>
                              <span style={{ fontSize: "0.68rem", fontWeight: 600, padding: "1px 8px", borderRadius: 3, backgroundColor: "rgba(239,68,68,0.1)", color: "#FCA5A5", border: "1px solid rgba(239,68,68,0.3)" }}>{value}</span>
                            </div>
                            <span style={{ fontSize: "0.62rem", color: "#334155", marginTop: 2 }}>{desc}</span>
                          </div>
                        ))}
                      </div>
                    </Panel>
                  );
                })()}

                {/* ── ATM Advanced Intelligence ─────────────────────────── */}
                {isATM && (() => {
                  const rows = [
                    { label: "Consecutive ATM Withdrawals", value: toolSignals.consecutive_atm  ? "Detected" : "Clear", flag: !!toolSignals.consecutive_atm,  desc: "3+ withdrawals in short intervals — possible card cloning" },
                    { label: "Foreign ATM Usage",           value: toolSignals.foreign_atm_usage ? "Detected" : "Clear", flag: !!toolSignals.foreign_atm_usage, desc: "ATM used abroad by primarily domestic customer" },
                    { label: "SIM Swap + ATM Pattern",      value: toolSignals.sim_swap_atm      ? "Detected" : "Clear", flag: !!toolSignals.sim_swap_atm,      desc: "ATM withdrawal after SIM swap — strongest ATM fraud signal" },
                  ];
                  const visible = rows.filter(r => r.flag);
                  if (visible.length === 0) return null;
                  return (
                    <Panel>
                      <SectionTitle>ATM Fraud Intelligence</SectionTitle>
                      <div style={{ display: "flex", flexDirection: "column" }}>
                        {visible.map(({ label, value, desc }) => (
                          <div key={label} style={{ display: "flex", flexDirection: "column", padding: "0.5rem 0", borderBottom: "1px solid #1E293B" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span style={{ fontSize: "0.7rem", color: "#64748B" }}>{label}</span>
                              <span style={{ fontSize: "0.68rem", fontWeight: 600, padding: "1px 8px", borderRadius: 3, backgroundColor: "rgba(239,68,68,0.1)", color: "#FCA5A5", border: "1px solid rgba(239,68,68,0.3)" }}>{value}</span>
                            </div>
                            <span style={{ fontSize: "0.62rem", color: "#334155", marginTop: 2 }}>{desc}</span>
                          </div>
                        ))}
                      </div>
                    </Panel>
                  );
                })()}

                {/* ── Universal Fraud Intelligence ──────────────────────── */}
                {(() => {
                  const rows = [
                    { label: "Prior Fraud Victim",       value: toolSignals.prior_fraud_victim ? "Detected" : "Clear", flag: !!toolSignals.prior_fraud_victim, desc: "Customer has been a fraud victim before — repeat targeting risk" },
                    { label: "Account Takeover Risk",    value: toolSignals.ato_risk_level ?? "LOW",                   flag: toolSignals.ato_risk_level === "HIGH" || toolSignals.ato_risk_level === "CRITICAL", desc: "Password reset + device change + SIM swap combination" },
                    { label: "Mule Account Suspected",   value: toolSignals.mule_suspected ? "Detected" : "Clear",    flag: !!toolSignals.mule_suspected,    desc: "Rapid fund pass-through pattern — possible money mule" },
                    { label: "Historical Case Similarity", value: toolSignals.case_similarity_high ? "Detected" : "Clear", flag: !!toolSignals.case_similarity_high, desc: "Current fraud pattern matches known historical fraud cases" },
                  ];
                  const visible = rows.filter(r => r.flag);
                  if (visible.length === 0) return null;
                  return (
                    <Panel>
                      <SectionTitle>Universal Fraud Intelligence</SectionTitle>
                      <div style={{ display: "flex", flexDirection: "column" }}>
                        {visible.map(({ label, value, desc }) => (
                          <div key={label} style={{ display: "flex", flexDirection: "column", padding: "0.5rem 0", borderBottom: "1px solid #1E293B" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <span style={{ fontSize: "0.7rem", color: "#64748B" }}>{label}</span>
                              <span style={{ fontSize: "0.68rem", fontWeight: 600, padding: "1px 8px", borderRadius: 3, backgroundColor: "rgba(239,68,68,0.1)", color: "#FCA5A5", border: "1px solid rgba(239,68,68,0.3)" }}>{value}</span>
                            </div>
                            <span style={{ fontSize: "0.62rem", color: "#334155", marginTop: 2 }}>{desc}</span>
                          </div>
                        ))}
                      </div>
                    </Panel>
                  );
                })()}

                {/* ── Identity Verification + Device + Behavioral ───────── */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.875rem" }}>

                  {/* KYC Match — only shown for digital channels where KYC tool runs */}
                  <Panel>
                    <SectionTitle>Identity Verification</SectionTitle>
                    {(isCardPOS || isATM) ? (
                      <div style={{ padding: "0.75rem 0", textAlign: "center" }}>
                        <div style={{ fontSize: "0.72rem", color: "#475569", marginBottom: 4 }}>Not applicable</div>
                        <div style={{ fontSize: "0.65rem", color: "#334155" }}>
                          KYC verification is not performed for {isATM ? "ATM" : "Card POS"} transactions — no customer device data available.
                        </div>
                      </div>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column" }}>
                        {[
                          { label: "KYC Match — Name",    ok: kycData.name_match },
                          { label: "KYC Match — Contact", ok: kycData.contact_match },
                        ].map(({ label, ok }) => (
                          <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.4rem 0", borderBottom: "1px solid #1E293B" }}>
                            <span style={{ fontSize: "0.7rem", color: "#64748B" }}>{label}</span>
                            {ok ? (
                              <span style={{ fontSize: "0.68rem", fontWeight: 600, color: "#4ADE80", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                                <CheckCircle style={{ width: 12, height: 12 }} /> Match
                              </span>
                            ) : (
                              <span style={{ fontSize: "0.68rem", fontWeight: 600, color: "#FCA5A5", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                                <AlertTriangle style={{ width: 12, height: 12 }} /> Mismatch
                              </span>
                            )}
                          </div>
                        ))}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.4rem 0" }}>
                          <span style={{ fontSize: "0.7rem", color: "#64748B" }}>Customer Since</span>
                          <span style={{ fontSize: "0.72rem", color: "#F8FAFC", fontFamily: "ui-monospace, monospace" }}>{kycData.join_date || "—"}</span>
                        </div>
                      </div>
                    )}
                  </Panel>

                  {/* Device Fingerprint + Location — only relevant for digital channels */}
                  {(isDigital) && <Panel>
                    <SectionTitle>Device &amp; Location</SectionTitle>
                    <div style={{ display: "flex", flexDirection: "column" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.4rem 0", borderBottom: "1px solid #1E293B" }}>
                        <span style={{ fontSize: "0.7rem", color: "#64748B" }}>Device Fingerprint</span>
                        {devData.recognized_device ? (
                          <span style={{ fontSize: "0.68rem", fontWeight: 600, color: "#4ADE80", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                            <CheckCircle style={{ width: 12, height: 12 }} /> Recognized
                          </span>
                        ) : (
                          <span style={{ fontSize: "0.68rem", fontWeight: 600, color: "#FCD34D", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                            <AlertTriangle style={{ width: 12, height: 12 }} /> New Device
                          </span>
                        )}
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.4rem 0", borderBottom: "1px solid #1E293B" }}>
                        <span style={{ fontSize: "0.7rem", color: "#64748B" }}>Location Familiarity</span>
                        {devData.location_consistent ? (
                          <span style={{ fontSize: "0.68rem", fontWeight: 600, color: "#4ADE80", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                            <CheckCircle style={{ width: 12, height: 12 }} /> Familiar
                          </span>
                        ) : (
                          <span style={{ fontSize: "0.68rem", fontWeight: 600, color: "#FCA5A5", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                            <AlertTriangle style={{ width: 12, height: 12 }} /> Unfamiliar
                          </span>
                        )}
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.4rem 0" }}>
                        <span style={{ fontSize: "0.7rem", color: "#64748B" }}>Device Risk</span>
                        <span style={{
                          fontSize: "0.65rem", fontWeight: 700, padding: "0.1rem 0.4rem", borderRadius: 3,
                          backgroundColor: devData.device_risk === "HIGH" ? "rgba(252,165,165,0.1)" : devData.device_risk === "MEDIUM" ? "rgba(252,211,77,0.1)" : "rgba(74,222,128,0.1)",
                          color: devData.device_risk === "HIGH" ? "#FCA5A5" : devData.device_risk === "MEDIUM" ? "#FCD34D" : "#4ADE80",
                          border: `1px solid ${devData.device_risk === "HIGH" ? "rgba(252,165,165,0.3)" : devData.device_risk === "MEDIUM" ? "rgba(252,211,77,0.3)" : "rgba(74,222,128,0.3)"}`
                        }}>
                          {devData.device_risk || "LOW"}
                        </span>
                      </div>
                    </div>
                  </Panel>}

                  {/* Behavioral Analysis */}
                  <Panel>
                    <SectionTitle>Behavioral Analysis</SectionTitle>
                    <div style={{ display: "flex", flexDirection: "column" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.4rem 0", borderBottom: "1px solid #1E293B" }}>
                        <span style={{ fontSize: "0.7rem", color: "#64748B" }}>Prior Disputes</span>
                        <span style={{ fontSize: "0.72rem", fontWeight: 600, color: (behavData.prior_dispute_count ?? 0) >= 3 ? "#FCA5A5" : "#F8FAFC" }}>
                          {behavData.prior_dispute_count ?? 0}
                        </span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.4rem 0", borderBottom: "1px solid #1E293B" }}>
                        <span style={{ fontSize: "0.7rem", color: "#64748B" }}>Velocity Breaches</span>
                        {behavData.velocity_breach_detected ? (
                          <span style={{ fontSize: "0.68rem", fontWeight: 600, color: "#FCA5A5", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                            <AlertTriangle style={{ width: 12, height: 12 }} /> Detected
                          </span>
                        ) : (
                          <span style={{ fontSize: "0.68rem", fontWeight: 600, color: "#4ADE80", display: "flex", alignItems: "center", gap: "0.25rem" }}>
                            <CheckCircle style={{ width: 12, height: 12 }} /> None
                          </span>
                        )}
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "0.4rem 0" }}>
                        <span style={{ fontSize: "0.7rem", color: "#64748B" }}>Friendly Fraud Indicators</span>
                        <span style={{
                          fontSize: "0.65rem", fontWeight: 700, padding: "0.1rem 0.4rem", borderRadius: 3,
                          backgroundColor: behavData.friendly_fraud_risk === "HIGH" ? "rgba(252,165,165,0.1)" : behavData.friendly_fraud_risk === "MEDIUM" ? "rgba(252,211,77,0.1)" : "rgba(74,222,128,0.1)",
                          color: behavData.friendly_fraud_risk === "HIGH" ? "#FCA5A5" : behavData.friendly_fraud_risk === "MEDIUM" ? "#FCD34D" : "#4ADE80",
                          border: `1px solid ${behavData.friendly_fraud_risk === "HIGH" ? "rgba(252,165,165,0.3)" : behavData.friendly_fraud_risk === "MEDIUM" ? "rgba(252,211,77,0.3)" : "rgba(74,222,128,0.3)"}`
                        }}>
                          {behavData.friendly_fraud_risk || "LOW"}
                        </span>
                      </div>
                    </div>
                  </Panel>
                </div>

                {/* ── Fraud Findings (FRIA Narrative) ──────────────────── */}
                <Panel>
                  <SectionTitle>Fraud Findings</SectionTitle>
                  <ul style={{ display: "flex", flexDirection: "column", gap: "0.4rem", margin: 0, padding: 0, listStyle: "none" }}>
                    {(fd as any).fraud_reasoning && (fd as any).fraud_reasoning.length > 0 ? (
                      (fd as any).fraud_reasoning.map((reason: string, idx: number) => (
                        <li key={idx} style={{ display: "flex", alignItems: "flex-start", gap: "0.625rem", fontSize: "0.75rem", color: "#94A3B8", lineHeight: 1.55 }}>
                          <span style={{ flexShrink: 0, width: 5, height: 5, borderRadius: "50%", backgroundColor: riskColor, marginTop: 7 }} />
                          {reason}
                        </li>
                      ))
                    ) : (
                      <li style={{ fontSize: "0.72rem", color: "#64748B" }}>No fraud findings generated.</li>
                    )}
                  </ul>
                </Panel>

              </div>
            );
          })()}

          {/* ── Investigation tab ─────────────────────────────────────────── */}
          {activeTab === "investigation" && (() => {
            if (!plan) return (
              <Panel style={{ padding: "3rem", textAlign: "center" }}>
                <p style={{ fontSize: "0.8rem", color: "#64748B" }}>Investigation plan not yet generated.</p>
                <p style={{ fontSize: "0.72rem", color: "#475569", marginTop: 4 }}>Re-submit or re-analyse to trigger the investigation agent.</p>
              </Panel>
            );

            const invConfPct   = plan.investigation_confidence != null ? Math.round(plan.investigation_confidence * 100) : null;
            const dqPct        = plan.data_quality_score != null ? Math.round(plan.data_quality_score * 100) : null;
            const queueConfPct = plan.queue_confidence != null ? Math.round(plan.queue_confidence * 100) : null;

            return (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>

                {/* Investigation header */}
                <Panel>
                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                    {plan.investigation_complexity && (
                      <span style={{ fontSize: "0.7rem", fontWeight: 600, padding: "0.25rem 0.625rem", border: "1px solid #334155", borderRadius: 3, backgroundColor: plan.investigation_complexity === "CRITICAL" ? "#FEF2F2" : plan.investigation_complexity === "HIGH" ? "#FFFBEB" : "#F0FDF4", color: plan.investigation_complexity === "CRITICAL" ? "#991B1B" : plan.investigation_complexity === "HIGH" ? "#92400E" : "#166534", borderColor: plan.investigation_complexity === "CRITICAL" ? "#FECACA" : plan.investigation_complexity === "HIGH" ? "#FDE68A" : "#BBF7D0" }}>
                        {plan.investigation_complexity} COMPLEXITY
                      </span>
                    )}
                    {plan.duplicate_found && <span style={{ fontSize: "0.7rem", fontWeight: 600, padding: "0.25rem 0.625rem", backgroundColor: "#FEF2F2", color: "#991B1B", border: "1px solid #FECACA", borderRadius: 3 }}>DUPLICATE DETECTED</span>}
                    {plan.manual_review_required && <span style={{ fontSize: "0.7rem", fontWeight: 600, padding: "0.25rem 0.625rem", backgroundColor: "#FFFBEB", color: "#92400E", border: "1px solid #FDE68A", borderRadius: 3 }}>MANUAL REVIEW</span>}
                  </div>
                  <p style={{ fontSize: "0.75rem", color: "#94A3B8", lineHeight: 1.6 }}>{plan.investigation_summary}</p>

                  {/* Confidence meters */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.875rem", marginTop: "0.875rem", paddingTop: "0.75rem", borderTop: "1px solid #334155" }}>
                    {[
                      { label: "Plan Confidence",  value: invConfPct },
                      { label: "Queue Confidence", value: queueConfPct },
                      { label: "Data Quality",     value: dqPct },
                    ].map(({ label, value }) => value != null ? (
                      <div key={label}>
                        <Label>{label}</Label>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <div style={{ flex: 1, height: 4, backgroundColor: "#334155", borderRadius: 2 }}>
                            <div style={{ height: "100%", width: `${value}%`, backgroundColor: value >= 75 ? "#15803D" : value >= 55 ? "#B45309" : "#B91C1C", borderRadius: 2, transition: "width 0.4s" }} />
                          </div>
                          <span style={{ fontSize: "0.72rem", fontWeight: 600, fontFamily: "ui-monospace, monospace", color: value >= 75 ? "#4ADE80" : value >= 55 ? "#FCD34D" : "#FCA5A5" }}>{value}%</span>
                        </div>
                      </div>
                    ) : null)}
                  </div>

                  {/* Investigation coverage — lives here alongside the scores */}
                  {plan.investigation_coverage && (
                    <div style={{ marginTop: "0.75rem", paddingTop: "0.75rem", borderTop: "1px solid #334155" }}>
                      <div style={{ fontSize: "0.6rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: "#64748B", marginBottom: "0.5rem" }}>Investigation Coverage</div>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.375rem" }}>
                        {[
                          { key: "customer_history_checked",  label: "Customer History" },
                          { key: "merchant_history_checked",  label: "Merchant Risk" },
                          { key: "duplicate_check_performed", label: "Duplicate Check" },
                          { key: "related_cases_reviewed",    label: "Related Cases" },
                        ].map(({ key, label }) => {
                          const checked = (plan.investigation_coverage as any)?.[key];
                          return (
                            <div key={key} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.3rem", padding: "0.5rem 0.375rem", backgroundColor: checked ? "#F0FDF4" : "#111827", border: `1px solid ${checked ? "#BBF7D0" : "#334155"}`, borderRadius: 3, textAlign: "center" }}>
                              {checked
                                ? <CheckCircle style={{ width: 13, height: 13, color: "#15803D" }} />
                                : <div style={{ width: 13, height: 13, borderRadius: "50%", border: "1px solid #334155" }} />}
                              <span style={{ fontSize: "0.6rem", fontWeight: 500, color: checked ? "#166534" : "#64748B", lineHeight: 1.3 }}>{label}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </Panel>

                {/* Manual review reasons */}
                {plan.manual_review_required && (plan.manual_review_reason ?? []).length > 0 && (
                  <Panel style={{ backgroundColor: "#FFFBEB", border: "1px solid #FDE68A" }}>
                    <SectionTitle>Manual Review Required</SectionTitle>
                    <ul style={{ display: "flex", flexDirection: "column", gap: "0.375rem", margin: 0, padding: 0, listStyle: "none" }}>
                      {(plan.manual_review_reason ?? []).map((r: string, i: number) => (
                        <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", fontSize: "0.72rem", color: "#92400E" }}>
                          <span style={{ width: 4, height: 4, borderRadius: "50%", backgroundColor: "#B45309", flexShrink: 0, marginTop: 5 }} />
                          {r}
                        </li>
                      ))}
                    </ul>
                  </Panel>
                )}

                {/* Key investigation findings */}
                {(plan.investigation_reasoning ?? []).length > 0 && (
                  <Panel>
                    <SectionTitle>Key Investigation Findings</SectionTitle>
                    <ol style={{ display: "flex", flexDirection: "column", gap: "0.5rem", margin: 0, padding: 0, listStyle: "none" }}>
                      {(plan.investigation_reasoning ?? []).map((finding: string, i: number) => (
                        <li key={i} style={{ display: "flex", gap: "0.625rem", fontSize: "0.72rem", color: "#94A3B8" }}>
                          <span style={{ flexShrink: 0, width: 18, height: 18, borderRadius: 3, backgroundColor: "#111827", border: "1px solid #334155", color: "#64748B", fontSize: "0.6rem", fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center" }}>{i + 1}</span>
                          <span style={{ lineHeight: 1.6, paddingTop: 1 }}>{finding}</span>
                        </li>
                      ))}
                    </ol>
                  </Panel>
                )}

                {/* Investigation gaps */}
                {(plan.investigation_gaps ?? []).length > 0 ? (
                  <Panel style={{ backgroundColor: "#FFFBEB", border: "1px solid #FDE68A" }}>
                    <SectionTitle>Investigation Gaps</SectionTitle>
                    <ul style={{ display: "flex", flexDirection: "column", gap: "0.375rem", margin: 0, padding: 0, listStyle: "none" }}>
                      {(plan.investigation_gaps ?? []).map((gap: string, i: number) => (
                        <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", fontSize: "0.72rem", color: "#92400E" }}>
                          <span style={{ width: 4, height: 4, borderRadius: "50%", backgroundColor: "#B45309", flexShrink: 0, marginTop: 5 }} />
                          {gap}
                        </li>
                      ))}
                    </ul>
                  </Panel>
                ) : (
                  <Panel style={{ backgroundColor: "#F0FDF4", border: "1px solid #BBF7D0", display: "flex", alignItems: "center", gap: "0.625rem" }}>
                    <CheckCircle style={{ width: 14, height: 14, color: "#15803D", flexShrink: 0 }} />
                    <p style={{ fontSize: "0.72rem", color: "#166534", fontWeight: 500 }}>No investigation gaps identified — all areas covered.</p>
                  </Panel>
                )}

                {/* Customer History + Merchant Intelligence */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.875rem" }}>
                  <Panel>
                    <SectionTitle>Customer History</SectionTitle>
                    <InfoRow label="Prior Disputes"  value={plan.customer_risk_profile?.previous_disputes ?? "—"} />
                    <InfoRow label="Fraud Claims"    value={plan.customer_risk_profile?.fraud_claims ?? "—"} />
                    <InfoRow label="Last Dispute"    value={plan.customer_risk_profile?.last_dispute_days_ago != null && plan.customer_risk_profile.last_dispute_days_ago >= 0 ? `${plan.customer_risk_profile.last_dispute_days_ago} days ago` : "Never"} />
                    <InfoRow label="Risk Level"      value={plan.customer_risk_profile?.risk_level ?? "—"} />
                    {plan.customer_risk_profile?.assessment && <div style={{ marginTop: "0.5rem", fontSize: "0.7rem", color: "#64748B", lineHeight: 1.5 }}>{plan.customer_risk_profile.assessment}</div>}
                  </Panel>
                  <Panel>
                    <SectionTitle>Merchant Intelligence</SectionTitle>
                    <InfoRow label="Risk Level"       value={plan.merchant_risk_profile?.merchant_risk ?? "—"} />
                    <InfoRow label="Prior Complaints" value={plan.merchant_risk_profile?.prior_complaints ?? "—"} />
                    <InfoRow label="Fraud Rate"       value={plan.merchant_risk_profile?.fraud_rate != null ? `${(plan.merchant_risk_profile.fraud_rate * 100).toFixed(0)}%` : "—"} />
                    {plan.merchant_risk_profile?.assessment && <div style={{ marginTop: "0.5rem", fontSize: "0.7rem", color: "#64748B", lineHeight: 1.5 }}>{plan.merchant_risk_profile.assessment}</div>}
                  </Panel>
                  <Panel>
                    <SectionTitle>Historical Cases</SectionTitle>
                    <InfoRow label="Similar Cases"      value={plan.related_cases?.similar_cases ?? "—"} />
                    <InfoRow label="Resolved in Favour" value={plan.related_cases?.resolved_in_favor ?? "—"} />
                    <InfoRow label="Resolution Rate"    value={plan.related_cases?.resolution_rate != null ? `${(plan.related_cases.resolution_rate * 100).toFixed(0)}%` : "—"} />
                    {plan.duplicate_found && plan.related_case_id && <InfoRow label="Duplicate Of" value={plan.related_case_id} mono />}
                  </Panel>
                  <Panel>
                    <SectionTitle>Recommended Steps</SectionTitle>
                    {plan.recommended_steps?.length > 0 ? (
                      <ol style={{ display: "flex", flexDirection: "column", gap: "0.375rem", margin: 0, padding: 0, listStyle: "none" }}>
                        {plan.recommended_steps.map((step: string, i: number) => (
                          <li key={i} style={{ display: "flex", gap: "0.5rem", fontSize: "0.72rem", color: "#94A3B8" }}>
                            <span style={{ flexShrink: 0, fontSize: "0.65rem", fontWeight: 700, color: "#2563EB", paddingTop: 1 }}>{i + 1}.</span>
                            <span style={{ lineHeight: 1.5 }}>{step}</span>
                          </li>
                        ))}
                      </ol>
                    ) : <p style={{ fontSize: "0.72rem", color: "#64748B" }}>No steps available.</p>}
                  </Panel>
                </div>

                {/* Queue routing rationale — collapsible */}
                {(plan.queue_confidence_factors ?? []).length > 0 && (
                  <Panel>
                    <button onClick={() => setWhyPlanOpen(v => !v)} style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
                      <span style={{ fontSize: "0.65rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#64748B" }}>Queue Routing Rationale</span>
                      {whyPlanOpen ? <ChevronUp style={{ width: 14, height: 14, color: "#64748B" }} /> : <ChevronDown style={{ width: 14, height: 14, color: "#64748B" }} />}
                    </button>
                    {whyPlanOpen && (
                      <ul style={{ display: "flex", flexDirection: "column", gap: "0.375rem", listStyle: "none", margin: 0, padding: 0, marginTop: "0.75rem", paddingTop: "0.75rem", borderTop: "1px solid #334155" }}>
                        {(plan.queue_confidence_factors ?? []).map((f: string, i: number) => (
                          <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", fontSize: "0.72rem", color: "#94A3B8" }}>
                            <span style={{ width: 3, height: 3, borderRadius: "50%", backgroundColor: "#2563EB", flexShrink: 0, marginTop: 6 }} />
                            {f}
                          </li>
                        ))}
                      </ul>
                    )}
                  </Panel>
                )}

              </div>
            );
          })()}

          {/* ── Evidence Review tab ──────────────────────────────────────── */}
          {activeTab === "evidence_review" && (() => {
            const ea = evidenceAssessment;

            if (!ea) {
              const eiaInPath = (wfPlan?.workflow_path ?? []).includes("EVIDENCE_AGENT");
              return (
                <Panel style={{ padding: "2rem", textAlign: "center" }}>
                  {eiaInPath ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" style={{ color: "#2563EB", margin: "0 auto 0.75rem" }} />
                      <p style={{ fontSize: "0.8rem", color: "#64748B", marginBottom: "0.25rem" }}>Evidence review in progress.</p>
                      <p style={{ fontSize: "0.72rem", color: "#475569" }}>Results will appear here once the pipeline completes.</p>
                    </>
                  ) : (
                    <>
                      <CheckCircle style={{ width: 18, height: 18, color: "#4ADE80", margin: "0 auto 0.75rem" }} />
                      <p style={{ fontSize: "0.8rem", color: "#64748B", marginBottom: "0.25rem" }}>Evidence review not required for this case.</p>
                      <p style={{ fontSize: "0.72rem", color: "#475569" }}>Case Coordination determined that a full evidence review was not needed based on the dispute type and submitted documents.</p>
                    </>
                  )}
                </Panel>
              );
            }

            // Downgrade strength when customer docs are still missing (matches backend logic)
            const customerMissingForStrength = (ea.missing_documents ?? []).filter(
              (d: string) => !BANK_OBTAINABLE.has(d)
            ).length;
            const effectiveStrength = (ea.evidence_strength === "HIGH" && customerMissingForStrength > 0)
              ? "MEDIUM"
              : ea.evidence_strength;

            const effectiveScore = ea.evidence_strength_score ?? 0;

            const strengthColor = effectiveStrength === "HIGH" ? "#4ADE80" : effectiveStrength === "MEDIUM" ? "#FCD34D" : "#FCA5A5";
            const strengthBg    = effectiveStrength === "HIGH" ? "#F0FDF4" : effectiveStrength === "MEDIUM" ? "#FFFBEB" : "#FEF2F2";
            const strengthBorder = effectiveStrength === "HIGH" ? "#BBF7D0" : effectiveStrength === "MEDIUM" ? "#FDE68A" : "#FECACA";
            const strengthTextColor = effectiveStrength === "HIGH" ? "#166534" : effectiveStrength === "MEDIUM" ? "#92400E" : "#991B1B";
            const completenessColor = (ea.evidence_completeness ?? 0) >= 80 ? "#15803D" : (ea.evidence_completeness ?? 0) >= 50 ? "#B45309" : "#B91C1C";

            return (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>

                {/* Fallback banner */}
                {ea.fallback_mode && (
                  <div style={{ padding: "0.625rem 1rem", backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 4, display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
                    <AlertTriangle style={{ width: 13, height: 13, color: "#94A3B8", flexShrink: 0, marginTop: 2 }} />
                    <span style={{ fontSize: "0.7rem", color: "#94A3B8" }}>Evidence review completed using standard assessment criteria.</span>
                  </div>
                )}

                {/* ── Section 1: Evidence Summary cards ── */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "0.5rem" }}>
                  <Panel>
                    <Label>Completeness</Label>
                    <div style={{ fontSize: "1.1rem", fontWeight: 700, color: completenessColor, fontFamily: "ui-monospace, monospace" }}>{ea.evidence_completeness ?? "—"}%</div>
                    <div style={{ marginTop: 4, height: 3, backgroundColor: "#334155", borderRadius: 2 }}>
                      <div style={{ height: "100%", width: `${ea.evidence_completeness ?? 0}%`, backgroundColor: completenessColor, borderRadius: 2 }} />
                    </div>
                  </Panel>
                  <Panel>
                    <Label>Status</Label>
                    {(() => {
                      const realIssues = (ea.consistency_issues ?? []).filter(
                        (i: string) => !i.toLowerCase().includes("not found")
                      );
                      const infoOnly = (ea.consistency_issues ?? []).length > 0 && realIssues.length === 0;
                      return (
                        <>
                          <div style={{ fontSize: "0.85rem", fontWeight: 700, color: realIssues.length > 0 ? "#FCA5A5" : infoOnly ? "#FCD34D" : "#4ADE80" }}>
                            {realIssues.length > 0 ? "Issues Found" : infoOnly ? "Unverified" : "Consistent"}
                          </div>
                          <div style={{ fontSize: "0.65rem", color: "#64748B", marginTop: 2 }}>
                            {realIssues.length > 0
                              ? `${realIssues.length} mismatch(es)`
                              : infoOnly ? "Txn record not found" : "No issues"}
                          </div>
                        </>
                      );
                    })()}
                  </Panel>
                  <Panel>
                    <Label>Review Status</Label>
                    {(() => {
                      const missingCustomerDocs = (ea.missing_documents ?? []).filter((d: string) => !BANK_OBTAINABLE.has(d));
                      const hasCustomerDocGap = missingCustomerDocs.length > 0;
                      const statusColor = ea.investigation_blocked ? "#FCA5A5" : hasCustomerDocGap ? "#FCD34D" : "#4ADE80";
                      const statusText = ea.investigation_blocked
                        ? "Blocked — Pending Documents"
                        : hasCustomerDocGap
                          ? "Additional Customer Documents Required"
                          : "Ready to Proceed";
                      return (
                        <div style={{ fontSize: "0.78rem", fontWeight: 700, color: statusColor, lineHeight: 1.3 }}>
                          {statusText}
                        </div>
                      );
                    })()}
                    <div style={{ fontSize: "0.65rem", color: "#64748B", marginTop: 4 }}>
                      {(ea.missing_documents ?? []).filter((d: string) => !BANK_OBTAINABLE.has(d)).length > 0
                        ? `${(ea.missing_documents ?? []).filter((d: string) => !BANK_OBTAINABLE.has(d)).length} customer doc(s) missing`
                        : "All customer docs present"}
                    </div>
                  </Panel>
                  <Panel>
                    <Label>Human Review</Label>
                    {(() => {
                      const customerMissingCount = (ea.missing_documents ?? []).filter(
                        (d: string) => !BANK_OBTAINABLE.has(d)
                      ).length;
                      const needsReview = ea.manual_evidence_review
                        || customerMissingCount > 0
                        || caseData.requires_manual_review;
                      return (
                        <div style={{ fontSize: "0.85rem", fontWeight: 700, color: needsReview ? "#FCA5A5" : "#4ADE80" }}>
                          {needsReview ? "Required" : "Not Required"}
                        </div>
                      );
                    })()}
                  </Panel>
                </div>

                {/* ── Section 2: Evidence Strength ── */}
                <Panel style={{ backgroundColor: strengthBg, border: `1px solid ${strengthBorder}` }}>
                  <SectionTitle>Evidence Strength</SectionTitle>
                  <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                        <span style={{ fontSize: "0.7rem", color: strengthTextColor, fontWeight: 600 }}>{effectiveStrength}</span>
                        <span style={{ fontSize: "0.7rem", color: strengthTextColor, fontFamily: "ui-monospace, monospace", fontWeight: 700 }}>
                          {Math.round(effectiveScore * 100)}%
                        </span>
                      </div>
                      <div style={{ height: 6, backgroundColor: "rgba(0,0,0,0.08)", borderRadius: 3 }}>
                        <div style={{ height: "100%", width: `${Math.round(effectiveScore * 100)}%`, backgroundColor: strengthColor, borderRadius: 3, transition: "width 0.4s" }} />
                      </div>
                    </div>
                  </div>
                  {(() => {
                    const customerMissingCount = (ea.missing_documents ?? []).filter(
                      (d: string) => !BANK_OBTAINABLE.has(d)
                    ).length;
                    const rec = customerMissingCount > 0
                      ? "Additional documentation required before investigation can proceed."
                      : ea.review_recommendation;
                    return rec ? (
                      <p style={{ fontSize: "0.75rem", color: strengthTextColor, marginTop: "0.75rem", fontWeight: 500, lineHeight: 1.5 }}>
                        {rec}
                      </p>
                    ) : null;
                  })()}
                </Panel>

                {/* ── Section 2b: Document Evidence Provenance ── */}
                {(() => {
                  const meta = caseData.agent_metadata;
                  const evaluatedFiles = meta?.evaluated_files ?? [];
                  const sourceSummary = meta?.evidence_source_summary ?? [];
                  const trace = meta?.evidence_trace;
                  if (evaluatedFiles.length === 0 && !trace) return null;
                  const verdictColor = trace?.verdict === "MATCH" ? "#4ADE80" : trace?.verdict === "PARTIAL_MATCH" ? "#FCD34D" : trace?.verdict === "MISMATCH" ? "#FCA5A5" : "#64748B";
                  return (
                    <Panel>
                      <SectionTitle>Document Evidence Provenance</SectionTitle>
                      {/* Verdict badge row */}
                      {trace && (
                        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem", padding: "0.5rem 0.75rem", backgroundColor: "#111827", border: "1px solid #1E293B", borderRadius: 4 }}>
                          <span style={{ fontSize: "0.65rem", fontWeight: 700, letterSpacing: "0.05em", color: "#475569", textTransform: "uppercase" }}>Agent 1 Verdict</span>
                          <span style={{ fontSize: "0.72rem", fontWeight: 700, color: verdictColor, fontFamily: "ui-monospace, monospace" }}>{trace.verdict}</span>
                          {trace.evidence_match === true && <span style={{ fontSize: "0.65rem", color: "#4ADE80" }}>— Documents support the claim</span>}
                          {trace.evidence_match === false && <span style={{ fontSize: "0.65rem", color: "#FCA5A5" }}>— Documents contradict the claim</span>}
                          {trace.evidence_match === null && <span style={{ fontSize: "0.65rem", color: "#64748B" }}>— Match not assessed</span>}
                        </div>
                      )}
                      {/* Evaluated files table */}
                      {evaluatedFiles.length > 0 && (
                        <div style={{ marginBottom: "0.75rem" }}>
                          <div style={{ display: "grid", gridTemplateColumns: "1fr 140px", gap: "0 0.5rem", borderBottom: "1px solid #1E293B", paddingBottom: "0.35rem", marginBottom: "0.35rem" }}>
                            <span style={{ fontSize: "0.6rem", fontWeight: 700, color: "#475569", textTransform: "uppercase" }}>File</span>
                            <span style={{ fontSize: "0.6rem", fontWeight: 700, color: "#475569", textTransform: "uppercase" }}>Document Type</span>
                          </div>
                          {evaluatedFiles.map((f, i) => {
                            const rawName = f.filename ?? "";
                            const baseName = rawName.replace(/\.[^.]+$/, "");
                            const ext = rawName.includes(".") ? rawName.split(".").pop() : "";
                            const isHash = /^[0-9a-f]{20,}$/i.test(baseName);
                            const displayName = isHash
                              ? `${baseName.slice(0, 8)}…${baseName.slice(-4)}.${ext}`
                              : rawName;
                            return (
                              <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 140px", gap: "0 0.5rem", padding: "0.3rem 0", borderBottom: "1px solid #0F172A" }}>
                                <span style={{ fontSize: "0.7rem", color: "#CBD5E1", fontFamily: "ui-monospace, monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={rawName}>{displayName}</span>
                                <span style={{ fontSize: "0.65rem", color: "#64748B" }}>{f.document_type.replace(/_/g, " ")}</span>
                              </div>
                            );
                          })}
                        </div>
                      )}
                      {/* Source summary */}
                      {sourceSummary.length > 0 && (
                        <ul style={{ display: "flex", flexDirection: "column", gap: "0.3rem", margin: 0, padding: 0, listStyle: "none" }}>
                          {sourceSummary.map((s, i) => (
                            <li key={i} style={{ display: "flex", gap: "0.5rem", fontSize: "0.71rem", color: "#94A3B8", lineHeight: 1.5 }}>
                              <span style={{ flexShrink: 0, color: "#334155", marginTop: 3 }}>›</span>
                              {s}
                            </li>
                          ))}
                        </ul>
                      )}
                    </Panel>
                  );
                })()}

                {/* ── Section 3: Missing Documents (customer-obtainable only) ── */}
                {(() => {
                  const customerMissing = (ea.missing_documents ?? []).filter(
                    (d: string) => !BANK_OBTAINABLE.has(d)
                  );
                  return customerMissing.length > 0 ? (
                    <Panel style={{ backgroundColor: "#FEF2F2", border: "1px solid #FECACA" }}>
                      <SectionTitle>Missing Documents</SectionTitle>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.375rem" }}>
                        {customerMissing.map((doc: string, i: number) => (
                          <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.4rem 0.625rem", backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 3 }}>
                            <FileText style={{ width: 11, height: 11, color: "#B91C1C", flexShrink: 0 }} />
                            <span style={{ fontSize: "0.7rem", color: "#991B1B" }}>{doc}</span>
                          </div>
                        ))}
                      </div>
                    </Panel>
                  ) : (
                    <Panel style={{ backgroundColor: "#F0FDF4", border: "1px solid #BBF7D0", display: "flex", alignItems: "center", gap: "0.625rem" }}>
                      <CheckCircle style={{ width: 14, height: 14, color: "#15803D", flexShrink: 0 }} />
                      <p style={{ fontSize: "0.72rem", color: "#166534", fontWeight: 500 }}>No missing documents — all required evidence is present.</p>
                    </Panel>
                  );
                })()}

                {/* ── Section 3b: Bank-Obtainable Docs (informational, not customer-facing) ── */}
                {(ea.bank_pending_documents?.length ?? 0) > 0 && (
                  <Panel style={{ border: "1px solid #334155" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.625rem" }}>
                      <SectionTitle>Pending — Bank to Obtain</SectionTitle>
                      <span style={{ fontSize: "0.6rem", color: "#475569", fontWeight: 500, padding: "0.1rem 0.5rem", border: "1px solid #334155", borderRadius: 3 }}>
                        Internal
                      </span>
                    </div>
                    <p style={{ fontSize: "0.68rem", color: "#475569", marginBottom: "0.625rem", lineHeight: 1.5 }}>
                      These documents are obtained by the bank or merchant internally — not the customer&apos;s responsibility.
                      They do not affect evidence completeness.
                    </p>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.375rem" }}>
                      {ea.bank_pending_documents!.map((doc: string, i: number) => (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.4rem 0.625rem", backgroundColor: "#111827", border: "1px solid #334155", borderRadius: 3 }}>
                          <FileText style={{ width: 11, height: 11, color: "#475569", flexShrink: 0 }} />
                          <span style={{ fontSize: "0.7rem", color: "#64748B" }}>{doc}</span>
                        </div>
                      ))}
                    </div>
                  </Panel>
                )}

                {/* ── Section 4: Recommended Document Requests — sourced from missing_documents ── */}
                {(ea.missing_documents ?? []).filter((d: string) => !BANK_OBTAINABLE.has(d)).length > 0 && (
                  <Panel>
                    <SectionTitle>Recommended Document Requests</SectionTitle>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                      {(ea.missing_documents ?? []).filter((doc: string) => !BANK_OBTAINABLE.has(doc)).map((doc: string, i: number) => (
                        <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.5rem 0.75rem", backgroundColor: "#111827", border: "1px solid #334155", borderRadius: 3 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <FileText style={{ width: 12, height: 12, color: "#2563EB", flexShrink: 0 }} />
                            <span style={{ fontSize: "0.72rem", color: "#94A3B8" }}>{doc}</span>
                          </div>
                          <button
                            onClick={async () => {
                              try {
                                await createDocumentRequest(caseData.case_id, "system", doc, `Required for evidence review`, undefined);
                                toast.success(`Request created: ${doc}`);
                              } catch {
                                toast.error("Failed to create request");
                              }
                            }}
                            style={{ fontSize: "0.65rem", fontWeight: 600, padding: "0.2rem 0.625rem", backgroundColor: "#1D4ED8", color: "#F8FAFC", border: "none", borderRadius: 3, cursor: "pointer", whiteSpace: "nowrap" }}
                          >
                            Create Request
                          </button>
                        </div>
                      ))}
                    </div>
                    <p style={{ fontSize: "0.65rem", color: "#475569", marginTop: "0.5rem", borderTop: "1px solid #334155", paddingTop: "0.5rem" }}>
                      Creating a request will notify the customer to submit the document.
                    </p>
                  </Panel>
                )}

                {/* ── Section 5: Consistency Issues ── */}
                {(ea.consistency_issues?.length ?? 0) > 0 && (() => {
                  const realIssues = (ea.consistency_issues ?? []).filter(
                    (i: string) => !i.toLowerCase().includes("not found")
                  );
                  const infoIssues = (ea.consistency_issues ?? []).filter(
                    (i: string) => i.toLowerCase().includes("not found")
                  );
                  return (
                    <>
                      {realIssues.length > 0 && (
                        <Panel style={{ backgroundColor: "#FFFBEB", border: "1px solid #FDE68A" }}>
                          <SectionTitle>Consistency Issues</SectionTitle>
                          <ul style={{ display: "flex", flexDirection: "column", gap: "0.375rem", margin: 0, padding: 0, listStyle: "none" }}>
                            {realIssues.map((issue: string, i: number) => (
                              <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", fontSize: "0.72rem", color: "#92400E" }}>
                                <span style={{ width: 4, height: 4, borderRadius: "50%", backgroundColor: "#B45309", flexShrink: 0, marginTop: 5 }} />
                                {issue}
                              </li>
                            ))}
                          </ul>
                        </Panel>
                      )}
                      {infoIssues.length > 0 && (
                        <Panel style={{ backgroundColor: "#1E293B", border: "1px solid #334155" }}>
                          <SectionTitle>Consistency Check Note</SectionTitle>
                          <ul style={{ display: "flex", flexDirection: "column", gap: "0.375rem", margin: 0, padding: 0, listStyle: "none" }}>
                            {infoIssues.map((issue: string, i: number) => (
                              <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", fontSize: "0.72rem", color: "#64748B" }}>
                                <span style={{ width: 4, height: 4, borderRadius: "50%", backgroundColor: "#475569", flexShrink: 0, marginTop: 5 }} />
                                {issue}
                              </li>
                            ))}
                          </ul>
                        </Panel>
                      )}
                    </>
                  );
                })()}

                {/* ── Section 6: Evidence Findings ── */}
                {(ea.evidence_summary?.length ?? 0) > 0 && (
                  <Panel>
                    <SectionTitle>Evidence Findings</SectionTitle>
                    <ul style={{ display: "flex", flexDirection: "column", gap: "0.4rem", margin: 0, padding: 0, listStyle: "none" }}>
                      {ea.evidence_summary!.map((finding: string, i: number) => (
                        <li key={i} style={{ display: "flex", gap: "0.625rem", fontSize: "0.72rem", color: "#94A3B8" }}>
                          <span style={{ flexShrink: 0, width: 18, height: 18, borderRadius: 3, backgroundColor: "#111827", border: "1px solid #334155", color: "#64748B", fontSize: "0.6rem", fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center" }}>{i + 1}</span>
                          <span style={{ lineHeight: 1.6, paddingTop: 1 }}>{finding}</span>
                        </li>
                      ))}
                    </ul>
                    <p style={{ fontSize: "0.65rem", color: "#475569", marginTop: 8, borderTop: "1px solid #334155", paddingTop: 8 }}>
                      Evidence findings are based on document requests and case data — not a legal conclusion.
                    </p>
                  </Panel>
                )}


              </div>
            );
          })()}

          {/* ── Case Coordination tab ─────────────────────────────────────── */}
          {activeTab === "orchestration" && (() => {
            if (!wfPlan) return (
              <Panel style={{ padding: "3rem", textAlign: "center" }}>
                <p style={{ fontSize: "0.8rem", color: "#64748B" }}>Case coordination plan not yet generated.</p>
                <p style={{ fontSize: "0.72rem", color: "#475569", marginTop: "0.5rem" }}>Re-analyse the case to generate the coordination plan.</p>
              </Panel>
            );

            // ── Business-language translation maps ──────────────────────────
            const reviewLabels: Record<string, { label: string; color: string; action: string }> = {
              FRAUD_AGENT:      { label: "Fraud Review",         color: "#FCA5A5", action: "Conduct fraud investigation and verify transaction authenticity" },
              MERCHANT_AGENT:   { label: "Merchant Verification", color: "#FCD34D", action: "Contact merchant and request transaction confirmation" },
              EVIDENCE_AGENT:   { label: "Evidence Verification", color: "#60A5FA", action: "Verify submitted documents and supporting evidence" },
              COMPLIANCE_AGENT: { label: "Compliance Review",    color: "#A78BFA", action: "Complete compliance assessment and regulatory review" },
            };

            const operationalStatus: Record<string, string> = {
              READY:       "Pending Review",
              IN_PROGRESS: "Under Review",
              WAITING:     "Awaiting Response",
              COMPLETED:   "Ready for Resolution",
              ESCALATED:   "Escalated — Senior Review Required",
            };

            const complexityColor: Record<string, string> = {
              CRITICAL: "#FCA5A5", HIGH: "#FCD34D", MEDIUM: "#60A5FA", LOW: "#4ADE80",
            };
            const escalationColor: Record<string, string> = {
              CRITICAL: "#FCA5A5", HIGH: "#FCD34D", MEDIUM: "#FDE68A",
            };

            // Fallback complexity from case priority when WOA didn't set it
            const complexityValue: string = wfPlan.workflow_complexity
              ?? (caseData.priority === "CRITICAL" ? "CRITICAL"
                : caseData.priority === "HIGH"     ? "HIGH"
                : caseData.priority === "MEDIUM"   ? "MEDIUM"
                : caseData.priority === "LOW"      ? "LOW"
                : "MEDIUM");
            const complexColor  = complexityColor[complexityValue] ?? "#94A3B8";
            const escalColor    = wfPlan.escalation_level ? (escalationColor[wfPlan.escalation_level] ?? "#FCD34D") : null;
            const statusLabel   = operationalStatus[wfPlan.workflow_status] ?? wfPlan.workflow_status;
            const statusColor   = wfPlan.workflow_status === "COMPLETED"   ? "#4ADE80"
                                : wfPlan.workflow_status === "ESCALATED"   ? "#FCA5A5"
                                : wfPlan.workflow_status === "IN_PROGRESS" ? "#FCD34D"
                                : wfPlan.workflow_status === "WAITING"     ? "#FB923C"
                                : "#60A5FA";

            const nextReview    = wfPlan.next_agent ? (reviewLabels[wfPlan.next_agent] ?? { label: wfPlan.next_agent, color: "#94A3B8", action: "Review this case" }) : null;
            const nextAction    = nextReview?.action ?? "No further reviews required — case is ready for resolution.";

            // Reconstruct workflow_path when null — build from completed + next + remaining
            // Also inject FRAUD_AGENT into completed when fraud data exists but path is missing
            const _completedAgents: string[] = wfPlan.completed_agents ?? [];
            const _remainingAgents: string[] = wfPlan.remaining_agents ?? [];
            const _nextAgent: string | null   = wfPlan.next_agent ?? null;
            const _hasFraudData = caseData.fraud_suspicion === true;
            const _effectiveCompleted = _hasFraudData && !_completedAgents.includes("FRAUD_AGENT")
              ? ["FRAUD_AGENT", ..._completedAgents]
              : _completedAgents;
            const _basePath: string[] = wfPlan.workflow_path ?? [
              ..._effectiveCompleted,
              ...(_nextAgent && !_effectiveCompleted.includes(_nextAgent) ? [_nextAgent] : []),
              ..._remainingAgents.filter((a: string) => a !== _nextAgent && !_effectiveCompleted.includes(a)),
            ];
            // Append any required_agents not yet in the path — these are future steps shown in yellow
            const _pendingFuture = (wfPlan.required_agents ?? []).filter((a: string) => !_basePath.includes(a));
            const effectiveWorkflowPath: string[] = [..._basePath, ..._pendingFuture];

            // Fall back to effectiveWorkflowPath when required_agents wasn't set by WOA
            const _requiredAgents: string[] = (wfPlan.required_agents ?? []).length > 0
              ? wfPlan.required_agents
              : effectiveWorkflowPath;
            const requiredReviews = _requiredAgents.map((a: string) => reviewLabels[a] ?? { label: a, color: "#94A3B8", action: "" });

            // Translate technical reasoning into analyst-friendly language
            const sanitiseReason = (r: string): string => {
              const agentPhrases: [RegExp, string][] = [
                [/FRAUD_AGENT\s*(mandatory|required|needed)?/gi,      "Fraud review is required"],
                [/EVIDENCE_AGENT\s*(mandatory|required|needed)?/gi,   "Evidence verification is required"],
                [/MERCHANT_AGENT\s*(mandatory|required|needed)?/gi,   "Merchant verification is required"],
                [/COMPLIANCE_AGENT\s*(mandatory|required|needed)?/gi, "Compliance review is required"],
                [/\bAgent\s*[123]\b/gi,                               "case assessment"],
                [/\bLLM\b/gi,                                         "assessment"],
                [/\bfallback\b/gi,                                    "standard criteria"],
                [/\btool\b/gi,                                        "check"],
                [/\borchestrat\w+\b/gi,                               "coordination"],
                [/\bworkflow path\b/gi,                               "review process"],
                [/\brouting\b/gi,                                     "case direction"],
              ];
              let out = r;
              for (const [pattern, replacement] of agentPhrases) {
                out = out.replace(pattern, replacement);
              }
              // Capitalise first letter after replacements
              return out.charAt(0).toUpperCase() + out.slice(1);
            };

            return (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>

                {/* Fallback info — reworded as operational note, not technical error */}

                {/* ── Row 1: Three metric cards ── */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem" }}>
                  <Panel>
                    <Label>Case Complexity</Label>
                    <div style={{ fontSize: "1rem", fontWeight: 700, color: complexColor }}>{complexityValue}</div>
                  </Panel>
                  <Panel>
                    <Label>Escalation</Label>
                    {wfPlan.escalation_required
                      ? <div style={{ fontSize: "0.9rem", fontWeight: 700, color: escalColor ?? "#FCD34D" }}>{wfPlan.escalation_level} — Required</div>
                      : <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "#4ADE80" }}>Not Required</div>}
                  </Panel>
                  <Panel>
                    <Label>Human Review</Label>
                    {wfPlan.manual_review_required
                      ? <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "#FCA5A5" }}>Required</div>
                      : <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "#4ADE80" }}>Not Required</div>}
                  </Panel>
                </div>

                {/* ── Row 2: Review Summary — primary card ── */}
                <Panel style={{ border: "1px solid #334155" }}>
                  <SectionTitle>Review Summary</SectionTitle>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem 2rem" }}>
                    <div>
                      <Label>Required Reviews</Label>
                      {requiredReviews.length > 0
                        ? <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem", marginTop: 4 }}>
                            {requiredReviews.map(r => (
                              <span key={r.label} style={{ fontSize: "0.7rem", fontWeight: 600, color: r.color, padding: "0.15rem 0.5rem", backgroundColor: `${r.color}14`, border: `1px solid ${r.color}33`, borderRadius: 3 }}>{r.label}</span>
                            ))}
                          </div>
                        : <div style={{ fontSize: "0.72rem", color: "#4ADE80", marginTop: 4 }}>No specialist review required</div>}
                    </div>
                    <div>
                      <Label>Current Stage</Label>
                      <div style={{ fontSize: "0.78rem", fontWeight: 700, color: statusColor, marginTop: 4 }}>{statusLabel}</div>
                    </div>
                    <div>
                      <Label>Next Action</Label>
                      <div style={{ fontSize: "0.72rem", color: "#F8FAFC", lineHeight: 1.5, marginTop: 4 }}>{nextAction}</div>
                    </div>
                    <div>
                      <Label>Escalation</Label>
                      <div style={{ fontSize: "0.72rem", marginTop: 4 }}>
                        {wfPlan.escalation_required
                          ? <span style={{ color: escalColor ?? "#FCD34D", fontWeight: 600 }}>{wfPlan.escalation_level} — Senior review required</span>
                          : <span style={{ color: "#4ADE80" }}>Not required</span>}
                      </div>
                    </div>
                  </div>
                </Panel>

                {/* ── Row 3: Next Action + Review Process ── */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>

                  {/* Next Action */}
                  <Panel>
                    <SectionTitle>Next Action</SectionTitle>
                    {nextReview ? (
                      <>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.625rem" }}>
                          <div style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: nextReview.color, flexShrink: 0 }} />
                          <span style={{ fontSize: "0.8rem", fontWeight: 700, color: "#F8FAFC" }}>{nextReview.label}</span>
                        </div>
                        <div style={{ fontSize: "0.72rem", color: "#CBD5E1", lineHeight: 1.55, marginBottom: "0.625rem" }}>{nextReview.action}</div>
                        {(wfPlan.remaining_agents ?? []).length > 0 && (
                          <div style={{ paddingTop: "0.5rem", borderTop: "1px solid #1E293B" }}>
                            <Label>Following Reviews</Label>
                            <div style={{ fontSize: "0.7rem", color: "#64748B", marginTop: 4 }}>
                              {wfPlan.remaining_agents.map(a => reviewLabels[a]?.label ?? a).join("  →  ")}
                            </div>
                          </div>
                        )}
                      </>
                    ) : (
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <CheckCircle style={{ width: 14, height: 14, color: "#4ADE80", flexShrink: 0 }} />
                        <span style={{ fontSize: "0.75rem", color: "#4ADE80" }}>No further reviews required — case is ready for resolution.</span>
                      </div>
                    )}
                    <div style={{ marginTop: "0.75rem", paddingTop: "0.5rem", borderTop: "1px solid #1E293B" }}>
                      <Label>Case Status</Label>
                      <span style={{ fontSize: "0.72rem", fontWeight: 700, color: statusColor }}>{statusLabel}</span>
                    </div>
                  </Panel>

                  {/* Case Progression */}
                  <Panel>
                    <SectionTitle>Case Progression</SectionTitle>
                    {effectiveWorkflowPath.length === 0 ? (
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <CheckCircle style={{ width: 14, height: 14, color: "#4ADE80", flexShrink: 0 }} />
                        <span style={{ fontSize: "0.72rem", color: "#4ADE80" }}>No specialist reviews required for this case.</span>
                      </div>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
                        {effectiveWorkflowPath.map((agent: string, idx: number) => {
                          const info    = reviewLabels[agent] ?? { label: agent, color: "#94A3B8", action: "" };
                          const isDone  = _effectiveCompleted.includes(agent);
                          const isNow   = agent === _nextAgent;
                          const isPending = !isDone && !isNow;
                          return (
                            <div key={agent} style={{ display: "flex", alignItems: "center", gap: "0.625rem", padding: "0.4rem 0.625rem", backgroundColor: isNow ? "#1E3A5F" : isDone ? "#0D2414" : "#1A1500", borderRadius: 3, border: `1px solid ${isNow ? "#2563EB" : isDone ? "#166534" : "#3D2E00"}` }}>
                              <span style={{ fontSize: "0.6rem", fontWeight: 700, color: isPending ? "#A16207" : "#475569", width: 14, textAlign: "center", flexShrink: 0 }}>{idx + 1}</span>
                              <div style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: isDone ? "#4ADE80" : isNow ? info.color : "#A16207", flexShrink: 0 }} />
                              <span style={{ fontSize: "0.72rem", color: isDone ? "#4ADE80" : isNow ? "#F8FAFC" : "#FCD34D", flex: 1, fontWeight: isNow ? 600 : isPending ? 500 : 400 }}>{info.label}</span>
                              {isDone     && <CheckCircle style={{ width: 11, height: 11, color: "#4ADE80", flexShrink: 0 }} />}
                              {isNow      && !isDone && <span style={{ fontSize: "0.58rem", color: "#60A5FA", fontWeight: 700, flexShrink: 0 }}>NOW</span>}
                              {isPending  && <span style={{ fontSize: "0.58rem", color: "#EAB308", fontWeight: 600, flexShrink: 0 }}>PENDING</span>}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </Panel>
                </div>

                {/* ── Row 4: Required Reviews ── */}
                {requiredReviews.length > 0 && (
                  <Panel>
                    <SectionTitle>Required Reviews</SectionTitle>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "0.5rem" }}>
                      {requiredReviews.map(r => (
                        <div key={r.label} style={{ display: "flex", alignItems: "flex-start", gap: "0.625rem", padding: "0.5rem 0.625rem", backgroundColor: "#0F172A", border: `1px solid ${r.color}22`, borderRadius: 3 }}>
                          <div style={{ width: 7, height: 7, borderRadius: "50%", backgroundColor: r.color, flexShrink: 0, marginTop: 3 }} />
                          <div>
                            <div style={{ fontSize: "0.72rem", fontWeight: 700, color: r.color, marginBottom: 2 }}>{r.label}</div>
                            <div style={{ fontSize: "0.65rem", color: "#64748B", lineHeight: 1.4 }}>{r.action}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </Panel>
                )}

                {/* ── Row 5: Case Routing Summary ── */}
                {(wfPlan.workflow_reasoning ?? []).length > 0 && (
                  <Panel>
                    <SectionTitle>Case Routing Summary</SectionTitle>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0" }}>
                      {wfPlan.workflow_reasoning.map((r, i) => (
                        <div key={i} style={{ display: "flex", gap: "0.625rem", alignItems: "flex-start", padding: "0.45rem 0", borderBottom: i < wfPlan.workflow_reasoning.length - 1 ? "1px solid #1E293B" : "none" }}>
                          <div style={{ width: 5, height: 5, borderRadius: "50%", backgroundColor: "#334155", flexShrink: 0, marginTop: 6 }} />
                          <span style={{ fontSize: "0.72rem", color: "#CBD5E1", lineHeight: 1.55 }}>{sanitiseReason(r)}</span>
                        </div>
                      ))}
                    </div>
                  </Panel>
                )}


              </div>
            );
          })()}

          {/* ── Evidence tab ──────────────────────────────────────────────── */}
          {activeTab === "evidence" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {uploads.length === 0 ? (
                <Panel style={{ padding: "2.5rem", textAlign: "center" }}>
                  <p style={{ fontSize: "0.8rem", color: "#64748B" }}>No evidence files uploaded for this case.</p>
                </Panel>
              ) : uploads.map((file) => (
                <Panel key={file.name}>
                  <div style={{ display: "flex", alignItems: "flex-start", gap: "1rem" }}>
                    {file.is_image ? (
                      <div onClick={() => setLightbox(`http://localhost:8000${file.url}`)} style={{ width: 120, height: 80, flexShrink: 0, borderRadius: 3, overflow: "hidden", border: "1px solid #334155", cursor: "pointer", position: "relative" }}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={`http://localhost:8000${file.url}`} alt={file.name} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                        <div style={{ position: "absolute", inset: 0, backgroundColor: "rgba(0,0,0,0.4)", opacity: 0, transition: "opacity 0.15s", display: "flex", alignItems: "center", justifyContent: "center" }} className="hover:opacity-100">
                          <ZoomIn style={{ width: 20, height: 20, color: "white" }} />
                        </div>
                      </div>
                    ) : (
                      <div style={{ width: 120, height: 80, flexShrink: 0, borderRadius: 3, border: "1px solid #334155", backgroundColor: "#111827", display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <FileText style={{ width: 24, height: 24, color: "#64748B" }} />
                      </div>
                    )}
                    <div>
                      <p style={{ fontSize: "0.8rem", fontWeight: 600, color: "#F8FAFC", marginBottom: 4 }}>{file.name}</p>
                      <p style={{ fontSize: "0.7rem", color: "#64748B" }}>{file.is_image ? "Image document" : "Document"} — text extracted and included in case analysis.</p>
                    </div>
                  </div>
                </Panel>
              ))}
            </div>
          )}

          {/* ── Audit Trail tab ───────────────────────────────────────────── */}
          {activeTab === "audit" && (
            <Panel>
              <SectionTitle>Case Audit Log</SectionTitle>
              {auditLogs.length === 0 ? (
                <p style={{ fontSize: "0.8rem", color: "#64748B" }}>No audit events recorded.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column" }}>
                  {auditLogs.map((log) => (
                    <div key={log.id} style={{ display: "flex", gap: "1rem", padding: "0.625rem 0", borderBottom: "1px solid #1E293B" }}>
                      <div style={{ flexShrink: 0, paddingTop: 3 }}>
                        <div style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: "#2563EB" }} />
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: 2 }}>
                          <span style={{ fontSize: "0.7rem", fontWeight: 600, fontFamily: "ui-monospace, monospace", color: "#60A5FA" }}>{log.event_type}</span>
                          {log.stage && <span style={{ fontSize: "0.6rem", color: "#64748B", backgroundColor: "#111827", border: "1px solid #334155", borderRadius: 2, padding: "0.1rem 0.4rem" }}>{log.stage}</span>}
                          <span style={{ fontSize: "0.62rem", color: "#64748B", marginLeft: "auto" }}>{formatDate(log.created_at)}</span>
                        </div>
                        <p style={{ fontSize: "0.7rem", color: "#94A3B8" }}>{log.message}</p>
                        <p style={{ fontSize: "0.62rem", color: "#475569", marginTop: 1 }}>Actor: {log.actor}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          )}

          {/* ── Communications tab ────────────────────────────────────────── */}
          {activeTab === "communications" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "#F8FAFC" }}>Customer Communications</div>
                  <div style={{ fontSize: "0.65rem", color: "#64748B", marginTop: 2 }}>All notifications sent to the customer for this case.</div>
                </div>
                <button
                  onClick={async () => {
                    const st = caseData?.status || "";
                    const typeMap: Record<string, string> = {
                      "Dispute Raised":      "CASE_RECEIVED",
                      "Under Investigation": "INVESTIGATION_STARTED",
                      "Pending Documents":   "DOCUMENT_REQUESTED",
                      "Escalated":           "STATUS_CHANGED",
                      "Resolved":            "CASE_RESOLVED",
                      "Rejected":            "CASE_RESOLVED",
                      "Closed":              "CASE_RESOLVED",
                    };
                    const type = typeMap[st] || "STATUS_CHANGED";
                    try {
                      await sendCommunication(caseId!, type);
                      const res = await getCommunications(caseId!);
                      setCommunications(res.communications || []);
                      toast.success("Communication sent");
                    } catch { toast.error("Failed to send communication"); }
                  }}
                  style={{ fontSize: "0.7rem", padding: "0.35rem 0.75rem", backgroundColor: "#1E3A5F", color: "#93C5FD", border: "1px solid #2563EB", borderRadius: 4, cursor: "pointer" }}
                >
                  + Send Update
                </button>
              </div>

              {communications.length === 0 ? (
                <Panel style={{ textAlign: "center", padding: "2rem" }}>
                  <div style={{ fontSize: "0.8rem", color: "#64748B" }}>No communications sent yet.</div>
                </Panel>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  {communications.map((comm) => (
                    <Panel key={comm.id} style={{ padding: 0, overflow: "hidden" }}>
                      {/* Header row */}
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.625rem 1rem", borderBottom: "1px solid #1E293B", backgroundColor: "#0F172A" }}>
                        <span style={{ fontSize: "0.62rem", fontWeight: 700, padding: "2px 7px", borderRadius: 3, backgroundColor: "#0F172A", color: "#94A3B8", border: "1px solid #334155", textTransform: "uppercase", letterSpacing: "0.05em", whiteSpace: "nowrap" }}>
                          {comm.notification_type.replace(/_/g, " ")}
                        </span>
                        <span style={{
                          fontSize: "0.6rem", fontWeight: 600, padding: "2px 7px", borderRadius: 3,
                          backgroundColor: comm.status === "SENT" ? "#14532D" : comm.status === "FAILED" ? "#450A0A" : "#1C1209",
                          color:           comm.status === "SENT" ? "#4ADE80" : comm.status === "FAILED" ? "#FCA5A5" : "#FCD34D",
                          border: `1px solid ${comm.status === "SENT" ? "#166534" : comm.status === "FAILED" ? "#7F1D1D" : "#3D2E00"}`,
                        }}>
                          {comm.status}
                        </span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <span style={{ fontSize: "0.72rem", fontWeight: 600, color: "#F8FAFC" }}>{comm.subject}</span>
                        </div>
                        <div style={{ fontSize: "0.62rem", color: "#475569", whiteSpace: "nowrap", flexShrink: 0 }}>
                          To: {comm.recipient} &nbsp;·&nbsp; {formatDate(comm.sent_at || comm.created_at || "")}
                        </div>
                      </div>
                      {/* Email body — rendered in sandboxed iframe, expanded to full width for ops preview */}
                      <iframe
                        srcDoc={comm.body}
                        sandbox="allow-same-origin"
                        style={{ width: "100%", minHeight: 420, border: "none", display: "block", backgroundColor: "#fff" }}
                        onLoad={(e) => {
                          const iframe = e.currentTarget;
                          try {
                            const doc = iframe.contentDocument;
                            if (doc) {
                              // Inject CSS to expand 600px email card to full width for ops preview
                              const style = doc.createElement("style");
                              style.textContent = [
                                "body,html{margin:0!important;padding:0!important;background:#fff!important;}",
                                "table[width='600'],[style*='max-width:600px'],[style*='max-width: 600px']{width:100%!important;max-width:100%!important;}",
                                "td[align='center']>table{width:100%!important;}",
                              ].join("");
                              doc.head?.appendChild(style);
                            }
                            const h = doc?.documentElement?.scrollHeight;
                            if (h && h > 0) iframe.style.height = h + "px";
                          } catch {}
                        }}
                      />
                    </Panel>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Advanced Diagnostics tab ──────────────────────────────────── */}
          {activeTab === "advanced" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
              <Panel style={{ padding: "0.75rem 1rem", backgroundColor: "#0F172A", border: "1px solid #334155" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: "0.7rem", color: "#64748B" }}>Internal diagnostic data — not for standard case review.</span>
                  <button
                    onClick={() => setShowAdvanced(v => !v)}
                    style={{ fontSize: "0.7rem", color: "#2563EB", background: "none", border: "none", cursor: "pointer", padding: 0 }}
                  >
                    {showAdvanced ? "Hide Details" : "Show Details"}
                  </button>
                </div>
              </Panel>

              {showAdvanced && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.875rem" }}>
                  <Panel>
                    <SectionTitle>Case Stage</SectionTitle>
                    <WorkflowStatus status={caseData.status as CaseStatus} workflowReady={caseData.workflow_ready} />
                  </Panel>
                  <Panel>
                    <SectionTitle>Pipeline Execution</SectionTitle>
                    {workflowStates.length === 0 ? (
                      <p style={{ fontSize: "0.8rem", color: "#64748B" }}>No execution data available.</p>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
                        {workflowStates.map((ws) => (
                          <div key={ws.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0.5rem 0.625rem", backgroundColor: "#111827", border: "1px solid #334155", borderRadius: 3 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                              {ws.success
                                ? <div style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: "#15803D", flexShrink: 0 }} />
                                : <div style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: "#B91C1C", flexShrink: 0 }} />}
                              <span style={{ fontSize: "0.7rem", fontFamily: "ui-monospace, monospace", color: "#94A3B8" }}>{ws.node_name}</span>
                            </div>
                            {ws.execution_time_ms != null && (
                              <span style={{ fontSize: "0.65rem", color: "#64748B", fontFamily: "ui-monospace, monospace" }}>{ws.execution_time_ms.toFixed(0)}ms</span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </Panel>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── RIGHT PANEL — Controls & meta ─────────────────────────────────── */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>

          {/* Actions */}
          <Panel>
            <SectionTitle>Actions</SectionTitle>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <button onClick={handleReanalyse} disabled={reanalysing} className="btn-ghost" style={{ width: "100%", justifyContent: "center" }}>
                {reanalysing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw style={{ width: 13, height: 13 }} />}
                Re-analyse
              </button>
            </div>
          </Panel>

          {/* Case Status */}
          <Panel>
            <SectionTitle>Case Status</SectionTitle>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <select className="bfsi-select" value={caseData.status} onChange={(e) => handleStatusUpdate(e.target.value)} disabled={updatingStatus} aria-label="Case Status" title="Select case status">
                {CASE_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              {updatingStatus && (
                <div style={{ display: "flex", alignItems: "center", gap: "0.375rem", fontSize: "0.65rem", color: "#64748B" }}>
                  <Loader2 className="w-3 h-3 animate-spin" /> Updating…
                </div>
              )}
            </div>
          </Panel>

          {/* Priority — severity badge replaces numeric score */}
          <Panel>
            <SectionTitle>Priority</SectionTitle>
            <div style={{ marginBottom: caseData.assigned_queue || caseData.fraud_suspicion || caseData.requires_manual_review ? "0.625rem" : 0 }}>
              <span className={getPriorityColor(caseData.priority as never)} style={{ fontSize: "0.78rem", padding: "0.3rem 0.75rem", display: "inline-block", letterSpacing: "0.04em" }}>
                {caseData.priority}
              </span>
            </div>
            {caseData.assigned_queue && (
              <div style={{ marginTop: "0.5rem" }}>
                <Label>Assigned Queue</Label>
                <span style={{ fontSize: "0.7rem", color: "#94A3B8" }}>{caseData.assigned_queue.replace(/_/g, " ")}</span>
              </div>
            )}
            {caseData.fraud_suspicion && (
              <div style={{ marginTop: "0.5rem", padding: "0.4rem 0.625rem", backgroundColor: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 3, display: "flex", alignItems: "center", gap: "0.375rem" }}>
                <AlertTriangle style={{ width: 12, height: 12, color: "#B91C1C", flexShrink: 0 }} />
                <span style={{ fontSize: "0.7rem", fontWeight: 600, color: "#991B1B" }}>Fraud Indicator</span>
              </div>
            )}
            {caseData.requires_manual_review && (
              <div style={{ marginTop: "0.5rem", padding: "0.4rem 0.625rem", backgroundColor: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: 3 }}>
                <span style={{ fontSize: "0.7rem", fontWeight: 600, color: "#92400E" }}>Manual Review Required</span>
                {caseData.manual_review_reason && <p style={{ fontSize: "0.65rem", color: "#92400E", marginTop: 3, lineHeight: 1.4 }}>{caseData.manual_review_reason}</p>}
              </div>
            )}
            {caseData.sla_breached && (
              <span style={{ display: "inline-block", marginTop: 6, fontSize: "0.65rem", fontWeight: 600, padding: "0.15rem 0.5rem", backgroundColor: "#FEF2F2", color: "#991B1B", border: "1px solid #FECACA", borderRadius: 3 }}>SLA BREACHED</span>
            )}
          </Panel>

          {/* Assessment Strength */}
          <Panel>
            <SectionTitle>Assessment Strength</SectionTitle>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
              <span style={{ fontSize: "0.75rem", fontWeight: 600, color: confColor }}>{reliabilityLabel}</span>
              <span style={{ fontSize: "0.95rem", fontWeight: 700, fontFamily: "ui-monospace, monospace", color: confColor }}>{confidencePct}%</span>
            </div>
            <div style={{ height: 5, backgroundColor: "#334155", borderRadius: 2, marginBottom: "0.625rem" }}>
              <div style={{ height: "100%", width: `${confidencePct}%`, backgroundColor: caseData.confidence_score >= 0.75 ? "#15803D" : caseData.confidence_score >= 0.55 ? "#B45309" : "#B91C1C", borderRadius: 2, transition: "width 0.5s" }} />
            </div>
            {(() => {
              const factors = ((caseData as any).confidence_factors ?? [])
                .filter((f: string) => !/unavailable|failure|error|unknown/i.test(f));
              return factors.length > 0 ? (
                <ul style={{ display: "flex", flexDirection: "column", gap: "0.3rem", margin: 0, padding: 0, listStyle: "none" }}>
                  {factors.map((f: string, i: number) => (
                    <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.375rem", fontSize: "0.65rem", color: "#64748B" }}>
                      <CheckCircle style={{ width: 10, height: 10, color: "#15803D", flexShrink: 0, marginTop: 2 }} />
                      {f}
                    </li>
                  ))}
                </ul>
              ) : null;
            })()}
          </Panel>


          {/* Duplicate warning */}
          {caseData.duplicate_of && (
            <Panel style={{ backgroundColor: "#FFFBEB", border: "1px solid #FDE68A" }}>
              <Label>Potential Duplicate</Label>
              <p style={{ fontSize: "0.72rem", color: "#92400E" }}>This case may be a duplicate of:</p>
              <Link href={`/internal-review/${caseData.duplicate_of}`} style={{ fontSize: "0.72rem", fontWeight: 600, color: "#2563EB", fontFamily: "ui-monospace, monospace", textDecoration: "none" }}>
                {caseData.duplicate_of}
              </Link>
            </Panel>
          )}
        </div>
      </div>

      {/* Lightbox */}
      {lightbox && (
        <div onClick={() => setLightbox(null)} style={{ position: "fixed", inset: 0, zIndex: 50, backgroundColor: "rgba(0,0,0,0.92)", display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem" }}>
          <button
            type="button"
            onClick={() => setLightbox(null)}
            aria-label="Close preview"
            title="Close preview"
            style={{ position: "absolute", top: "1rem", right: "1rem", background: "none", border: "none", cursor: "pointer", color: "#94A3B8" }}
          >
            <X style={{ width: 24, height: 24 }} />
          </button>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={lightbox} alt="Evidence" style={{ maxWidth: "100%", maxHeight: "90vh", objectFit: "contain", borderRadius: 4 }} onClick={(e) => e.stopPropagation()} />
        </div>
      )}
    </>
  );
}
