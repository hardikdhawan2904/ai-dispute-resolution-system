"use client";

import { useState } from "react";
import {
  Loader2,
  CheckCircle,
  AlertTriangle,
  FileText,
  User,
  CreditCard,
  ShieldAlert,
  Paperclip,
  Check,
  KeyRound,
  UserX,
  Monitor,
  ExternalLink,
  Phone,
  Share2,
  Laptop,
  UserPlus,
  ArrowDownLeft,
} from "lucide-react";
import { FormValues } from "../schema";
import { TxConfig } from "../config";
import { Panel, SubSection } from "./FormControls";

interface Step6Props {
  values: FormValues;
  files: File[];
  txConfig: TxConfig | null;
  onSubmit: () => void;
  submitting: boolean;
  apiError?: string;
}

// ── Data row ──────────────────────────────────────────────────────────────────

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === null || value === undefined || value === "" || value === false)
    return null;
  const display =
    typeof value === "boolean" ? (value ? "Yes" : "No") : value;
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-slate-100 last:border-0">
      <span className="text-xs text-slate-400 w-36 shrink-0 pt-0.5 font-medium">
        {label}
      </span>
      <span className="text-xs text-slate-800 font-medium break-all leading-relaxed">
        {display}
      </span>
    </div>
  );
}

// ── Fraud signal label map (all 10 signals) ───────────────────────────────────

const FRAUD_SIGNAL_META: Array<{
  field: keyof FormValues;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  risk: "HIGH" | "MEDIUM";
}> = [
  { field: "otp_shared",          label: "OTP / PIN shared with caller",             icon: KeyRound,     risk: "HIGH"   },
  { field: "bank_impersonation",  label: "Bank staff impersonation call received",    icon: UserX,        risk: "HIGH"   },
  { field: "remote_access",       label: "Remote access application installed",       icon: Monitor,      risk: "HIGH"   },
  { field: "phishing_link",       label: "Phishing link clicked",                    icon: ExternalLink, risk: "HIGH"   },
  { field: "sim_swap_suspected",  label: "SIM swap suspected",                       icon: Phone,        risk: "HIGH"   },
  { field: "screen_sharing",      label: "Screen sharing was active on device",      icon: Share2,       risk: "HIGH"   },
  { field: "device_lost",         label: "Registered device lost or stolen",         icon: Laptop,       risk: "MEDIUM" },
  { field: "card_lost",           label: "Physical card lost or stolen",             icon: CreditCard,   risk: "MEDIUM" },
  { field: "unknown_beneficiary", label: "Unknown beneficiary added to account",     icon: UserPlus,     risk: "MEDIUM" },
  { field: "upi_collect_fraud",   label: "UPI collect request unknowingly accepted", icon: ArrowDownLeft,risk: "MEDIUM" },
];

// ── Step6 ─────────────────────────────────────────────────────────────────────

export default function Step6({
  values,
  files,
  txConfig,
  onSubmit,
  submitting,
  apiError,
}: Step6Props) {
  const [declared, setDeclared] = useState(false);

  const typeSpecificFields = txConfig?.extraFields ?? [];

  const activeSignals = FRAUD_SIGNAL_META.filter(
    ({ field }) => values[field] === true
  );

  const amountFormatted =
    `${values.currency || "INR"} ` +
    (typeof values.amount === "number"
      ? values.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })
      : String(values.amount ?? ""));

  return (
    <div className="space-y-4">

      {/* Page header */}
      <div className="mb-1">
        <h3 className="text-base font-bold text-slate-900">Review &amp; Submit</h3>
        <p className="text-xs text-slate-500 mt-0.5">
          Verify all case details before final submission. You cannot edit after submitting.
        </p>
      </div>

      {/* ── Customer Details ────────────────────────────────────────────── */}
      <Panel label="Customer Details">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-7 h-7 rounded-md bg-blue-50 flex items-center justify-center">
            <User className="w-3.5 h-3.5 text-blue-600" />
          </div>
          <span className="text-xs font-semibold text-slate-600">Account Holder</span>
        </div>
        <Row label="Full Name"    value={values.customer_name} />
        <Row label="Customer ID"  value={values.customer_id} />
        <Row label="Email"        value={values.email} />
        <Row label="Phone"        value={values.phone} />
      </Panel>

      {/* ── Transaction Details ─────────────────────────────────────────── */}
      <Panel label="Transaction Details">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-7 h-7 rounded-md bg-blue-50 flex items-center justify-center">
            <CreditCard className="w-3.5 h-3.5 text-blue-600" />
          </div>
          <span className="text-xs font-semibold text-slate-600">Transaction Record</span>
        </div>
        <Row label="Type"           value={values.transaction_type} />
        <Row label="Transaction ID" value={values.transaction_id} />
        <Row label="Merchant"       value={values.merchant} />
        <Row label="Amount"         value={amountFormatted} />
        <Row label="Date"           value={values.transaction_date} />
        {values.transaction_time && (
          <Row label="Time" value={values.transaction_time} />
        )}
        {typeSpecificFields.map((field) => {
          const val = values[field.key as keyof FormValues];
          if (val === null || val === undefined || val === "" || val === false) return null;
          return (
            <Row
              key={field.key}
              label={field.label}
              value={typeof val === "boolean" ? (val ? "Yes" : "No") : String(val)}
            />
          );
        })}
      </Panel>

      {/* ── Dispute Details ─────────────────────────────────────────────── */}
      <Panel label="Dispute Details">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-7 h-7 rounded-md bg-blue-50 flex items-center justify-center">
            <FileText className="w-3.5 h-3.5 text-blue-600" />
          </div>
          <span className="text-xs font-semibold text-slate-600">Case Classification</span>
        </div>
        <Row label="Dispute Reason" value={values.dispute_reason} />
        <Row label="Case Narrative" value={values.customer_comment} />
        <Row
          label="Fraud Declared"
          value={values.fraud_selected ? "Yes — Fraud Investigation" : "No"}
        />
      </Panel>

      {/* ── Fraud Indicators (only when fraud declared + signals active) ── */}
      {values.fraud_selected && activeSignals.length > 0 && (
        <Panel label="Confirmed Fraud Indicators">
          <div className="flex items-center gap-2.5 mb-3">
            <div className="w-7 h-7 rounded-md bg-red-50 flex items-center justify-center">
              <ShieldAlert className="w-3.5 h-3.5 text-red-600" />
            </div>
            <span className="text-xs font-semibold text-red-700">
              {activeSignals.length} of 10 indicators confirmed
            </span>
          </div>
          <div className="divide-y divide-gray-100 border border-gray-200 rounded">
            {activeSignals.map(({ field, label }) => (
              <div key={field} className="flex items-center gap-2.5 px-3 py-2.5">
                <div className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
                <span className="text-xs text-gray-700">{label}</span>
              </div>
            ))}
          </div>
          {values.fraud_additional_details && (
            <div className="mt-4 pt-4 border-t border-slate-100">
              <SubSection label="Fraud Incident Narrative">
                <p className="text-xs text-slate-600 leading-relaxed">
                  {values.fraud_additional_details}
                </p>
              </SubSection>
            </div>
          )}
        </Panel>
      )}

      {/* ── Supporting Documents ────────────────────────────────────────── */}
      <Panel label="Supporting Documents">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="w-7 h-7 rounded-md bg-blue-50 flex items-center justify-center">
            <Paperclip className="w-3.5 h-3.5 text-blue-600" />
          </div>
          <span className="text-xs font-semibold text-slate-600">
            {files.length > 0 ? `${files.length} document${files.length > 1 ? "s" : ""} attached` : "No documents attached"}
          </span>
        </div>
        {files.length === 0 ? (
          <p className="text-xs text-slate-400 italic">
            No supporting documents were uploaded for this case.
          </p>
        ) : (
          <div className="space-y-2">
            {files.map((file, idx) => (
              <div
                key={idx}
                className="flex items-center gap-2.5 px-3 py-2.5 border border-slate-200 bg-slate-50/50 rounded-lg"
              >
                <FileText className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                <span className="text-xs font-medium text-slate-700 truncate flex-1">
                  {file.name}
                </span>
                <span className="text-[10px] text-slate-400 shrink-0 font-mono">
                  {(file.size / 1024).toFixed(0)} KB
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {/* ── API Error ────────────────────────────────────────────────────── */}
      {apiError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3">
          <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-red-700 mb-1">
              Submission Failed
            </p>
            <p className="text-xs text-red-600 leading-relaxed">{apiError}</p>
          </div>
        </div>
      )}

      {/* ── Declaration ──────────────────────────────────────────────────── */}
      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-100 bg-slate-50/70 flex items-center gap-2.5">
          <div className="w-0.5 h-3.5 bg-blue-700 rounded-full shrink-0" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
            Applicant Declaration
          </span>
        </div>
        <div className="p-5">
          <button
            type="button"
            onClick={() => setDeclared((d) => !d)}
            className={[
              "w-full flex items-start gap-3 text-left p-4 rounded-lg border transition-all duration-150",
              declared
                ? "border-blue-200 bg-blue-50/50"
                : "border-gray-200 bg-gray-50/40 hover:border-slate-300",
            ].join(" ")}
          >
            <div className={[
              "mt-0.5 w-5 h-5 rounded border-2 shrink-0 flex items-center justify-center transition-colors",
              declared ? "bg-blue-600 border-blue-600" : "border-gray-300",
            ].join(" ")}>
              {declared && <Check className="w-3 h-3 text-white" strokeWidth={3} />}
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              I declare that all information provided in this dispute submission is true, complete, and accurate to the best of my knowledge. I understand that providing false or misleading information may result in account action under applicable banking regulations and RBI guidelines.
            </p>
          </button>
        </div>
      </div>

      {/* ── Submit button ────────────────────────────────────────────────── */}
      <button
        type="button"
        onClick={onSubmit}
        disabled={!declared || submitting}
        className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed text-white font-bold rounded-lg py-3.5 text-sm transition-colors shadow-sm flex items-center justify-center gap-2"
      >
        {submitting ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Submitting Dispute...
          </>
        ) : (
          <>
            <CheckCircle className="w-4 h-4" />
            Submit Dispute to Bank
          </>
        )}
      </button>

      {!declared && !submitting && (
        <p className="text-center text-xs text-slate-400">
          Confirm the declaration above to enable submission.
        </p>
      )}

    </div>
  );
}
