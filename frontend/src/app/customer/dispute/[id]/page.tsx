"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, CheckCircle, Clock, AlertCircle, Circle, FileText } from "lucide-react";
import { customerGetDispute, type CustomerDispute } from "@/lib/api";

const STATUS_FLOW = [
  { key: "Dispute Submitted",         label: "Submitted",       desc: "Your dispute has been received and logged." },
  { key: "Under Review",              label: "Under Review",    desc: "Our team is reviewing the details of your dispute." },
  { key: "Documents Requested",       label: "Docs Requested",  desc: "We need additional documents from you." },
  { key: "Investigation In Progress", label: "Investigating",   desc: "A dedicated investigator is handling your case." },
  { key: "Awaiting Resolution",       label: "Final Review",    desc: "Your case is in final review before resolution." },
  { key: "Resolved",                  label: "Resolved",        desc: "Your dispute has been resolved." },
];

const CUSTOMER_MESSAGES: Record<string, string> = {
  "Dispute Submitted":
    "Your dispute has been received. Our team will begin reviewing it shortly. You will hear from us within 2–3 business days.",
  "Under Review":
    "Your dispute is currently being reviewed by our operations team. We are examining the transaction details and will contact you if we need anything.",
  "Documents Requested":
    "We require additional supporting documents to process your dispute. Please visit the Uploads section to submit the required documents as soon as possible to avoid delays.",
  "Investigation In Progress":
    "A specialist is actively investigating your dispute. This process typically takes 5–7 business days. We appreciate your patience.",
  "Awaiting Resolution":
    "The investigation is complete and your case is under final review. A resolution will be communicated to you within 1–2 business days.",
  "Resolved":
    "Your dispute has been reviewed and a decision has been made. Please check your registered email or contact our support team for details about the resolution outcome.",
};

function StepIcon({ status }: { status: "done" | "active" | "pending" }) {
  if (status === "done")   return <CheckCircle className="w-5 h-5 text-green-500" />;
  if (status === "active") return <Clock className="w-5 h-5 text-blue-600" />;
  return <Circle className="w-5 h-5 text-gray-300" />;
}

export default function DisputeDetailPage() {
  const { id }   = useParams<{ id: string }>();
  const [dispute, setDispute] = useState<CustomerDispute | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");

  useEffect(() => {
    if (!id) return;
    customerGetDispute(id)
      .then(setDispute)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return (
    <div className="text-center py-16 text-gray-400">Loading dispute details...</div>
  );
  if (error) return (
    <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl p-4 text-sm">{error}</div>
  );
  if (!dispute) return null;

  const currentIdx = STATUS_FLOW.findIndex((s) => s.key === dispute.status);

  return (
    <div className="space-y-5">
      {/* Breadcrumb */}
      <Link href="/customer/disputes" className="inline-flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Back to My Disputes
      </Link>

      {/* Case header */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 mb-6">
          <div>
            <p className="text-xs text-gray-400 mb-1">Case Reference</p>
            <p className="font-mono font-semibold text-gray-900">{dispute.case_id}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-400 mb-1">Amount Disputed</p>
            <p className="text-2xl font-bold text-gray-900">
              {dispute.currency} {dispute.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div>
            <p className="text-xs text-gray-400 mb-0.5">Merchant</p>
            <p className="font-medium text-gray-900">{dispute.merchant}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-0.5">Type</p>
            <p className="font-medium text-gray-900">{dispute.transaction_type}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-0.5">Date</p>
            <p className="font-medium text-gray-900">{dispute.transaction_date ?? "—"}</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 mb-0.5">Submitted</p>
            <p className="font-medium text-gray-900">{new Date(dispute.created_at).toLocaleDateString("en-IN")}</p>
          </div>
        </div>
      </div>

      {/* Status timeline */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
        <h2 className="font-semibold text-gray-900 mb-6">Case Progress</h2>
        <div className="space-y-0">
          {STATUS_FLOW.map((step, i) => {
            const stepStatus = i < currentIdx ? "done" : i === currentIdx ? "active" : "pending";
            const isLast = i === STATUS_FLOW.length - 1;
            return (
              <div key={step.key} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <StepIcon status={stepStatus} />
                  {!isLast && (
                    <div className={`w-0.5 h-10 mt-1 ${stepStatus === "done" ? "bg-green-200" : "bg-gray-100"}`} />
                  )}
                </div>
                <div className="pb-8 last:pb-0 flex-1 min-w-0">
                  <p className={`text-sm font-semibold mb-0.5 ${stepStatus === "pending" ? "text-gray-400" : stepStatus === "active" ? "text-blue-700" : "text-gray-900"}`}>
                    {step.label}
                    {stepStatus === "active" && (
                      <span className="ml-2 text-xs bg-blue-100 text-blue-600 px-2 py-0.5 rounded-full font-medium">Current</span>
                    )}
                  </p>
                  {stepStatus !== "pending" && (
                    <p className="text-xs text-gray-500">{step.desc}</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Status message */}
      <div className="bg-blue-50 border border-blue-100 rounded-2xl p-5">
        <div className="flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-blue-600 mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold text-blue-900 text-sm mb-1">Status Update</p>
            <p className="text-blue-800 text-sm leading-relaxed">
              {CUSTOMER_MESSAGES[dispute.status] ?? "We are processing your dispute. Please check back soon."}
            </p>
          </div>
        </div>
      </div>

      {/* Documents requested CTA */}
      {dispute.status === "Documents Requested" && (
        <div className="bg-orange-50 border border-orange-200 rounded-2xl p-5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <FileText className="w-5 h-5 text-orange-600 shrink-0" />
            <div>
              <p className="font-semibold text-orange-900 text-sm">Documents Required</p>
              <p className="text-orange-700 text-sm">Please upload the requested documents to continue processing.</p>
            </div>
          </div>
          <Link href="/customer/uploads" className="bg-orange-600 text-white text-sm font-medium px-4 py-2 rounded-xl hover:bg-orange-700 transition-all whitespace-nowrap">
            Upload Now
          </Link>
        </div>
      )}

      {/* What to expect */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
        <h3 className="font-semibold text-gray-900 text-sm mb-3">What to Expect</h3>
        <div className="space-y-2 text-sm text-gray-600">
          <p>• Most disputes are resolved within <strong>7–10 business days</strong></p>
          <p>• You will receive email updates at each stage of the investigation</p>
          <p>• If we need documents, upload them promptly to avoid delays</p>
          <p>• For urgent matters, call our helpline: <strong>1800-000-0000</strong></p>
        </div>
      </div>
    </div>
  );
}
