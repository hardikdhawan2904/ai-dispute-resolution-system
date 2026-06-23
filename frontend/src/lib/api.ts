import axios from "axios";
import type {
  DisputeSubmissionInput,
  CasesListResponse,
  DashboardStats,
  DisputeCase,
  AuditLog,
  WorkflowState,
  CaseNote,
  DocumentRequest,
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

export async function getDocumentRequirements(
  disputeReason: string,
  fraudSelected: boolean,
  amount: number,
): Promise<{ category: string; required_documents: string[] } | null> {
  try {
    const res = await api.get<{ category: string; required_documents: string[] }>(
      "/api/disputes/document-requirements",
      { params: { dispute_reason: disputeReason, fraud_selected: fraudSelected, amount } },
    );
    return res.data;
  } catch {
    return null;
  }
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

// ── Disputes ──────────────────────────────────────────────────────────────────

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
  const res = await api.get<CasesListResponse>("/api/disputes/cases", { params, timeout: 120_000 });
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

// ── Ops — Document requests ───────────────────────────────────────────────────

export async function createDocumentRequest(
  caseId: string,
  requestedBy: string,
  documentType: string,
  description?: string,
  dueDate?: string,
  notify: boolean = true,
  notifyDocs?: string[],
): Promise<DocumentRequest> {
  const res = await api.post<DocumentRequest>(`/api/ops/cases/${caseId}/document-requests`, {
    requested_by: requestedBy,
    document_type: documentType,
    description,
    due_date: dueDate,
    notify,
    notify_docs: notifyDocs,
  });
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

// ── Communications (Agent 6 — CCA) ───────────────────────────────────────────

export interface CommunicationLog {
  id:                number;
  case_id:           string;
  notification_type: string;
  recipient:         string;
  subject:           string;
  body:              string;
  status:            "SENT" | "FAILED" | "PENDING";
  sent_at:           string | null;
  created_at:        string;
}

export async function getCommunications(caseId: string): Promise<{ case_id: string; total: number; communications: CommunicationLog[] }> {
  const res = await api.get(`/api/communications/${caseId}`);
  return res.data;
}

export async function sendCommunication(
  caseId: string,
  notificationType: string,
  context?: Record<string, unknown>,
): Promise<{ case_id: string; result: CommunicationLog }> {
  const res = await api.post(`/api/communications/${caseId}/send`, {
    notification_type: notificationType,
    context: context ?? {},
  });
  return res.data;
}
