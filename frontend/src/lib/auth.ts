const TOKEN_KEY = "bfsi_token";
const USER_KEY  = "bfsi_user";

export type UserRole =
  | "CUSTOMER"
  | "FRAUD_ANALYST"
  | "DISPUTE_INVESTIGATOR"
  | "COMPLIANCE_OFFICER"
  | "OPERATIONS_ADMIN";

export interface AuthUser {
  email: string;
  name: string;
  role: UserRole;
  customer_id?: string | null;
  access_token: string;
}

export function saveAuth(user: AuthUser): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, user.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch { return null; }
}

export function clearAuth(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isAuthenticated(): boolean { return !!getToken(); }

export function isBankStaff(): boolean {
  const user = getUser();
  if (!user) return false;
  return ["FRAUD_ANALYST","DISPUTE_INVESTIGATOR","COMPLIANCE_OFFICER","OPERATIONS_ADMIN"].includes(user.role);
}

export function isCustomer(): boolean { return getUser()?.role === "CUSTOMER"; }

export function getPostLoginRedirect(role: UserRole): string {
  switch (role) {
    case "CUSTOMER":              return "/submit-dispute";
    case "FRAUD_ANALYST":         return "/internal-review";
    case "DISPUTE_INVESTIGATOR":  return "/internal-review";
    case "COMPLIANCE_OFFICER":    return "/internal-review";
    case "OPERATIONS_ADMIN":      return "/internal-review";
    default:                      return "/login";
  }
}

export const ROLE_LABEL: Record<UserRole, string> = {
  CUSTOMER:              "Customer",
  FRAUD_ANALYST:         "Fraud Analyst",
  DISPUTE_INVESTIGATOR:  "Investigator",
  COMPLIANCE_OFFICER:    "Compliance Officer",
  OPERATIONS_ADMIN:      "Operations Admin",
};
