import axios from "axios";
import type {
  DisputeSubmissionInput,
  DisputeSubmissionResponse,
  CasesListResponse,
  DashboardStats,
  DisputeCase,
  AuditLog,
  WorkflowState,
  CaseNote,
  DocumentRequest,
  TimelineEntry,
  RiskIndicator,
  QueueSummary,
  OpsAnalytics,
} from "@/types";
import type { AuthUser } from "@/lib/auth";
import { getToken } from "@/lib/auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 60_000,
});

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers["Authorization"] = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const message =
      err.response?.data?.detail?.message ??
      err.response?.data?.detail ??
      err.message ??
      "Unknown error";
    return Promise.reject(new Error(typeof message === "string" ? message : JSON.stringify(message)));
  }
);

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(email: string, password: string): Promise<AuthUser> {
  const res = await api.post<{
    access_token: string;
    role: string;
    name: string;
    email: string;
    customer_id?: string | null;
  }>("/auth/login", { email, password });
  const d = res.data;
  return {
    access_token: d.access_token,
    role: d.role as AuthUser["role"],
    name: d.name,
    email: d.email,
    customer_id: d.customer_id,
  };
}

// ── Customer lookup ───────────────────────────────────────────────────────────

export interface BankCustomer {
  customer_id: string;
  full_name: string;
  email: string;
  phone: string;
}

export async function lookupCustomer(customerId: string): Promise<BankCustomer | null> {
  try {
    const res = await api.get<BankCustomer>(`/api/customer/lookup/${customerId.toUpperCase()}`);
    return res.data;
  } catch {
    return null;
  }
}

export interface BankTransaction {
  transaction_id:   string;
  customer_id:      string;
  merchant_name:    string;
  amount:           number;
  currency:         string;
  transaction_type: string;
  transaction_date: string | null;
  status:           string;
}

export async function lookupTransaction(transactionId: string): Promise<BankTransaction | null> {
  try {
    const res = await api.get<BankTransaction>(
      `/api/customer/lookup/transaction/${transactionId.toUpperCase()}`
    );
    return res.data;
  } catch {
    return null;
  }
}

// ── Internal bank disputes ────────────────────────────────────────────────────

export async function submitDispute(data: DisputeSubmissionInput): Promise<DisputeSubmissionResponse> {
  const res = await api.post<DisputeSubmissionResponse>("/api/disputes/submit", data);
  return res.data;
}

export async function submitDisputePublic(data: DisputeSubmissionInput): Promise<{
  success: boolean;
  case_id: string;
  message: string;
}> {
  const res = await api.post("/api/disputes/submit-public", data, { timeout: 90_000 });
  return res.data;
}

export async function listCases(params?: {
  skip?: number;
  limit?: number;
  status?: string;
  priority?: string;
  category?: string;
  fraud_only?: boolean;
}): Promise<CasesListResponse> {
  const res = await api.get<CasesListResponse>("/api/disputes/cases", { params });
  return res.data;
}

export async function getCase(caseId: string): Promise<DisputeCase> {
  const res = await api.get<DisputeCase>(`/api/disputes/cases/${caseId}`);
  return res.data;
}

export async function getDashboardStats(): Promise<DashboardStats> {
  const res = await api.get<DashboardStats>("/api/disputes/stats");
  return res.data;
}

export async function updateCaseStatus(
  caseId: string,
  status: string,
  actor = "operations_team",
  note?: string
): Promise<DisputeCase> {
  const res = await api.put<DisputeCase>(`/api/disputes/cases/${caseId}/status`, { status, actor, note });
  return res.data;
}

export async function getAuditLogs(caseId: string): Promise<{ case_id: string; audit_logs: AuditLog[] }> {
  const res = await api.get(`/api/disputes/cases/${caseId}/audit-logs`);
  return res.data;
}

export async function getWorkflowStates(caseId: string): Promise<{ case_id: string; workflow_states: WorkflowState[] }> {
  const res = await api.get(`/api/disputes/cases/${caseId}/workflow-states`);
  return res.data;
}

// ── Customer portal ───────────────────────────────────────────────────────────

export interface CustomerDispute {
  case_id: string;
  transaction_id: string;
  transaction_type: string;
  merchant: string;
  amount: number;
  currency: string;
  transaction_date?: string;
  status: string;
  created_at: string;
  updated_at?: string;
}

export async function customerSubmitDispute(data: DisputeSubmissionInput): Promise<{
  success: boolean;
  case_id: string;
  message: string;
  dispute_case: CustomerDispute;
}> {
  const res = await api.post("/api/customer/disputes/submit", data);
  return res.data;
}

export async function customerListDisputes(): Promise<CustomerDispute[]> {
  const res = await api.get<CustomerDispute[]>("/api/customer/disputes");
  return res.data;
}

export async function customerGetDispute(caseId: string): Promise<CustomerDispute> {
  const res = await api.get<CustomerDispute>(`/api/customer/disputes/${caseId}`);
  return res.data;
}

// ── Health ────────────────────────────────────────────────────────────────────

export async function healthCheck(): Promise<{ status: string }> {
  const res = await api.get("/health");
  return res.data;
}

// ── Ops — Case notes ──────────────────────────────────────────────────────────

export async function getCaseNotes(caseId: string, includeInternal = true): Promise<CaseNote[]> {
  const res = await api.get(`/api/ops/cases/${caseId}/notes`, { params: { include_internal: includeInternal } });
  return res.data.notes;
}

export async function addCaseNote(caseId: string, analyst: string, note: string, isInternal = true): Promise<CaseNote> {
  const res = await api.post<CaseNote>(`/api/ops/cases/${caseId}/notes`, { analyst, note, is_internal: isInternal });
  return res.data;
}

// ── Ops — Document requests ───────────────────────────────────────────────────

export async function getDocumentRequests(caseId: string): Promise<DocumentRequest[]> {
  const res = await api.get(`/api/ops/cases/${caseId}/document-requests`);
  return res.data.requests;
}

export async function createDocumentRequest(
  caseId: string,
  requestedBy: string,
  documentType: string,
  description?: string,
  dueDate?: string,
): Promise<DocumentRequest> {
  const res = await api.post<DocumentRequest>(`/api/ops/cases/${caseId}/document-requests`, {
    requested_by: requestedBy,
    document_type: documentType,
    description,
    due_date: dueDate,
  });
  return res.data;
}

export async function fulfillDocumentRequest(requestId: number): Promise<DocumentRequest> {
  const res = await api.post<DocumentRequest>(`/api/ops/cases/document-requests/${requestId}/fulfill`);
  return res.data;
}

// ── Ops — Case lock ───────────────────────────────────────────────────────────

export async function checkCaseLock(caseId: string): Promise<{ locked: boolean; locked_by?: string; expires_at?: string }> {
  const res = await api.get(`/api/ops/cases/${caseId}/lock`);
  return res.data;
}

export async function acquireCaseLock(caseId: string, analyst: string): Promise<{ acquired: boolean; locked_by?: string; expires_at?: string; error?: string }> {
  const res = await api.post(`/api/ops/cases/${caseId}/lock`, { analyst });
  return res.data;
}

export async function releaseCaseLock(caseId: string, analyst: string): Promise<{ released: boolean }> {
  const res = await api.delete(`/api/ops/cases/${caseId}/lock`, { params: { analyst } });
  return res.data;
}

// ── Ops — Analyst actions ─────────────────────────────────────────────────────

export async function performAnalystAction(
  caseId: string,
  action: string,
  analyst: string,
  options?: { note?: string; new_assignee?: string; new_queue?: string },
): Promise<DisputeCase> {
  const res = await api.post<DisputeCase>(`/api/ops/cases/${caseId}/actions`, {
    action,
    analyst,
    note: options?.note,
    new_assignee: options?.new_assignee,
    new_queue: options?.new_queue,
  });
  return res.data;
}

// ── Ops — Investigation timeline ──────────────────────────────────────────────

export async function getCaseTimeline(caseId: string): Promise<TimelineEntry[]> {
  const res = await api.get(`/api/ops/cases/${caseId}/timeline`);
  return res.data.timeline;
}

// ── Ops — Risk explanation ────────────────────────────────────────────────────

export async function getCaseRiskExplanation(caseId: string): Promise<{ risk_indicators: RiskIndicator[]; investigation_summary: string }> {
  const res = await api.get(`/api/ops/cases/${caseId}/risk-explanation`);
  return res.data;
}

// ── Ops — Re-analyse ──────────────────────────────────────────────────────────

export async function reanalyseCase(caseId: string): Promise<DisputeCase> {
  const res = await api.post(`/api/ops/cases/${caseId}/reanalyse`, {}, { timeout: 300_000 });
  return res.data;
}

// ── Ops — Uploaded evidence ───────────────────────────────────────────────────

export interface CaseUploadFile {
  name: string;
  url: string;
  is_image: boolean;
}

export async function getCaseUploads(caseId: string): Promise<CaseUploadFile[]> {
  const res = await api.get<{ case_id: string; files: CaseUploadFile[] }>(`/api/ops/cases/${caseId}/uploads`);
  return res.data.files;
}

export async function analyseUploads(caseId: string): Promise<{ analysed: number; files: CaseUploadFile[] }> {
  const res = await api.post<{ analysed: number; files: CaseUploadFile[] }>(`/api/ops/cases/${caseId}/uploads/analyse`, {}, { timeout: 120_000 });
  return res.data;
}

// ── Ops — Advanced search ─────────────────────────────────────────────────────

export async function searchCases(params: {
  query?: string;
  status?: string;
  priority?: string;
  category?: string;
  queue?: string;
  analyst?: string;
  fraud_only?: boolean;
  manual_review_only?: boolean;
  sla_breached_only?: boolean;
  min_amount?: number;
  max_amount?: number;
  skip?: number;
  limit?: number;
}): Promise<CasesListResponse> {
  const res = await api.post<CasesListResponse>("/api/ops/cases/search", params);
  return res.data;
}

// ── Ops — Analytics ───────────────────────────────────────────────────────────

export async function getOpsAnalytics(): Promise<OpsAnalytics> {
  const res = await api.get<OpsAnalytics>("/api/ops/analytics");
  return res.data;
}

// ── Ops — Queues ──────────────────────────────────────────────────────────────

export async function listQueues(): Promise<QueueSummary[]> {
  const res = await api.get<{ queues: QueueSummary[] }>("/api/ops/queues");
  return res.data.queues;
}

export async function getQueueCases(queueName: string, skip = 0, limit = 50): Promise<{ queue: string; display: string; total: number; cases: DisputeCase[] }> {
  const res = await api.get(`/api/ops/queues/${queueName}/cases`, { params: { skip, limit } });
  return res.data;
}
