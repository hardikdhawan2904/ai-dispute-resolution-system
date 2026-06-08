"use client";

import { useState } from "react";
import { UseFormReturn, Controller } from "react-hook-form";
import { Loader2, CheckCircle2, XCircle } from "lucide-react";
import { FormValues } from "../schema";
import { TxConfig, ExtraField } from "../config";
import { FInput, FSelect, FToggle, FMaskedDigits, Panel, SubSection, InfoBanner } from "./FormControls";
import { lookupTransaction } from "@/lib/api";

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
}

export default function Step2({ form, config }: Step2Props) {
  const { register, setValue, watch, formState: { errors } } = form;
  const [lookupState, setLookupState] = useState<"idle" | "loading" | "found" | "not_found">("idle");

  const transactionId = watch("transaction_id");
  const txType        = watch("transaction_type");

  async function handleTransactionIdBlur() {
    const id = transactionId?.trim();
    if (!id) return;

    setLookupState("loading");
    const txn = await lookupTransaction(id);

    if (txn) {
      setValue("merchant",          txn.merchant_name,              { shouldValidate: true });
      setValue("amount",            txn.amount,                     { shouldValidate: true });
      setValue("currency",          txn.currency || "INR",          { shouldValidate: false });
      setValue("transaction_type",  txn.transaction_type,           { shouldValidate: true });
      const datePart = txn.transaction_date ? txn.transaction_date.split("T")[0] : "";
      setValue("transaction_date",  datePart,                       { shouldValidate: true });
      if (txn.transaction_date?.includes("T")) {
        setValue("transaction_time", txn.transaction_date.split("T")[1]?.substring(0, 5) || "", { shouldValidate: false });
      }
      setLookupState("found");
    } else {
      setValue("merchant",          "");
      setValue("amount",            0  as unknown as number);
      setValue("transaction_type",  "");
      setValue("transaction_date",  "");
      setLookupState("not_found");
    }
  }

  const toggleFields    = config?.extraFields.filter((f) => f.type === "toggle") ?? [];
  const nonToggleFields = config?.extraFields.filter((f) => f.type !== "toggle") ?? [];

  return (
    <div className="space-y-4">

      {/* ── Transaction Lookup ─────────────────────────────────────────────── */}
      <Panel label="Transaction Details">
        <div className="space-y-4">
          {/* Transaction ID */}
          <div className="relative">
            <FInput
              label="Transaction ID"
              required
              placeholder="TXN-XXXXXXXXXX"
              error={errors.transaction_id?.message}
              {...register("transaction_id")}
              onBlur={handleTransactionIdBlur}
            />
            {lookupState === "loading" && (
              <div className="absolute right-3 top-8 flex items-center gap-1.5 text-xs text-gray-400">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Looking up…
              </div>
            )}
            {lookupState === "found" && (
              <div className="absolute right-3 top-8 flex items-center gap-1.5 text-xs text-green-500">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Transaction found
              </div>
            )}
            {lookupState === "not_found" && (
              <div className="absolute right-3 top-8 flex items-center gap-1.5 text-xs text-red-500">
                <XCircle className="w-3.5 h-3.5" />
                Transaction not found — check your Transaction ID
              </div>
            )}
          </div>

          {/* Read-only fields — always populated from DB */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <FInput
              label="Transaction Type"
              required
              placeholder="Loaded from your transaction record"
              error={errors.transaction_type?.message}
              readOnly
              className="bg-gray-50 cursor-not-allowed"
              {...register("transaction_type")}
            />

            <FInput
              label="Merchant / Payee"
              required
              placeholder="Loaded from your transaction record"
              error={errors.merchant?.message}
              readOnly
              className="bg-gray-50 cursor-not-allowed"
              {...register("merchant")}
            />

            {/* Amount with currency */}
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1.5">
                Amount <span className="text-red-500">*</span>
              </label>
              <div className="flex">
                <span className="border border-r-0 border-gray-200 rounded-l-lg px-3 py-2.5 text-sm bg-gray-100 text-gray-500 font-mono select-none">
                  {watch("currency") || "INR"}
                </span>
                <input
                  type="number"
                  readOnly
                  tabIndex={-1}
                  {...register("amount")}
                  className="flex-1 border border-gray-200 rounded-r-lg px-3 py-2.5 text-sm text-gray-700 font-mono bg-gray-50 cursor-not-allowed focus:outline-none"
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
              readOnly
              className="bg-gray-50 cursor-not-allowed"
              error={errors.transaction_date?.message}
              {...register("transaction_date")}
            />
          </div>

          <InfoBanner>
            Enter your Transaction ID to load the transaction details automatically.
            These fields are sourced from bank records and cannot be edited.
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
