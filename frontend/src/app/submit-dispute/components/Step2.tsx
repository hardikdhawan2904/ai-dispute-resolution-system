"use client";

import { useState } from "react";
import { UseFormReturn, Controller } from "react-hook-form";
import { Loader2, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { FormValues } from "../schema";
import { TX_TYPES } from "../schema";
import { TxConfig, ExtraField } from "../config";
import { FInput, FSelect, FToggle, FMaskedDigits, Panel, SubSection, InfoBanner } from "./FormControls";
import { lookupTransaction } from "@/lib/api";

const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD"];

// ── Dynamic field renderer (type-specific metadata) ────────────────────────────

function DynamicField({
  field,
  form,
}: {
  field: ExtraField;
  form: UseFormReturn<FormValues>;
}) {
  const { register, control, formState: { errors }, setValue, watch } = form;
  const key = field.key as keyof FormValues;
  const error = (errors[key] as { message?: string } | undefined)?.message;

  if (field.type === "toggle") {
    return (
      <Controller
        control={control}
        name={key}
        render={({ field: f }) => (
          <FToggle
            label={field.label}
            description={field.help}
            checked={!!f.value}
            onChange={(v) => f.onChange(v)}
          />
        )}
      />
    );
  }

  if (field.type === "masked-digits") {
    return (
      <Controller
        control={control}
        name={key}
        render={({ field: f }) => (
          <FMaskedDigits
            label={field.label}
            required={field.required}
            help={field.help}
            error={error}
            value={typeof f.value === "string" ? f.value : ""}
            onChange={(v) => f.onChange(v)}
          />
        )}
      />
    );
  }

  if (field.type === "select" && field.options) {
    const currentValue = watch(key);
    return (
      <FSelect
        label={field.label}
        required={field.required}
        help={field.help}
        error={error}
        options={field.options}
        value={typeof currentValue === "string" ? currentValue : ""}
        placeholder={`Select ${field.label}`}
        onChange={(v) => setValue(key, v as FormValues[keyof FormValues])}
      />
    );
  }

  return (
    <FInput
      label={field.label}
      required={field.required}
      help={field.help}
      error={error}
      placeholder={field.placeholder}
      {...register(key, {
        onChange:
          field.transform === "uppercase"
            ? (e) => { e.target.value = e.target.value.toUpperCase(); }
            : undefined,
      })}
      onInput={
        field.transform === "uppercase"
          ? (e) => {
              (e.target as HTMLInputElement).value = (e.target as HTMLInputElement).value.toUpperCase();
            }
          : field.transform === "digits-only"
          ? (e) => {
              (e.target as HTMLInputElement).value = (e.target as HTMLInputElement).value.replace(/\D/g, "");
            }
          : undefined
      }
    />
  );
}

// ── Step2 ──────────────────────────────────────────────────────────────────────

interface Step2Props {
  form: UseFormReturn<FormValues>;
  config: TxConfig | null;
  onVerifiedChange?: (verified: boolean) => void;
}

type VerifyState = "idle" | "loading" | "matched" | "mismatch" | "not_found";

export default function Step2({ form, config, onVerifiedChange }: Step2Props) {
  const { register, setValue, watch, control, formState: { errors } } = form;

  const [verifyState, setVerifyState] = useState<VerifyState>("idle");
  const [mismatchFields, setMismatchFields] = useState<string[]>([]);

  function updateVerifyState(s: VerifyState) {
    setVerifyState(s);
    onVerifiedChange?.(s === "matched");
  }

  const transactionId   = watch("transaction_id");
  const txType          = watch("transaction_type");
  const merchant        = watch("merchant");
  const amount          = watch("amount");
  const transactionDate = watch("transaction_date");
  const currency        = watch("currency") || "INR";

  async function handleVerify() {
    const id = transactionId?.trim();
    if (!id) return;

    updateVerifyState("loading");
    setMismatchFields([]);

    const txn = await lookupTransaction(id);

    if (!txn) {
      updateVerifyState("not_found");
      return;
    }

    // Compare every entered field against the DB record
    const mismatches: string[] = [];

    const enteredType = (txType || "").trim().toLowerCase();
    const dbType      = (txn.transaction_type || "").trim().toLowerCase();
    if (enteredType && dbType && enteredType !== dbType) {
      mismatches.push("Transaction Type");
    }

    const enteredMerchant = (merchant || "").trim().toLowerCase();
    const dbMerchant      = (txn.merchant_name || "").trim().toLowerCase();
    if (enteredMerchant && dbMerchant && enteredMerchant !== dbMerchant) {
      mismatches.push("Merchant / Payee");
    }

    const enteredAmount = parseFloat(String(amount));
    const dbAmount      = parseFloat(String(txn.amount));
    if (!isNaN(enteredAmount) && !isNaN(dbAmount) && Math.abs(enteredAmount - dbAmount) > 0.01) {
      mismatches.push("Amount");
    }

    const dbDatePart = txn.transaction_date ? txn.transaction_date.split("T")[0] : "";
    if (transactionDate && dbDatePart && transactionDate !== dbDatePart) {
      mismatches.push("Transaction Date");
    }

    if (mismatches.length > 0) {
      updateVerifyState("mismatch");
      setMismatchFields(mismatches);
    } else {
      // Sync currency and time from DB (user can't know these)
      setValue("currency", txn.currency || "INR", { shouldValidate: false });
      if (txn.transaction_date?.includes("T")) {
        setValue("transaction_time", txn.transaction_date.split("T")[1]?.substring(0, 5) || "", { shouldValidate: false });
      }
      updateVerifyState("matched");
    }
  }

  // Reset verification state whenever the user edits any core field
  function resetVerify() {
    if (verifyState !== "idle") {
      updateVerifyState("idle");
      setMismatchFields([]);
    }
  }

  const toggleFields    = config?.extraFields.filter((f) => f.type === "toggle") ?? [];
  const nonToggleFields = config?.extraFields.filter((f) => f.type !== "toggle") ?? [];

  return (
    <div className="space-y-4">

      {/* ── Transaction Details — all manually entered ─────────────────────── */}
      <Panel label="Transaction Details">
        <div className="space-y-4">

          {/* Transaction Type */}
          <Controller
            control={control}
            name="transaction_type"
            render={({ field: f }) => (
              <FSelect
                label="Transaction Type"
                required
                placeholder="Select transaction type"
                error={errors.transaction_type?.message}
                options={[...TX_TYPES]}
                value={f.value || ""}
                onChange={(v) => {
                  f.onChange(v);
                  resetVerify();
                }}
              />
            )}
          />

          {/* Merchant and Amount row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FInput
              label="Merchant / Payee"
              required
              placeholder="e.g. Amazon.in, Vijay Sales"
              error={errors.merchant?.message}
              {...register("merchant", { onChange: resetVerify })}
            />

            {/* Amount with currency selector */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">
                Amount <span className="text-red-500">*</span>
              </label>
              <div className="flex">
                <Controller
                  control={control}
                  name="currency"
                  render={({ field: f }) => (
                    <select
                      value={f.value || "INR"}
                      onChange={(e) => { f.onChange(e.target.value); resetVerify(); }}
                      className="border border-r-0 border-gray-200 rounded-l-lg px-2 py-2.5 text-sm bg-gray-50 text-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    >
                      {CURRENCIES.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  )}
                />
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  placeholder="0.00"
                  {...register("amount", { onChange: resetVerify })}
                  className="flex-1 border border-gray-200 rounded-r-lg px-3 py-2.5 text-sm text-gray-700 font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
              {errors.amount && (
                <p className="text-xs text-red-500 mt-1">{errors.amount.message}</p>
              )}
            </div>

            <FInput
              label="Transaction Date"
              required
              type="date"
              error={errors.transaction_date?.message}
              {...register("transaction_date", { onChange: resetVerify })}
            />
          </div>

          {/* Transaction ID — verify on blur */}
          <div className="pt-1 border-t border-gray-100">
            <div className="relative">
              <FInput
                label="Transaction ID"
                required
                placeholder="TXN-XXXXXXXXXX"
                error={errors.transaction_id?.message}
                {...register("transaction_id", { onChange: resetVerify })}
                onBlur={handleVerify}
              />

              {/* Verification status badge */}
              {verifyState === "loading" && (
                <div className="absolute right-3 top-8 flex items-center gap-1.5 text-xs text-gray-400">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Verifying…
                </div>
              )}
              {verifyState === "matched" && (
                <div className="absolute right-3 top-8 flex items-center gap-1.5 text-xs text-green-600">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  Details verified
                </div>
              )}
              {verifyState === "not_found" && (
                <div className="absolute right-3 top-8 flex items-center gap-1.5 text-xs text-red-500">
                  <XCircle className="w-3.5 h-3.5" />
                  Transaction ID not found
                </div>
              )}
              {verifyState === "mismatch" && (
                <div className="absolute right-3 top-8 flex items-center gap-1.5 text-xs text-amber-600">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  Details don&apos;t match
                </div>
              )}
            </div>

            {/* Mismatch breakdown */}
            {verifyState === "mismatch" && mismatchFields.length > 0 && (
              <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                <p className="text-xs font-medium text-amber-800 mb-1">
                  The following fields don&apos;t match our records — please correct them:
                </p>
                <ul className="list-disc list-inside space-y-0.5">
                  {mismatchFields.map((f) => (
                    <li key={f} className="text-xs text-amber-700">{f}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Matched confirmation */}
            {verifyState === "matched" && (
              <div className="mt-2 rounded-lg border border-green-200 bg-green-50 px-4 py-2.5">
                <p className="text-xs text-green-700">
                  Transaction verified — your details match our bank records. You may proceed.
                </p>
              </div>
            )}
          </div>

          <InfoBanner>
            Fill in your transaction details above, then enter your Transaction ID.
            We&apos;ll verify that the details you provided match our bank records.
          </InfoBanner>
        </div>
      </Panel>

      {/* ── Type-Specific Metadata ─────────────────────────────────────────── */}
      {config && txType && (
        <Panel label={`${txType} — Additional Details`}>
          <div className="space-y-5">
            {nonToggleFields.length > 0 && (
              <SubSection label="Transaction Metadata">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {nonToggleFields.map((f) => (
                    <div key={f.key} className={f.type === "masked-digits" ? "sm:col-span-2" : ""}>
                      <DynamicField field={f} form={form} />
                    </div>
                  ))}
                </div>
              </SubSection>
            )}

            {toggleFields.length > 0 && (
              <SubSection label="Transaction Flags">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {toggleFields.map((f) => (
                    <DynamicField key={f.key} field={f} form={form} />
                  ))}
                </div>
              </SubSection>
            )}

            <div className="flex items-start gap-2 pt-3 mt-1 border-t border-gray-100">
              <p className="text-[11px] text-gray-500 leading-relaxed">{config.contextHelp}</p>
            </div>
          </div>
        </Panel>
      )}
    </div>
  );
}
