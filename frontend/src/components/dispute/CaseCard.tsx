"use client";
import Link from "next/link";
import { AlertTriangle, CreditCard, ArrowRight, Calendar } from "lucide-react";
import { cn, formatCurrency, formatDate, getPriorityColor, getStatusColor } from "@/lib/utils";
import RiskTags from "./RiskTags";
import ConfidenceScore from "./ConfidenceScore";
import type { DisputeCase } from "@/types";

interface CaseCardProps {
  case_data: DisputeCase;
}

export default function CaseCard({ case_data: c }: CaseCardProps) {
  const priorityClass = getPriorityColor(c.priority as any);
  const statusClass = getStatusColor(c.status as any);

  return (
    <Link href={`/ops/case/${c.case_id}`} className="block group">
      <div className={cn(
        "bfsi-card p-5 transition-all duration-200",
        "hover:border-bfsi-gold/30 hover:shadow-bfsi-glow",
        c.fraud_suspicion && "border-l-2 border-l-red-500",
        c.priority === "CRITICAL" && !c.fraud_suspicion && "border-l-2 border-l-orange-500",
      )}>

        {/* Header row */}
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-mono text-bfsi-text-dim">{c.case_id}</span>
              {c.fraud_suspicion && (
                <span className="flex items-center gap-1 text-xs text-red-400 bg-red-400/10 border border-red-400/20 px-1.5 py-0.5 rounded-full">
                  <AlertTriangle className="w-3 h-3" />
                  Fraud
                </span>
              )}
            </div>
            <div className="text-sm font-semibold text-bfsi-text">{c.customer_name || c.customer_id}</div>
            <div className="text-xs text-bfsi-text-dim mt-0.5">{c.merchant}</div>
          </div>

          <div className="text-right flex-shrink-0">
            <div className="text-lg font-bold text-bfsi-text font-mono">
              {formatCurrency(c.amount, c.currency)}
            </div>
            <div className="text-xs text-bfsi-text-dim">{c.transaction_type}</div>
          </div>
        </div>

        {/* Category + Priority + Status */}
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <span className="text-xs text-bfsi-text-muted bg-bfsi-muted px-2 py-0.5 rounded-md">
            {c.dispute_category || "Uncategorized"}
          </span>
          <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full border", priorityClass)}>
            {c.priority}
          </span>
          <span className={cn("text-xs px-2 py-0.5 rounded-full border", statusClass)}>
            {c.status}
          </span>
        </div>

        {/* Confidence score */}
        <div className="mb-4">
          <div className="text-[10px] text-bfsi-text-dim mb-1 uppercase tracking-wider">AI Confidence</div>
          <ConfidenceScore score={c.confidence_score} showLabel={false} size="sm" />
        </div>

        {/* Risk tags (compact) */}
        {c.risk_tags && c.risk_tags.length > 0 && (
          <div className="mb-3">
            <RiskTags tags={c.risk_tags.slice(0, 3)} compact />
            {c.risk_tags.length > 3 && (
              <span className="text-[10px] text-bfsi-text-dim ml-1">+{c.risk_tags.length - 3} more</span>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-3 border-t border-bfsi-border">
          <div className="flex items-center gap-1.5 text-xs text-bfsi-text-dim">
            <Calendar className="w-3 h-3" />
            {formatDate(c.created_at)}
          </div>
          <div className="flex items-center gap-1 text-xs text-bfsi-gold opacity-0 group-hover:opacity-100 transition-opacity">
            View Details
            <ArrowRight className="w-3 h-3" />
          </div>
        </div>
      </div>
    </Link>
  );
}
