"use client";

import { Check } from "lucide-react";

const STEPS = [
  { id: 1, label: "Customer" },
  { id: 2, label: "Transaction" },
  { id: 3, label: "Dispute" },
  { id: 4, label: "Documents" },
  { id: 5, label: "Review" },
];

interface StepIndicatorProps {
  currentStep: number;
  completedSteps: number[];
}

export default function StepIndicator({ currentStep, completedSteps }: StepIndicatorProps) {
  return (
    <div className="w-full">
      <div className="flex items-center justify-between">
        {STEPS.map((step, idx) => {
          const isCompleted = completedSteps.includes(step.id);
          const isCurrent   = currentStep === step.id;

          return (
            <div key={step.id} className="flex items-center flex-1">
              <div className="flex flex-col items-center">
                <div className={[
                  "w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold border-2 transition-all",
                  isCompleted ? "bg-blue-600 border-blue-600 text-white" :
                  isCurrent   ? "bg-white border-blue-600 text-blue-600" :
                                "bg-white border-gray-200 text-gray-400",
                ].join(" ")}>
                  {isCompleted ? <Check className="w-4 h-4" /> : <span>{idx + 1}</span>}
                </div>
                <span className={[
                  "mt-1.5 text-xs font-medium hidden sm:block",
                  isCurrent   ? "text-blue-600" :
                  isCompleted ? "text-gray-600" :
                                "text-gray-400",
                ].join(" ")}>
                  {step.label}
                </span>
              </div>

              {idx < STEPS.length - 1 && (
                <div className={`flex-1 h-0.5 mx-2 transition-colors ${
                  isCompleted ? "bg-blue-600" : "bg-gray-200"
                }`} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
