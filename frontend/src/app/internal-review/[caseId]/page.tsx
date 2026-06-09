"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import toast from "react-hot-toast";
import {
  ArrowLeft, AlertTriangle, FileText, CheckCircle, Loader2,
  RefreshCw, X, ZoomIn, ChevronDown, ChevronUp,
} from "lucide-react";
import { formatCurrency, formatDate, getPriorityColor, getConfidenceLabel } from "@/lib/utils";
import { getCase, getAuditLogs, getWorkflowStates, updateCaseStatus, reanalyseCase, getCaseUploads } from "@/lib/api";
import type { CaseUploadFile } from "@/lib/api";
import type { DisputeCase, AuditLog, WorkflowState, CaseStatus } from "@/types";
import RiskTags from "@/components/dispute/RiskTags";
import WorkflowStatus from "@/components/dispute/WorkflowStatus";
import { useDisputeSocket, type DisputeSocketEvent } from "@/hooks/useDisputeSocket";

const CASE_STATUSES: CaseStatus[] = [
  "Dispute Raised", "Under Investigation", "Pending Documents",
  "Escalated", "Resolved", "Rejected", "Closed",
];

// ── Helpers ──────────────────────────────────────────────────────────────────

function getReliabilityLabel(score: number): string {
  if (score >= 0.85) return "High Reliability";
  if (score >= 0.70) return "Good Reliability";
  if (score >= 0.55) return "Moderate Reliability";
  if (score >= 0.40) return "Limited Reliability";
  return "Low Reliability";
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
  return <div style={{ fontSize: "0.6rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.07em", color: "#64748B", marginBottom: 4 }}>{children}</div>;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div style={{ fontSize: "0.65rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "#475569", paddingBottom: "0.5rem", borderBottom: "1px solid #334155", marginBottom: "0.75rem" }}>{children}</div>;
}

function InfoRow({ label, value, mono = false }: { label: string; value?: string | number | boolean | null; mono?: boolean }) {
  const display = value === true ? "Yes" : value === false ? "No" : (value ?? "—");
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", padding: "0.4rem 0", borderBottom: "1px solid #1E293B" }}>
      <span style={{ fontSize: "0.68rem", color: "#64748B" }}>{label}</span>
      <span style={{ fontSize: "0.72rem", color: "#F8FAFC", wordBreak: "break-all", fontFamily: mono ? "ui-monospace, monospace" : undefined }}>{String(display)}</span>
    </div>
  );
}

function Field({ label, value, mono = false }: { label: string; value?: string | number | boolean | null; mono?: boolean }) {
  const display = value === true ? "Yes" : value === false ? "No" : (value ?? "—");
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", padding: "0.45rem 0", borderBottom: "1px solid #1E293B" }}>
      <span style={{ fontSize: "0.7rem", color: "#64748B", flexShrink: 0, width: 130 }}>{label}</span>
      <span style={{ fontSize: "0.72rem", color: "#F8FAFC", textAlign: "right", wordBreak: "break-all", fontFamily: mono ? "ui-monospace, monospace" : undefined }}>{String(display)}</span>
    </div>
  );
}

function Panel({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 4, padding: "1rem", ...style }}>
      {children}
    </div>
  );
}

function CollapsibleSection({ title, open, onToggle, children }: {
  title: string; open: boolean; onToggle: () => void; children: React.ReactNode;
}) {
  return (
    <Panel style={{ padding: "0.75rem 1rem" }}>
      <button
        onClick={onToggle}
        style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", background: "none", border: "none", cursor: "pointer", padding: 0 }}
      >
        <span style={{ fontSize: "0.65rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: open ? "#94A3B8" : "#64748B" }}>
          {title}
        </span>
        {open
          ? <ChevronUp style={{ width: 12, height: 12, color: "#64748B" }} />
          : <ChevronDown style={{ width: 12, height: 12, color: "#64748B" }} />
        }
      </button>
      {open && (
        <div style={{ marginTop: "0.625rem", paddingTop: "0.625rem", borderTop: "1px solid #1E293B" }}>
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
  const [activeTab, setActiveTab]           = useState<"analysis" | "investigation" | "evidence" | "audit" | "workflow">("analysis");
  const [whyPlanOpen, setWhyPlanOpen]       = useState(false);
  const [liveUpdate, setLiveUpdate]         = useState(false);
  const [sidebarOpen, setSidebarOpen]       = useState<Record<string, boolean>>({
    summary: true, customer: false, transaction: false, dispute: false,
  });

  useEffect(() => {
    if (!caseId) return;
    setLoading(true);
    Promise.all([getCase(caseId), getAuditLogs(caseId), getWorkflowStates(caseId), getCaseUploads(caseId)])
      .then(([c, a, w, up]) => { setCaseData(c); setAuditLogs(a.audit_logs); setWorkflowStates(w.workflow_states); setUploads(up); })
      .catch(() => { toast.error("Case not found"); router.push("/internal-review"); })
      .finally(() => setLoading(false));
  }, [caseId, router]);

  useDisputeSocket((event: DisputeSocketEvent) => {
    if (event.type === "ANALYSIS_COMPLETE" && event.case_id === caseId) {
      setCaseData(event.case as unknown as DisputeCase);
      setLiveUpdate(true);
      setTimeout(() => setLiveUpdate(false), 3000);
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

  const tabs = [
    { key: "analysis",      label: "Case Analysis" },
    { key: "investigation", label: "Investigation" },
    { key: "evidence",      label: `Evidence (${uploads.length})` },
    { key: "audit",         label: "Audit Trail" },
    { key: "workflow",      label: "Workflow" },
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
      <div style={{ display: "grid", gridTemplateColumns: "260px 1fr 220px", gap: "1rem", alignItems: "start" }}>

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
              <button key={key} onClick={() => setActiveTab(key)}
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

              {/* Required documents */}
              {(() => {
                const docs: string[] = caseData.investigation_plan?.required_documents ?? [];
                return docs.length > 0 ? (
                  <Panel>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.75rem" }}>
                      <SectionTitle>Required Documents</SectionTitle>
                      <span style={{ fontSize: "0.65rem", color: "#64748B", backgroundColor: "#111827", border: "1px solid #334155", borderRadius: 3, padding: "0.1rem 0.5rem" }}>{docs.length} items</span>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.375rem" }}>
                      {docs.map((doc: string, i: number) => (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.4rem 0.625rem", backgroundColor: "#111827", border: "1px solid #334155", borderRadius: 3 }}>
                          <FileText style={{ width: 11, height: 11, color: "#2563EB", flexShrink: 0 }} />
                          <span style={{ fontSize: "0.7rem", color: "#94A3B8" }}>{doc}</span>
                        </div>
                      ))}
                    </div>
                    <p style={{ fontSize: "0.65rem", color: "#475569", marginTop: 8, borderTop: "1px solid #334155", paddingTop: 8 }}>
                      Requirements determined by dispute category, fraud indicators, and transaction value.
                    </p>
                  </Panel>
                ) : null;
              })()}
            </div>
          )}

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
                    <span style={{ fontSize: "0.7rem", fontWeight: 600, padding: "0.25rem 0.625rem", backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 3, color: "#94A3B8" }}>
                      {plan.recommended_queue?.replace(/_/g, " ") ?? "—"}
                    </span>
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
                    <InfoRow label="Last Dispute"    value={plan.customer_risk_profile?.last_dispute_days_ago != null ? `${plan.customer_risk_profile.last_dispute_days_ago} days ago` : "—"} />
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

                {/* Data quality */}
                {dqPct != null && (
                  <Panel>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.625rem" }}>
                      <SectionTitle>Data Quality Assessment</SectionTitle>
                      <span style={{ fontSize: "0.75rem", fontWeight: 700, color: dqPct >= 90 ? "#4ADE80" : dqPct >= 75 ? "#FCD34D" : "#FCA5A5", fontFamily: "ui-monospace, monospace" }}>
                        {dqPct}% — {dqPct >= 90 ? "Excellent" : dqPct >= 75 ? "Good" : dqPct >= 60 ? "Moderate" : "Limited"}
                      </span>
                    </div>
                    <div style={{ height: 4, backgroundColor: "#334155", borderRadius: 2, marginBottom: "0.75rem" }}>
                      <div style={{ height: "100%", width: `${dqPct}%`, backgroundColor: dqPct >= 75 ? "#15803D" : dqPct >= 55 ? "#B45309" : "#B91C1C", borderRadius: 2 }} />
                    </div>
                    {(plan.data_quality_factors ?? []).length > 0 && (
                      <ul style={{ display: "flex", flexDirection: "column", gap: "0.25rem", margin: 0, padding: 0, listStyle: "none" }}>
                        {(plan.data_quality_factors ?? []).map((f: string, i: number) => (
                          <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", fontSize: "0.7rem", color: "#64748B" }}>
                            <span style={{ width: 3, height: 3, borderRadius: "50%", backgroundColor: "#64748B", flexShrink: 0, marginTop: 6 }} />
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

          {/* ── Workflow tab ──────────────────────────────────────────────── */}
          {activeTab === "workflow" && (
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
              <select className="bfsi-select" value={caseData.status} onChange={(e) => handleStatusUpdate(e.target.value)} disabled={updatingStatus} style={{ fontSize: "0.75rem" }}>
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

          {/* Assessment Reliability — renamed from Case Confidence */}
          <Panel>
            <SectionTitle>Assessment Reliability</SectionTitle>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
              <span style={{ fontSize: "0.75rem", fontWeight: 600, color: confColor }}>{reliabilityLabel}</span>
              <span style={{ fontSize: "0.95rem", fontWeight: 700, fontFamily: "ui-monospace, monospace", color: confColor }}>{confidencePct}%</span>
            </div>
            <div style={{ height: 5, backgroundColor: "#334155", borderRadius: 2, marginBottom: "0.625rem" }}>
              <div style={{ height: "100%", width: `${confidencePct}%`, backgroundColor: caseData.confidence_score >= 0.75 ? "#15803D" : caseData.confidence_score >= 0.55 ? "#B45309" : "#B91C1C", borderRadius: 2, transition: "width 0.5s" }} />
            </div>
            {((caseData as any).confidence_factors ?? []).length > 0 && (
              <ul style={{ display: "flex", flexDirection: "column", gap: "0.3rem", margin: 0, padding: 0, listStyle: "none" }}>
                {((caseData as any).confidence_factors ?? []).slice(0, 4).map((f: string, i: number) => (
                  <li key={i} style={{ display: "flex", alignItems: "flex-start", gap: "0.375rem", fontSize: "0.65rem", color: "#64748B" }}>
                    <CheckCircle style={{ width: 10, height: 10, color: "#15803D", flexShrink: 0, marginTop: 2 }} />
                    {f}
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          {/* Case Processing — agent execution summary */}
          <Panel>
            <SectionTitle>Case Processing</SectionTitle>
            <InfoRow label="Analysis"      value={ariaVersion} />
            <InfoRow label="Investigation" value={iiaVersion} />
            <InfoRow label="Tools Used"    value={toolsUsed || "—"} />
            {execTimeSec && <InfoRow label="Exec Time" value={`${execTimeSec}s`} />}
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
          <button onClick={() => setLightbox(null)} style={{ position: "absolute", top: "1rem", right: "1rem", background: "none", border: "none", cursor: "pointer", color: "#94A3B8" }}>
            <X style={{ width: 24, height: 24 }} />
          </button>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={lightbox} alt="Evidence" style={{ maxWidth: "100%", maxHeight: "90vh", objectFit: "contain", borderRadius: 4 }} onClick={(e) => e.stopPropagation()} />
        </div>
      )}
    </>
  );
}
