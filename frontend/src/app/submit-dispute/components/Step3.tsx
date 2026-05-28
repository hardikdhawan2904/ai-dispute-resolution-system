"use client";

import { UseFormReturn, Controller } from "react-hook-form";
import { AlertCircle } from "lucide-react";
import { FormValues } from "../schema";
import { FTextarea } from "./FormControls";

// ── Fraud verification questions ───────────────────────────────────────────────

const FRAUD_QUESTIONS: Array<{ field: keyof FormValues; question: string }> = [
  {
    field: "otp_shared",
    question: "Did you share your OTP or PIN with another person?",
  },
  {
    field: "bank_impersonation",
    question: "Did you receive a call from someone claiming to represent the bank?",
  },
  {
    field: "remote_access",
    question: "Did you install a remote access application at someone's request?",
  },
  {
    field: "phishing_link",
    question: "Did you click on a link in an SMS, email, or message and enter your banking details?",
  },
  {
    field: "sim_swap_suspected",
    question: "Was your mobile service unexpectedly disrupted around the time of this transaction?",
  },
  {
    field: "screen_sharing",
    question: "Was screen sharing active on your device during this period?",
  },
  {
    field: "device_lost",
    question: "Was your registered mobile device lost or stolen before this transaction?",
  },
  {
    field: "card_lost",
    question: "Was your debit or credit card lost or stolen before this transaction?",
  },
  {
    field: "unknown_beneficiary",
    question: "Was an unrecognised beneficiary added to your account?",
  },
  {
    field: "upi_collect_fraud",
    question: "Did you approve a UPI collect request from an unverified source?",
  },
];

// ── Constants ──────────────────────────────────────────────────────────────────

const FALLBACK_REASONS = [
  "Unauthorised transaction",
  "Duplicate charge",
  "Refund not received",
  "Service not delivered",
  "Incorrect amount charged",
  "Other",
];

// ── Yes/No question row ────────────────────────────────────────────────────────

function YesNoQuestion({
  question,
  value,
  onChange,
  name,
}: {
  question: string;
  value: boolean | undefined;
  onChange: (v: boolean) => void;
  name: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-gray-100 last:border-0">
      <span className="text-sm text-gray-700 leading-snug flex-1">{question}</span>
      <div className="flex items-center gap-5 shrink-0">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="radio"
            name={name}
            checked={value === true}
            onChange={() => onChange(true)}
            className="w-3.5 h-3.5 text-blue-600 border-gray-300 focus:ring-1 focus:ring-blue-500 cursor-pointer"
          />
          <span className="text-sm text-gray-600">Yes</span>
        </label>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="radio"
            name={name}
            checked={value === false || value === undefined}
            onChange={() => onChange(false)}
            className="w-3.5 h-3.5 text-blue-600 border-gray-300 focus:ring-1 focus:ring-blue-500 cursor-pointer"
          />
          <span className="text-sm text-gray-600">No</span>
        </label>
      </div>
    </div>
  );
}

// ── Step3 ──────────────────────────────────────────────────────────────────────

interface Step3Props {
  form: UseFormReturn<FormValues>;
  reasons: string[];
}

export default function Step3({ form, reasons }: Step3Props) {
  const { control, watch, setValue, formState: { errors } } = form;

  const selectedReason  = watch("dispute_reason");
  const customerComment = watch("customer_comment");
  const fraudSelected   = watch("fraud_selected");
  const commentLen      = customerComment?.length ?? 0;

  const yesCount = FRAUD_QUESTIONS.filter(
    ({ field }) => watch(field) === true
  ).length;

  const displayReasons = reasons.length > 0 ? reasons : FALLBACK_REASONS;

  return (
    <div className="space-y-4">

      {/* ── Reason for Dispute ─────────────────────────────────────── */}
      <div className="bg-white border border-gray-200 rounded">
        <div className="px-4 py-3 border-b border-gray-100">
          <p className="text-xs font-semibold text-gray-700">Reason for Dispute</p>
          <p className="text-[11px] text-gray-400 mt-0.5">
            Select the category that best describes your complaint
          </p>
        </div>
        <div className="px-4 py-3 space-y-0.5">
          {displayReasons.map((reason) => {
            const isSelected = selectedReason === reason;
            return (
              <button
                key={reason}
                type="button"
                onClick={() => setValue("dispute_reason", reason, { shouldValidate: true })}
                className={[
                  "w-full flex items-center gap-3 px-3 py-2.5 rounded text-left transition-colors",
                  isSelected
                    ? "bg-blue-50 border border-blue-200"
                    : "border border-transparent hover:bg-gray-50",
                ].join(" ")}
              >
                <div className={[
                  "w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center",
                  isSelected ? "border-blue-600" : "border-gray-300",
                ].join(" ")}>
                  {isSelected && <div className="w-2 h-2 rounded-full bg-blue-600" />}
                </div>
                <span className={`text-sm ${isSelected ? "text-gray-900 font-medium" : "text-gray-600"}`}>
                  {reason}
                </span>
              </button>
            );
          })}
        </div>
        {errors.dispute_reason && (
          <div className="px-4 pb-3">
            <p className="flex items-center gap-1.5 text-xs text-red-600">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              {errors.dispute_reason.message}
            </p>
          </div>
        )}
      </div>

      {/* ── Case Description ───────────────────────────────────────── */}
      <div className="bg-white border border-gray-200 rounded">
        <div className="px-4 py-3 border-b border-gray-100">
          <p className="text-xs font-semibold text-gray-700">Case Description</p>
          <p className="text-[11px] text-gray-400 mt-0.5">
            Describe the disputed transaction in your own words
          </p>
        </div>
        <div className="px-4 py-4">
          <Controller
            control={control}
            name="customer_comment"
            render={({ field }) => (
              <FTextarea
                label=""
                placeholder="Describe what happened, including the date, merchant involved, and any steps already taken to resolve this."
                value={field.value ?? ""}
                onChange={field.onChange}
                rows={5}
                maxLength={2000}
                error={errors.customer_comment?.message}
              />
            )}
          />
          {commentLen > 0 && commentLen < 50 && (
            <p className="text-[11px] text-gray-400 mt-1.5">
              A complete description helps us process your case more efficiently.
            </p>
          )}
        </div>
      </div>

      {/* ── Unauthorised Transaction ────────────────────────────────── */}
      <div className={[
        "bg-white border rounded transition-colors duration-150",
        fraudSelected ? "border-amber-300" : "border-gray-200",
      ].join(" ")}>
        <div className={[
          "px-4 py-3 border-b transition-colors",
          fraudSelected ? "border-amber-200" : "border-gray-100",
        ].join(" ")}>
          <p className="text-xs font-semibold text-gray-700">Unauthorised Transaction</p>
        </div>

        <div className="px-4 py-4">
          {/* Declaration checkbox */}
          <Controller
            control={control}
            name="fraud_selected"
            render={({ field }) => (
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!field.value}
                  onChange={(e) => field.onChange(e.target.checked)}
                  className="mt-0.5 w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-1 focus:ring-blue-500 cursor-pointer shrink-0"
                />
                <div>
                  <p className="text-sm text-gray-800 font-medium leading-snug">
                    This transaction was not authorised by me
                  </p>
                  <p className="text-[11px] text-gray-400 mt-0.5">
                    Selecting this will initiate an unauthorised transaction review under applicable RBI guidelines.
                  </p>
                </div>
              </label>
            )}
          />

          {/* Expanded verification questions */}
          <div
            style={{ maxHeight: fraudSelected ? "2200px" : "0px" }}
            className="overflow-hidden transition-all duration-300"
          >
            <div className="mt-5 pt-4 border-t border-gray-100">
              <p className="text-xs font-semibold text-gray-700 mb-0.5">
                Transaction Verification
              </p>
              <p className="text-[11px] text-gray-400 mb-4">
                Please answer the following questions. Select all responses that apply.
              </p>

              <div className="border border-gray-200 rounded divide-y divide-gray-100">
                <div className="px-4 py-2 bg-gray-50 flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">Question</span>
                  <div className="flex items-center gap-7 pr-1">
                    <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">Yes</span>
                    <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide">No</span>
                  </div>
                </div>
                <div className="px-4">
                  {FRAUD_QUESTIONS.map(({ field, question }) => (
                    <Controller
                      key={field}
                      control={control}
                      name={field}
                      render={({ field: f }) => (
                        <YesNoQuestion
                          name={`fraud-${field}`}
                          question={question}
                          value={f.value as boolean | undefined}
                          onChange={(v) => f.onChange(v)}
                        />
                      )}
                    />
                  ))}
                </div>
              </div>

              {/* Additional details */}
              <div className="mt-5">
                <p className="text-xs font-semibold text-gray-700 mb-1">
                  Additional Details{" "}
                  <span className="text-gray-400 font-normal">(optional)</span>
                </p>
                <Controller
                  control={control}
                  name="fraud_additional_details"
                  render={({ field }) => (
                    <FTextarea
                      label=""
                      placeholder="Include any additional context — e.g., calls received, links clicked, or a timeline of events."
                      value={field.value ?? ""}
                      onChange={field.onChange}
                      rows={3}
                      maxLength={1000}
                    />
                  )}
                />
              </div>

              {/* Amber notice when multiple Yes answers */}
              {yesCount >= 2 && (
                <p className="mt-4 text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2.5 leading-relaxed">
                  Based on your responses, additional verification may be required. Our team may contact you for further information within 2–3 business days.
                </p>
              )}

              {/* RBI liability note */}
              <p className="mt-4 text-[11px] text-gray-400 leading-relaxed">
                Unauthorised transactions reported within 3 business days may qualify for limited liability protection, subject to investigation outcome, under RBI Circular RBI/2017-18/15.
              </p>
            </div>
          </div>

          {!fraudSelected && (
            <p className="mt-3 text-[11px] text-gray-400">
              Select only if this transaction was conducted without your knowledge or consent.
            </p>
          )}
        </div>
      </div>

    </div>
  );
}
