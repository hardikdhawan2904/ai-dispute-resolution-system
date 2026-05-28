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
  | "VELOCITY_BREACH";

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

// ── UI Helper Types ────────────────────────────────────────────────────────────

export interface FormErrors {
  [field: string]: string;
}

export type ApiStatus = "idle" | "loading" | "success" | "error";
