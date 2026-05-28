"use client";
import { CheckCircle, Circle, AlertCircle, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CaseStatus } from "@/types";

const WORKFLOW_STAGES: { key: CaseStatus; label: string; description: string }[] = [
  { key: "Dispute Raised",       label: "Dispute Raised",       description: "Customer complaint registered" },
  { key: "Under Investigation",  label: "Under Investigation",  description: "AI analysis initiated" },
  { key: "Pending Documents",    label: "Pending Documents",    description: "Additional info required" },
  { key: "Escalated",            label: "Escalated",            description: "Routed to senior team" },
  { key: "Resolved",             label: "Resolved",             description: "Case closed with resolution" },
];

const STATUS_ORDER: Record<string, number> = {
  "Dispute Raised": 0,
  "Under Investigation": 1,
  "Pending Documents": 2,
  "Escalated": 3,
  "Resolved": 4,
  "Rejected": 4,
  "Closed": 4,
};

interface WorkflowStatusProps {
  status: CaseStatus;
  workflowReady: boolean;
}

export default function WorkflowStatus({ status, workflowReady }: WorkflowStatusProps) {
  const currentIndex = STATUS_ORDER[status] ?? 0;

  return (
    <div className="space-y-4">
      {/* Workflow Ready Badge */}
      <div className="flex items-center gap-2">
        <div className={cn(
          "inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border",
          workflowReady
            ? "text-green-400 bg-green-400/10 border-green-400/30"
            : "text-orange-400 bg-orange-400/10 border-orange-400/30"
        )}>
          {workflowReady ? <CheckCircle className="w-3.5 h-3.5" /> : <Clock className="w-3.5 h-3.5" />}
          {workflowReady ? "Workflow Ready" : "Workflow Pending"}
        </div>
      </div>

      {/* Stage Timeline */}
      <div className="relative">
        {WORKFLOW_STAGES.map((stage, i) => {
          const isCompleted = i < currentIndex;
          const isActive = i === currentIndex;
          const isFuture = i > currentIndex;

          // Handle terminal statuses
          const isRejected = status === "Rejected" && i === 4;
          const isClosed = status === "Closed" && i === 4;

          return (
            <div key={stage.key} className="flex gap-4 pb-4 last:pb-0">
              {/* Icon + connector */}
              <div className="flex flex-col items-center">
                <div className={cn(
                  "w-7 h-7 rounded-full border-2 flex items-center justify-center flex-shrink-0 transition-all",
                  isCompleted ? "bg-green-400/20 border-green-400" :
                  isActive    ? "bg-bfsi-gold/20 border-bfsi-gold animate-pulse" :
                  isRejected  ? "bg-red-400/20 border-red-400" :
                  "bg-bfsi-muted border-bfsi-border"
                )}>
                  {isCompleted ? (
                    <CheckCircle className="w-4 h-4 text-green-400" />
                  ) : isActive ? (
                    <div className="w-2.5 h-2.5 rounded-full bg-bfsi-gold" />
                  ) : isRejected ? (
                    <AlertCircle className="w-4 h-4 text-red-400" />
                  ) : (
                    <Circle className="w-4 h-4 text-bfsi-text-dim" />
                  )}
                </div>
                {i < WORKFLOW_STAGES.length - 1 && (
                  <div className={cn(
                    "w-0.5 flex-1 mt-1 min-h-[16px]",
                    isCompleted ? "bg-green-400/40" : "bg-bfsi-border"
                  )} />
                )}
              </div>

              {/* Label */}
              <div className="pt-0.5 pb-4">
                <div className={cn(
                  "text-sm font-medium",
                  isCompleted ? "text-green-400" :
                  isActive    ? "text-bfsi-gold" :
                  "text-bfsi-text-dim"
                )}>
                  {stage.label}
                </div>
                <div className="text-xs text-bfsi-text-dim mt-0.5">{stage.description}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
