import axios from "axios";
import type {
  DisputeSubmissionInput,
  DisputeSubmissionResponse,
  CasesListResponse,
  DashboardStats,
  DisputeCase,
  AuditLog,
  WorkflowState,
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
