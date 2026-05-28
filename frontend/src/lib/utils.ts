import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Priority, CaseStatus, RiskTag } from "@/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number, currency = "INR"): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(amount);
}

export function formatDate(dateString: string): string {
  if (!dateString) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  }).format(new Date(dateString));
}

export function formatConfidence(score: number): string {
  return `${(score * 100).toFixed(1)}%`;
}

export function getPriorityColor(priority: Priority): string {
  switch (priority) {
    case "CRITICAL": return "text-red-400 bg-red-400/10 border-red-400/30";
    case "HIGH":     return "text-orange-400 bg-orange-400/10 border-orange-400/30";
    case "MEDIUM":   return "text-yellow-400 bg-yellow-400/10 border-yellow-400/30";
    case "LOW":      return "text-green-400 bg-green-400/10 border-green-400/30";
    default:         return "text-slate-400 bg-slate-400/10 border-slate-400/30";
  }
}

export function getStatusColor(status: CaseStatus): string {
  switch (status) {
    case "Dispute Raised":      return "text-blue-400 bg-blue-400/10 border-blue-400/30";
    case "Under Investigation": return "text-yellow-400 bg-yellow-400/10 border-yellow-400/30";
    case "Pending Documents":   return "text-orange-400 bg-orange-400/10 border-orange-400/30";
    case "Escalated":           return "text-red-400 bg-red-400/10 border-red-400/30";
    case "Resolved":            return "text-green-400 bg-green-400/10 border-green-400/30";
    case "Rejected":            return "text-slate-400 bg-slate-400/10 border-slate-400/30";
    case "Closed":              return "text-slate-500 bg-slate-500/10 border-slate-500/30";
    default:                    return "text-slate-400 bg-slate-400/10 border-slate-400/30";
  }
}

export function getRiskTagColor(tag: string): string {
  const dangerTags = ["POSSIBLE_FRAUD", "OTP_VERIFIED", "DEVICE_MISMATCH", "SUSPICIOUS_BEHAVIOR"];
  const warningTags = ["HIGH_VALUE_TRANSACTION", "HIGH_PRIORITY_CASE", "INTERNATIONAL_TRANSACTION", "VELOCITY_BREACH"];
  if (dangerTags.includes(tag)) return "text-red-400 bg-red-400/10 border-red-400/30";
  if (warningTags.includes(tag)) return "text-orange-400 bg-orange-400/10 border-orange-400/30";
  return "text-slate-400 bg-slate-400/10 border-slate-400/30";
}

export function getConfidenceColor(score: number): string {
  if (score >= 0.8) return "text-green-400";
  if (score >= 0.6) return "text-yellow-400";
  if (score >= 0.4) return "text-orange-400";
  return "text-red-400";
}

export function getConfidenceLabel(score: number): string {
  if (score >= 0.85) return "Very High";
  if (score >= 0.70) return "High";
  if (score >= 0.55) return "Moderate";
  if (score >= 0.40) return "Low";
  return "Very Low";
}

export function truncate(str: string, maxLen: number): string {
  if (str.length <= maxLen) return str;
  return str.slice(0, maxLen - 3) + "...";
}
