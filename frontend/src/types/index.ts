// ── Core Domain Types ─────────────────────────────────────────────────────────

export type TransactionType =
  | "Credit Card"
  | "Debit Card"
  | "UPI"
  | "Net Banking"
  | "Wallet"
  | "POS"
  | "ATM"
  | "Online Purchase"
  | "International";

export type DisputeCategory =
  | "Unauthorized Transaction"
  | "Duplicate Transaction"
  | "Refund Not Received"
  | "Product Not Received"
  | "Subscription Abuse"
  | "ATM Cash Issue"
  | "Merchant Dispute"
  | "Friendly Fraud"
  | "Other";

export type Priority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export type CaseStatus =
  | "Dispute Raised"
  | "Under Investigation"
  | "Pending Documents"
  | "Escalated"
  | "Resolved"
  | "Rejected"
  | "Closed";

export type RiskTag =
  | "HIGH_VALUE_TRANSACTION"
  | "INTERNATIONAL_TRANSACTION"
  | "POSSIBLE_FRAUD"
  | "DUPLICATE_PAYMENT"
  | "FRIENDLY_FRAUD_RISK"
  | "HIGH_PRIORITY_CASE"
  | "OTP_VERIFIED"
  | "DEVICE_MISMATCH"
  | "SUSPICIOUS_BEHAVIOR"
  | "CARD_NOT_PRESENT"
  | "RECURRING_DISPUTE"
  | "MERCHANT_BLACKLISTED"
  | "VELOCITY_BREACH"
  | "AI_UNAVAILABLE";

// ── Request/Response Types ─────────────────────────────────────────────────────

export interface DisputeSubmissionInput {
  customer_name: string;
  customer_id: string;
  email: string;
  phone: string;
  transaction_id: string;
  transaction_type: TransactionType;
  merchant: string;
  amount: number;
  currency: string;
  transaction_date: string;
  transaction_time: string;
  customer_comment: string;
  dispute_reason: string;
  fraud_selected: boolean;
}

export type QueueName =
  | "FRAUD_OPS"
  | "ATM_INVESTIGATION"
  | "CHARGEBACK_TEAM"
  | "COMPLIANCE_REVIEW"
  | "HIGH_PRIORITY"
  | "GENERAL";

export interface InvestigationPlan {
  case_id: string;
  recommended_queue: string;
  queue_confidence?: number;
  queue_confidence_factors?: string[];
  investigation_complexity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  manual_review_required: boolean;
  customer_risk_profile: {
    previous_disputes: number;
    fraud_claims: number;
    last_dispute_days_ago: number;
    risk_level: string;
    assessment: string;
  };
  merchant_risk_profile: {
    merchant_risk: string;
    prior_complaints: number;
    fraud_rate: number;
    assessment: string;
  };
  duplicate_found: boolean;
  related_case_id: string | null;
  related_cases: {
    similar_cases: number;
    resolved_in_favor: number;
    resolved_against: number;
    resolution_rate: number;
  };
  required_documents: string[];
  recommended_steps: string[];
  investigation_reasoning?: string[];
  investigation_summary: string;
  confidence_score: number;
  // Change 4 — manual review explanation
  manual_review_reason?: string[];
  // Change 1 — tool decision trace
  tool_decisions?: Array<{ tool: string; reason: string }>;
  // Change 2 — investigation gaps
  investigation_gaps?: string[];
  // Change 3 — data quality
  data_quality_score?: number;
  data_quality_factors?: string[];
  // Investigation confidence (server-stamped deterministic score)
  investigation_confidence?: number;
  investigation_confidence_factors?: string[];
  // Change 6 — investigation coverage (server-stamped)
  investigation_coverage?: {
    customer_history_checked: boolean;
    merchant_history_checked: boolean;
    duplicate_check_performed: boolean;
    related_cases_reviewed: boolean;
    documents_recommended: boolean;
  };
  // Agent 2 audit trail
  tools_used?: string[];
  agent_metadata?: {
    agent_name: string;
    agent_version: string;
    model: string;
    execution_timestamp: string;
    execution_duration_ms: number;
  };
  metrics?: {
    total_duration_ms: number;
    llm_calls: number;
    tool_calls: number;
    retry_count: number;
  };
  created_at?: string;
}

export type SpecialistAgent =
  | "FRAUD_AGENT"
  | "MERCHANT_AGENT"
  | "EVIDENCE_AGENT"
  | "COMPLIANCE_AGENT";

export type WorkflowStatus = "READY" | "IN_PROGRESS" | "WAITING" | "COMPLETED" | "ESCALATED";
export type WorkflowComplexity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AnalystLevel = "JUNIOR" | "STANDARD" | "SENIOR" | "LEAD";
export type EscalationLevel = "CRITICAL" | "HIGH" | "MEDIUM" | null;

export interface WorkflowPlan {
  case_id: string;
  workflow_complexity: WorkflowComplexity;
  required_agents: SpecialistAgent[];
  workflow_path: SpecialistAgent[];
  workflow_status: WorkflowStatus;
  next_agent: SpecialistAgent | null;
  remaining_agents: SpecialistAgent[];
  completed_agents: SpecialistAgent[];
  escalation_required: boolean;
  escalation_level: EscalationLevel;
  manual_review_required: boolean;
  estimated_investigation_hours: number;
  analyst_level: AnalystLevel;
  workflow_reasoning: string[];
  tool_decisions: Array<{ tool: string; reason: string }>;
  tools_used: string[];
  agent_metadata?: {
    agent_name: string;
    agent_version: string;
    model: string;
    execution_timestamp: string;
    execution_duration_ms: number;
  };
  metrics?: {
    total_duration_ms: number;
    llm_calls: number;
    tool_calls: number;
    retry_count: number;
  };
  workflow_execution_id: string;
  workflow_version: string;
  fallback_mode?: boolean;
  failure_reason?: string | null;
  created_at?: string;
}

export interface EvidenceAssessment {
  case_id: string;
  evidence_completeness: number;
  evidence_strength: "HIGH" | "MEDIUM" | "LOW";
  evidence_strength_score: number;
  evidence_consistent: boolean;
  consistency_issues: string[];
  missing_documents: string[];
  recommended_document_requests: string[];
  bank_pending_documents?: string[];
  investigation_blocked: boolean;
  evidence_summary: string[];
  review_recommendation: string;
  manual_evidence_review: boolean;
  tool_decisions?: Array<{ tool: string; reason: string }>;
  tools_used?: string[];
  agent_metadata?: {
    agent_name: string;
    agent_version: string;
    model: string;
    execution_timestamp: string;
    execution_duration_ms: number;
  };
  metrics?: {
    total_duration_ms: number;
    llm_calls: number;
    tool_calls: number;
    retry_count: number;
  };
  fallback_mode?: boolean;
  failure_reason?: string | null;
  created_at?: string;
}

export interface DisputeCase {
  case_id: string;
  customer_id: string;
  customer_name?: string;
  email?: string;
  phone?: string;
  transaction_id: string;
  transaction_type: string;
  merchant: string;
  amount: number;
  currency: string;
  transaction_date?: string;
  transaction_time?: string;
  customer_comment?: string;
  dispute_reason?: string;
  fraud_selected: boolean;
  dispute_category?: DisputeCategory;
  fraud_suspicion: boolean;
  customer_intent_summary?: string;
  priority: Priority;
  confidence_score: number;
  risk_tags: RiskTag[];
  structured_reasoning?: string;
  status: CaseStatus;
  workflow_ready: boolean;
  // Enterprise fields
  assigned_queue?: QueueName;
  assigned_analyst?: string;
  priority_score: number;
  sla_deadline?: string;
  sla_breached: boolean;
  sla_paused_at?: string;
  duplicate_of?: string;
  requires_manual_review: boolean;
  manual_review_reason?: string;
  locked_by?: string;
  locked_at?: string;
  investigation_plan?: InvestigationPlan | null;
  // Agent 3 — WOA workflow plan
  workflow_plan?: WorkflowPlan | null;
  // Agent 4 — EIA evidence assessment
  evidence_assessment?: EvidenceAssessment | null;
  // Agent 1 fallback resilience
  fallback_mode?: boolean;
  failure_reason?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface CaseNote {
  id: number;
  case_id: string;
  analyst: string;
  note: string;
  is_internal: boolean;
  created_at: string;
}

export interface DocumentRequest {
  id: number;
  case_id: string;
  requested_by: string;
  document_type: string;
  description?: string;
  due_date?: string;
  fulfilled: boolean;
  fulfilled_at?: string;
  created_at: string;
}

export interface TimelineEntry {
  id: string;
  type: string;
  label: string;
  color: string;
  icon: string;
  actor: string;
  actor_type: "system" | "analyst" | "customer";
  message: string;
  payload: Record<string, unknown>;
  timestamp: string;
  source: string;
}

export interface RiskIndicator {
  tag: string;
  explanation: string;
}

export interface QueueSummary {
  queue: string;
  display: string;
  count: number;
  critical: number;
  sla_breached: number;
}

export interface OpsAnalytics {
  total_cases: number;
  open_cases: number;
  fraud_cases: number;
  critical_cases: number;
  sla_breached_cases: number;
  manual_review_cases: number;
  resolved_cases: number;
  resolution_rate: number;
  new_cases_7d: number;
  new_cases_30d: number;
  avg_confidence_score: number;
  by_queue: Record<string, number>;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  by_category: Record<string, number>;
  // Agent 4 — EIA evidence metrics
  evidence_reviews_pending?: number;
  evidence_reviews_completed?: number;
  blocked_investigations?: number;
  avg_evidence_completeness?: number;
}

export interface DisputeSubmissionResponse {
  success: boolean;
  case_id: string;
  message: string;
  dispute_case: DisputeCase;
}

export interface CasesListResponse {
  total: number;
  cases: DisputeCase[];
}

export interface DashboardStats {
  total_cases: number;
  open_cases: number;
  fraud_cases: number;
  critical_cases: number;
  avg_confidence_score: number;
  cases_by_category: Record<string, number>;
  cases_by_priority: Record<string, number>;
  cases_by_status: Record<string, number>;
  recent_cases: DisputeCase[];
}

export interface AuditLog {
  id: number;
  case_id: string;
  event_type: string;
  stage?: string;
  actor: string;
  message?: string;
  created_at: string;
}

export interface WorkflowState {
  id: number;
  case_id: string;
  node_name: string;
  execution_time_ms?: number;
  success: boolean;
  error_message?: string;
  created_at: string;
}

