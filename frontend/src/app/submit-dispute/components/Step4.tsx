"use client";

import { UseFormReturn, Controller } from "react-hook-form";
import { FormValues } from "../schema";
import { FToggle, FTextarea, SectionCard } from "./FormControls";
import { ShieldAlert, Info } from "lucide-react";

interface Step4Props {
  form: UseFormReturn<FormValues>;
}

const FRAUD_QUESTIONS: Array<{
  field: keyof FormValues;
  label: string;
  description: string;
}> = [
  {
    field: "otp_shared",
    label: "Was a One-Time Password (OTP) shared with anyone?",
    description:
      "Banks never ask for OTP. Sharing OTP constitutes consent under RBI guidelines.",
  },
  {
    field: "device_lost",
    label: "Was your phone or card lost or stolen around the time of the transaction?",
    description:
      "Loss or theft of the registered device is a key fraud indicator.",
  },
  {
    field: "bank_impersonation",
    label: "Did anyone impersonate a bank employee or call claiming to be from the bank?",
    description:
      "Vishing (voice phishing) is the most common fraud vector in India.",
  },
  {
    field: "remote_access",
    label: "Was a remote access or screen-sharing app installed? (e.g. AnyDesk, TeamViewer)",
    description:
      "Remote access apps allow fraudsters to initiate transactions on your device.",
  },
  {
    field: "phishing_link",
    label: "Did you click a link from an unknown SMS, email, or WhatsApp message?",
    description:
      "Phishing links often redirect to fake banking portals to steal credentials.",
  },
  {
    field: "card_lost",
    label: "Was your physical card lost or stolen?",
    description:
      "A lost or stolen card should be blocked immediately via net banking or the bank helpline.",
  },
];

export default function Step4({ form }: Step4Props) {
  const {
    control,
    formState: { errors },
  } = form;

  return (
    <div className="space-y-4">
      {/* Red alert header */}
      <div className="bg-red-50 border border-red-200 rounded-2xl p-5">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center shrink-0">
            <ShieldAlert className="w-5 h-5 text-red-600" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-red-800 uppercase tracking-wide">
              FRAUD ALERT — Additional Information Required
            </h3>
            <p className="text-sm text-red-600 mt-1">
              Please answer the following questions to help us investigate your fraud claim. All information is confidential.
            </p>
          </div>
        </div>
      </div>

      {/* Fraud indicator toggles */}
      <SectionCard
        title="Fraud Indicators"
        subtitle="Answer each question honestly — this helps us investigate faster"
      >
        <div className="space-y-3">
          {FRAUD_QUESTIONS.map(({ field, label, description }) => (
            <Controller
              key={field}
              control={control}
              name={field}
              render={({ field: f }) => (
                <FToggle
                  label={label}
                  description={description}
                  checked={!!f.value}
                  onChange={(v) => f.onChange(v)}
                />
              )}
            />
          ))}
        </div>
      </SectionCard>

      {/* Additional details */}
      <SectionCard
        title="Additional Details"
        subtitle="Optional — any other information about the fraud incident"
      >
        <Controller
          control={control}
          name="fraud_additional_details"
          render={({ field }) => (
            <FTextarea
              label="Additional details about the fraud incident"
              placeholder="Describe any other suspicious activity, callers, messages, or events related to this fraud..."
              value={field.value ?? ""}
              onChange={field.onChange}
              rows={4}
              maxLength={1000}
            />
          )}
        />
      </SectionCard>

      {/* RBI note */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 flex items-start gap-3">
        <Info className="w-4 h-4 text-blue-500 mt-0.5 shrink-0" />
        <div className="text-xs text-blue-700">
          <p className="font-semibold mb-1">RBI Zero Liability Policy</p>
          <p>
            Under RBI guidelines, unauthorized transactions reported within 3 business days
            qualify for zero customer liability. We have pre-notified the fraud team and
            your case will be treated with highest priority. A temporary hold may be placed
            on your account as a protective measure.
          </p>
        </div>
      </div>
    </div>
  );
}
