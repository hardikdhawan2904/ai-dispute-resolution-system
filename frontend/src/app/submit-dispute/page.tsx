"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { Shield, Lock } from "lucide-react";

import { formSchema, FormValues } from "./schema";
import { TX_CONFIG } from "./config";
import StepIndicator from "./components/StepIndicator";
import Step1 from "./components/Step1";
import Step2 from "./components/Step2";
import Step3 from "./components/Step3";
import Step4 from "./components/Step5";
import Step5 from "./components/Step6";
import TrackDispute from "./components/TrackDispute";

// ── Step config ────────────────────────────────────────────────────────────────

const STEPS = [
  {
    id: 1,
    label: "Customer",
    fields: ["customer_name", "customer_id", "email", "phone"] as (keyof FormValues)[],
  },
  {
    id: 2,
    label: "Transaction",
    fields: [
      "transaction_id",
      "transaction_type",
      "merchant",
      "amount",
      "transaction_date",
    ] as (keyof FormValues)[],
  },
  {
    id: 3,
    label: "Dispute",
    fields: ["dispute_reason", "customer_comment"] as (keyof FormValues)[],
  },
  { id: 4, label: "Documents", fields: [] as (keyof FormValues)[] },
  { id: 5, label: "Review",    fields: [] as (keyof FormValues)[] },
];

// ── Main page ──────────────────────────────────────────────────────────────────

export default function SubmitDisputePage() {
  const [activeTab,     setActiveTab]     = useState<"raise" | "track">("raise");
  const [trackedCaseId, setTrackedCaseId] = useState<string | null>(null);
  const [step,          setStep]          = useState(1);
  const [files,         setFiles]         = useState<File[]>([]);
  const [submitting,    setSubmitting]    = useState(false);
  const [apiError,      setApiError]      = useState("");

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      customer_name: "",
      customer_id: "",
      email: "",
      phone: "",
      transaction_id: "",
      merchant: "",
      transaction_date: "",
      dispute_reason: "",
      customer_comment: "",
      currency: "INR",
      fraud_selected: false,
      is_international: false,
      cash_dispensed: false,
      partial_cash: false,
      otp_received: false,
      card_blocked: false,
      bank_contacted: false,
      transaction_location: "",
      otp_shared: false,
      device_lost: false,
      bank_impersonation: false,
      remote_access: false,
      phishing_link: false,
      card_lost: false,
      sim_swap_suspected: false,
      screen_sharing: false,
      unknown_beneficiary: false,
      upi_collect_fraud: false,
    },
    mode: "onBlur",
    reValidateMode: "onChange",
  });

  const txType   = form.watch("transaction_type");
  const txConfig = txType ? TX_CONFIG[txType] : null;

  const completedSteps = Array.from({ length: step - 1 }, (_, i) => i + 1);

  async function handleNext() {
    const stepData = STEPS[step - 1];
    const valid =
      stepData.fields.length === 0 ||
      (await form.trigger(stepData.fields));
    if (valid) setStep(step + 1);
  }

  async function handleSubmit() {
    setSubmitting(true);
    setApiError("");
    try {
      const values = form.getValues();

      const coreFieldKeys = new Set([
        "customer_name", "customer_id", "email", "phone",
        "transaction_id", "transaction_type", "merchant", "amount", "currency",
        "transaction_date", "transaction_time", "dispute_reason", "customer_comment",
        "fraud_selected",
      ]);

      const metadata: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(values)) {
        if (!coreFieldKeys.has(k) && v !== undefined && v !== "" && v !== false) {
          metadata[k] = v;
        }
      }

      const payload = {
        customer_name:       values.customer_name,
        customer_id:         values.customer_id,
        email:               values.email,
        phone:               values.phone,
        transaction_id:      values.transaction_id,
        transaction_type:    values.transaction_type,
        merchant:            values.merchant,
        amount:              values.amount,
        currency:            values.currency || "INR",
        transaction_date:    values.transaction_date,
        transaction_time:    values.transaction_time || "",
        customer_comment:    values.customer_comment,
        dispute_reason:      values.dispute_reason,
        fraud_selected:      values.fraud_selected,
        transaction_metadata: metadata,
      };

      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/disputes/submit-public`,
        {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body:    JSON.stringify(payload),
        }
      );

      const data = await res.json();
      if (!res.ok) {
        const detail = data?.detail;
        const msg =
          typeof detail === "object" && detail !== null && "message" in detail
            ? String((detail as { message: unknown }).message)
            : typeof detail === "string"
            ? detail
            : "Submission failed. Please try again.";
        throw new Error(msg);
      }

      // Upload any attached documents (best-effort — non-fatal on failure)
      if (files.length > 0) {
        try {
          const fd = new FormData();
          files.forEach((f) => fd.append("files", f));
          await fetch(
            `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/disputes/cases/${data.case_id}/documents`,
            { method: "POST", body: fd }
          );
        } catch {
          // Document upload failure does not block the submission success flow
        }
      }

      // Switch to the Track tab with the newly submitted case
      setTrackedCaseId(data.case_id);
      setActiveTab("track");
      form.reset();
      setFiles([]);
      setStep(1);

    } catch (e: unknown) {
      setApiError(
        e instanceof Error ? e.message : "An unexpected error occurred."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">

      {/* ── Header ──────────────────────────────────────────────────── */}
      <header className="bg-white border-b border-gray-100 px-6 py-4 sticky top-0 z-10">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-600 flex items-center justify-center">
              <Shield className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-gray-900">SecureBank</h1>
              <p className="text-xs text-gray-400">Dispute Resolution Centre</p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-green-600 bg-green-50 border border-green-100 rounded-full px-3 py-1.5">
            <Lock className="w-3 h-3" />
            <span className="font-medium hidden sm:inline">256-bit TLS Encrypted</span>
            <span className="font-medium sm:hidden">Secure</span>
          </div>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8">

        {/* ── Tab navigation ──────────────────────────────────────── */}
        <div className="flex border-b border-gray-200 mb-6">
          <button
            type="button"
            onClick={() => setActiveTab("raise")}
            className={[
              "px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
              activeTab === "raise"
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-gray-500 hover:text-gray-700",
            ].join(" ")}
          >
            Raise Dispute
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("track")}
            className={[
              "px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
              activeTab === "track"
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-gray-500 hover:text-gray-700",
            ].join(" ")}
          >
            Track Dispute
          </button>
        </div>

        {/* ── Raise Dispute tab ────────────────────────────────────── */}
        {activeTab === "raise" && (
          <>
            <div className="mb-6">
              <h2 className="text-xl font-bold text-gray-900">Raise a Dispute</h2>
              <p className="text-gray-500 text-sm mt-1">
                Complete all steps to submit your dispute. Our team will review
                your submission and contact you within 5–7 business days.
              </p>
            </div>

            <StepIndicator currentStep={step} completedSteps={completedSteps} />

            <div className="mt-6">
              {step === 1 && <Step1 form={form} />}
              {step === 2 && <Step2 form={form} config={txConfig} />}
              {step === 3 && (
                <Step3 form={form} reasons={txConfig?.disputeReasons ?? []} />
              )}
              {step === 4 && (
                <Step4
                  files={files}
                  onAdd={(newFiles) => setFiles((prev) => [...prev, ...newFiles])}
                  onRemove={(idx) => setFiles((prev) => prev.filter((_, i) => i !== idx))}
                  suggestions={txConfig?.uploadSuggestions ?? []}
                />
              )}
              {step === 5 && (
                <Step5
                  values={form.getValues()}
                  files={files}
                  txConfig={txConfig}
                  onSubmit={handleSubmit}
                  submitting={submitting}
                  apiError={apiError}
                />
              )}
            </div>

            <div className="flex items-center justify-between mt-6">
              <div>
                {step > 1 && (
                  <button
                    type="button"
                    onClick={() => setStep(step - 1)}
                    className="border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 px-6 py-2.5 rounded text-sm font-medium transition-colors"
                  >
                    Back
                  </button>
                )}
              </div>
              <div>
                {step < 5 && (
                  <button
                    type="button"
                    onClick={handleNext}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2.5 rounded text-sm font-semibold shadow-sm transition-colors"
                  >
                    Continue
                  </button>
                )}
              </div>
            </div>

            <p className="text-center text-xs text-gray-400 mt-4">
              Step {step} of 5
            </p>
          </>
        )}

        {/* ── Track Dispute tab ────────────────────────────────────── */}
        {activeTab === "track" && (
          <TrackDispute
            key={trackedCaseId || "empty"}
            initialCaseId={trackedCaseId || undefined}
          />
        )}

      </main>
    </div>
  );
}
