"use client";
import { AlertTriangle, Globe, DollarSign, Copy, ShieldAlert, Zap, Smartphone, Eye, CreditCard, RefreshCw, Ban, Activity } from "lucide-react";
import { cn, getRiskTagColor } from "@/lib/utils";
import type { RiskTag } from "@/types";

const TAG_META: Record<string, { label: string; icon: React.ElementType; description: string }> = {
  HIGH_VALUE_TRANSACTION:    { label: "High Value", icon: DollarSign, description: "Transaction amount exceeds ₹50,000" },
  INTERNATIONAL_TRANSACTION: { label: "International", icon: Globe, description: "Cross-border transaction" },
  POSSIBLE_FRAUD:            { label: "Possible Fraud", icon: ShieldAlert, description: "Strong fraud indicators present" },
  DUPLICATE_PAYMENT:         { label: "Duplicate", icon: Copy, description: "Potential duplicate charge" },
  FRIENDLY_FRAUD_RISK:       { label: "Friendly Fraud Risk", icon: Eye, description: "Customer may be filing false dispute" },
  HIGH_PRIORITY_CASE:        { label: "High Priority", icon: Zap, description: "Requires immediate attention" },
  OTP_VERIFIED:              { label: "OTP Shared", icon: Smartphone, description: "Customer shared OTP with third party" },
  DEVICE_MISMATCH:           { label: "Device Mismatch", icon: Smartphone, description: "Transaction from unrecognized device" },
  SUSPICIOUS_BEHAVIOR:       { label: "Suspicious", icon: AlertTriangle, description: "Unusual behavioral pattern detected" },
  CARD_NOT_PRESENT:          { label: "Card Not Present", icon: CreditCard, description: "Online transaction, no physical card" },
  RECURRING_DISPUTE:         { label: "Recurring", icon: RefreshCw, description: "Subscription or recurring charge" },
  MERCHANT_BLACKLISTED:      { label: "Blacklisted Merchant", icon: Ban, description: "Known problematic merchant" },
  VELOCITY_BREACH:           { label: "Velocity Breach", icon: Activity, description: "Multiple rapid transactions" },
};

interface RiskTagsProps {
  tags: string[];
  compact?: boolean;
}

export default function RiskTags({ tags, compact = false }: RiskTagsProps) {
  if (!tags || tags.length === 0) {
    return (
      <span className="text-xs text-bfsi-text-dim italic">No risk tags identified</span>
    );
  }

  return (
    <div className="flex flex-wrap gap-2">
      {tags.map((tag) => {
        const meta = TAG_META[tag] ?? { label: tag, icon: AlertTriangle, description: tag };
        const Icon = meta.icon;
        const colorClass = getRiskTagColor(tag);

        return (
          <div
            key={tag}
            title={meta.description}
            className={cn(
              "flex items-center gap-1.5 border rounded-full cursor-default transition-all duration-200",
              compact ? "px-2 py-0.5 text-[11px]" : "px-3 py-1 text-xs",
              colorClass
            )}
          >
            <Icon className={cn("flex-shrink-0", compact ? "w-3 h-3" : "w-3.5 h-3.5")} />
            <span className="font-medium whitespace-nowrap">{meta.label}</span>
          </div>
        );
      })}
    </div>
  );
}
