"use client";
import { getRiskTagSeverity } from "@/lib/utils";

const TAG_LABELS: Record<string, string> = {
  HIGH_VALUE_TRANSACTION:    "High Value Transaction",
  INTERNATIONAL_TRANSACTION: "International Transaction",
  POSSIBLE_FRAUD:            "Possible Fraud",
  DUPLICATE_PAYMENT:         "Duplicate Payment",
  FRIENDLY_FRAUD_RISK:       "Friendly Fraud Pattern",
  HIGH_PRIORITY_CASE:        "High Priority",
  OTP_VERIFIED:              "OTP Shared",
  DEVICE_MISMATCH:           "Device Mismatch",
  SUSPICIOUS_BEHAVIOR:       "Suspicious Behaviour",
  CARD_NOT_PRESENT:          "Card Not Present",
  RECURRING_DISPUTE:         "Recurring Charge",
  MERCHANT_BLACKLISTED:      "Blacklisted Merchant",
  VELOCITY_BREACH:           "Velocity Breach",
  AI_UNAVAILABLE:            "Manual Review Required",
};

const SEVERITY_CONFIG = {
  critical: { label: "Critical",      bg: "#FEF2F2", text: "#991B1B", border: "#FECACA", dot: "#B91C1C" },
  warning:  { label: "Moderate",      bg: "#FFFBEB", text: "#92400E", border: "#FDE68A", dot: "#B45309" },
  info:     { label: "Informational", bg: "#EFF6FF", text: "#1D4ED8", border: "#BFDBFE", dot: "#2563EB" },
} as const;

interface RiskTagsProps {
  tags: string[];
  compact?: boolean;
}

export default function RiskTags({ tags, compact = false }: RiskTagsProps) {
  if (!tags || tags.length === 0) {
    return <span className="text-xs text-slate-500">No risk indicators identified</span>;
  }

  const grouped: Record<"critical" | "warning" | "info", string[]> = { critical: [], warning: [], info: [] };
  tags.forEach((tag) => { grouped[getRiskTagSeverity(tag)].push(tag); });

  if (compact) {
    return (
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag) => {
          const sev = getRiskTagSeverity(tag);
          const cfg = SEVERITY_CONFIG[sev];
          return (
            <span
              key={tag}
              style={{ background: cfg.bg, color: cfg.text, borderColor: cfg.border }}
              className="border rounded-[3px] px-2 py-0.5 text-[10.5px] font-semibold"
            >
              {TAG_LABELS[tag] ?? tag.replace(/_/g, " ")}
            </span>
          );
        })}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3.5">
      {(["critical", "warning", "info"] as const).map((sev) => {
        const items = grouped[sev];
        if (items.length === 0) return null;
        const cfg = SEVERITY_CONFIG[sev];
        return (
          <div key={sev}>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">
              {cfg.label}
            </div>
            <div className="flex flex-col gap-1">
              {items.map((tag) => (
                <div
                  key={tag}
                  style={{ background: cfg.bg, borderColor: cfg.border }}
                  className="flex items-center gap-2 px-2.5 py-1.5 border rounded-[3px]"
                >
                  <div
                    style={{ backgroundColor: cfg.dot }}
                    className="w-1.5 h-1.5 rounded-full shrink-0"
                  />
                  <span
                    style={{ color: cfg.text }}
                    className="text-[11.5px] font-medium"
                  >
                    {TAG_LABELS[tag] ?? tag.replace(/_/g, " ")}
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
