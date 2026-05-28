"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import {
  User, CreditCard, Building2, DollarSign, Calendar,
  MessageSquare, AlertTriangle, Loader2, ChevronRight, Shield
} from "lucide-react";
import { cn } from "@/lib/utils";
import { submitDispute } from "@/lib/api";
import type { DisputeSubmissionInput, TransactionType, FormErrors } from "@/types";

const TRANSACTION_TYPES: TransactionType[] = [
  "Credit Card", "Debit Card", "UPI", "Net Banking",
  "Wallet", "POS", "ATM", "Online Purchase", "International",
];

const DISPUTE_REASONS = [
  "Unauthorized Transaction",
  "Duplicate Transaction",
  "Refund Not Received",
  "Product Not Received",
  "Subscription Abuse",
  "ATM Cash Issue",
  "Merchant Dispute",
  "Other",
];

const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD"];

const EMPTY_FORM: DisputeSubmissionInput = {
  customer_name: "",
  customer_id: "",
  email: "",
  phone: "",
  transaction_id: "",
  transaction_type: "UPI",
  merchant: "",
  amount: 0,
  currency: "INR",
  transaction_date: "",
  transaction_time: "",
  customer_comment: "",
  dispute_reason: "Unauthorized Transaction",
  fraud_selected: false,
};

interface FieldProps {
  label: string;
  required?: boolean;
  icon?: React.ElementType;
  error?: string;
  children: React.ReactNode;
  hint?: string;
}

function Field({ label, required, icon: Icon, error, children, hint }: FieldProps) {
  return (
    <div className="space-y-1.5">
      <label className="flex items-center gap-1.5 text-xs font-medium text-bfsi-text-muted">
        {Icon && <Icon className="w-3.5 h-3.5 text-bfsi-text-dim" />}
        {label}
        {required && <span className="text-bfsi-gold">*</span>}
      </label>
      {children}
      {hint && !error && <p className="text-[11px] text-bfsi-text-dim">{hint}</p>}
      {error && <p className="text-[11px] text-red-400">{error}</p>}
    </div>
  );
}

export default function DisputeForm() {
  const router = useRouter();
  const [form, setForm] = useState<DisputeSubmissionInput>(EMPTY_FORM);
  const [errors, setErrors] = useState<FormErrors>({});
  const [loading, setLoading] = useState(false);

  const set = (key: keyof DisputeSubmissionInput, value: unknown) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const validate = (): boolean => {
    const e: FormErrors = {};
    if (!form.customer_name.trim()) e.customer_name = "Customer name is required";
    if (!form.customer_id.trim())   e.customer_id = "Customer ID is required";
    if (!form.email.match(/[^@]+@[^@]+\.[^@]+/)) e.email = "Valid email required";
    if (!form.phone.replace(/\D/, "").match(/\d{10,}/)) e.phone = "Valid phone required";
    if (!form.transaction_id.trim()) e.transaction_id = "Transaction ID is required";
    if (!form.merchant.trim())       e.merchant = "Merchant name is required";
    if (!form.amount || form.amount <= 0) e.amount = "Amount must be greater than zero";
    if (!form.transaction_date)      e.transaction_date = "Transaction date is required";
    if (!form.customer_comment.trim() || form.customer_comment.length < 10)
      e.customer_comment = "Please provide a detailed description (min 10 characters)";
    if (!form.dispute_reason)        e.dispute_reason = "Select a dispute reason";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) {
      toast.error("Please fix the errors before submitting");
      return;
    }
    setLoading(true);
    try {
      const result = await submitDispute({
        ...form,
        amount: Number(form.amount),
      });
      toast.success(`Case ${result.case_id} created — AI analysis complete`);
      router.push(`/dashboard/cases/${result.case_id}`);
    } catch (err: any) {
      toast.error(err.message || "Submission failed — please try again");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-8">

      {/* Section: Customer Information */}
      <section className="bfsi-card p-6 bfsi-card-accent">
        <p className="section-header">Customer Information</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <Field label="Customer Name" required icon={User} error={errors.customer_name}>
            <input
              className="bfsi-input"
              placeholder="Full legal name"
              value={form.customer_name}
              onChange={(e) => set("customer_name", e.target.value)}
            />
          </Field>
          <Field label="Customer ID" required icon={Shield} error={errors.customer_id}
            hint="Bank-issued customer identifier">
            <input
              className="bfsi-input"
              placeholder="e.g. CUST-00123"
              value={form.customer_id}
              onChange={(e) => set("customer_id", e.target.value)}
            />
          </Field>
          <Field label="Email Address" required icon={User} error={errors.email}>
            <input
              type="email"
              className="bfsi-input"
              placeholder="customer@email.com"
              value={form.email}
              onChange={(e) => set("email", e.target.value)}
            />
          </Field>
          <Field label="Phone Number" required icon={User} error={errors.phone}>
            <input
              type="tel"
              className="bfsi-input"
              placeholder="+91 98765 43210"
              value={form.phone}
              onChange={(e) => set("phone", e.target.value)}
            />
          </Field>
        </div>
      </section>

      {/* Section: Transaction Details */}
      <section className="bfsi-card p-6">
        <p className="section-header">Transaction Details</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <Field label="Transaction ID" required icon={CreditCard} error={errors.transaction_id}
            hint="Bank reference / UTR / ARN number">
            <input
              className="bfsi-input font-mono"
              placeholder="UPI20240315143200001"
              value={form.transaction_id}
              onChange={(e) => set("transaction_id", e.target.value)}
            />
          </Field>
          <Field label="Transaction Type" required error={errors.transaction_type}>
            <select
              className="bfsi-select"
              value={form.transaction_type}
              onChange={(e) => set("transaction_type", e.target.value as TransactionType)}
            >
              {TRANSACTION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Merchant / Payee" required icon={Building2} error={errors.merchant}>
            <input
              className="bfsi-input"
              placeholder="e.g. Amazon India, Zomato"
              value={form.merchant}
              onChange={(e) => set("merchant", e.target.value)}
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Amount" required icon={DollarSign} error={errors.amount}>
              <input
                type="number"
                className="bfsi-input"
                placeholder="0.00"
                min={0}
                step={0.01}
                value={form.amount || ""}
                onChange={(e) => set("amount", parseFloat(e.target.value) || 0)}
              />
            </Field>
            <Field label="Currency">
              <select
                className="bfsi-select"
                value={form.currency}
                onChange={(e) => set("currency", e.target.value)}
              >
                {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
          </div>
          <Field label="Transaction Date" required icon={Calendar} error={errors.transaction_date}>
            <input
              type="date"
              className="bfsi-input"
              value={form.transaction_date}
              onChange={(e) => set("transaction_date", e.target.value)}
            />
          </Field>
          <Field label="Transaction Time" hint="Optional but helps with fraud detection">
            <input
              type="time"
              className="bfsi-input"
              value={form.transaction_time}
              onChange={(e) => set("transaction_time", e.target.value)}
            />
          </Field>
        </div>
      </section>

      {/* Section: Dispute Information */}
      <section className="bfsi-card p-6">
        <p className="section-header">Dispute Information</p>
        <div className="space-y-5">
          <Field label="Primary Dispute Reason" required error={errors.dispute_reason}>
            <select
              className="bfsi-select"
              value={form.dispute_reason}
              onChange={(e) => set("dispute_reason", e.target.value)}
            >
              {DISPUTE_REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </Field>

          <Field
            label="Customer's Complaint"
            required
            icon={MessageSquare}
            error={errors.customer_comment}
            hint="Describe what happened in detail. AI will analyze this text to classify the dispute."
          >
            <textarea
              className="bfsi-textarea min-h-[120px]"
              placeholder="Describe the issue in detail — what happened, when, and what the customer expects as resolution..."
              value={form.customer_comment}
              onChange={(e) => set("customer_comment", e.target.value)}
            />
            <div className="text-[11px] text-bfsi-text-dim text-right">
              {form.customer_comment.length} characters
            </div>
          </Field>

          {/* Fraud Flag */}
          <div
            className={cn(
              "flex items-start gap-4 p-4 rounded-lg border cursor-pointer transition-all duration-200",
              form.fraud_selected
                ? "bg-red-400/5 border-red-400/40"
                : "bg-bfsi-muted border-bfsi-border hover:border-bfsi-text-dim"
            )}
            onClick={() => set("fraud_selected", !form.fraud_selected)}
          >
            <div className={cn(
              "w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 mt-0.5 transition-all",
              form.fraud_selected ? "bg-red-500 border-red-500" : "border-bfsi-text-dim"
            )}>
              {form.fraud_selected && (
                <svg className="w-3 h-3 text-white" viewBox="0 0 12 12" fill="none">
                  <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <AlertTriangle className={cn("w-4 h-4", form.fraud_selected ? "text-red-400" : "text-bfsi-text-dim")} />
                <span className={cn("text-sm font-medium", form.fraud_selected ? "text-red-400" : "text-bfsi-text-muted")}>
                  I believe this is a fraudulent transaction
                </span>
              </div>
              <p className="text-xs text-bfsi-text-dim mt-1">
                Check this if you suspect unauthorized access, card skimming, phishing, or account takeover.
                This flags the case for priority fraud investigation.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Submit */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-bfsi-text-dim">
          * Required fields. Dispute will be analysed by AI immediately after submission.
        </p>
        <button
          type="submit"
          disabled={loading}
          className="btn-gold flex items-center gap-2 min-w-[180px] justify-center"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Analyzing Dispute...
            </>
          ) : (
            <>
              Submit Dispute
              <ChevronRight className="w-4 h-4" />
            </>
          )}
        </button>
      </div>
    </form>
  );
}
