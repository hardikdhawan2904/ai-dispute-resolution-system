"use client";

import { UseFormReturn, Controller } from "react-hook-form";
import {
  CreditCard,
  Zap,
  Landmark,
  Store,
  Banknote,
  ShoppingCart,
  Globe,
  Smartphone,
  Check,
  Info,
  AlertCircle,
} from "lucide-react";
import { FormValues, TX_TYPES, TxType } from "../schema";
import { TxConfig, ExtraField } from "../config";
import { FInput, FSelect, FToggle, FMaskedDigits, Panel, SubSection } from "./FormControls";
import { TX_CONFIG } from "../config";

// ── Icon + metadata maps ───────────────────────────────────────────────────────

const TX_ICONS: Record<TxType, React.ComponentType<{ className?: string }>> = {
  "Credit Card":      CreditCard,
  "Debit Card":       CreditCard,
  "UPI":              Zap,
  "Net Banking":      Landmark,
  "Wallet":           Smartphone,
  "POS":              Store,
  "ATM":              Banknote,
  "Online Purchase":  ShoppingCart,
  "International":    Globe,
};

const TX_META: Record<TxType, { title: string; description: string }> = {
  "Credit Card":     { title: "Credit Card",            description: "Online, POS, recurring subscription and international card transactions" },
  "Debit Card":      { title: "Debit Card",             description: "ATM withdrawals, POS purchases and debit-based payments" },
  "UPI":             { title: "UPI Transfer",           description: "Instant account-to-account transfers via UPI apps and QR payments" },
  "Net Banking":     { title: "Net Banking",            description: "NEFT, RTGS, IMPS and online banking fund transfers" },
  "Wallet":          { title: "Digital Wallet",         description: "Wallet-based transactions through payment apps and stored balances" },
  "POS":             { title: "POS Transaction",        description: "Point-of-sale terminal transactions using physical cards" },
  "ATM":             { title: "ATM Withdrawal",         description: "Cash withdrawals, failed withdrawals and ATM debit disputes" },
  "Online Purchase": { title: "Online Purchase",        description: "E-commerce orders, merchant disputes and delivery-related issues" },
  "International":   { title: "International",          description: "Cross-border transactions and foreign merchant payments" },
};

// ── Sub-components ─────────────────────────────────────────────────────────────

function AdvisoryNote({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2 pt-3 mt-1 border-t border-gray-100">
      <Info className="w-3.5 h-3.5 text-gray-400 shrink-0 mt-0.5" />
      <p className="text-[11px] text-gray-500 leading-relaxed">{text}</p>
    </div>
  );
}

// ── Dynamic field renderer ─────────────────────────────────────────────────────

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
  const { register, control, watch, setValue, formState: { errors } } = form;
  const txType = watch("transaction_type");

  const toggleFields    = config?.extraFields.filter((f) => f.type === "toggle") ?? [];
  const nonToggleFields = config?.extraFields.filter((f) => f.type !== "toggle") ?? [];

  return (
    <div className="space-y-4">

      {/* ── Transaction Type Grid ──────────────────────────────────────────── */}
      <Panel label="Select Transaction Type">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {TX_TYPES.map((type) => {
            const Icon     = TX_ICONS[type];
            const meta     = TX_META[type];
            const selected = txType === type;

            return (
              <button
                key={type}
                type="button"
                onClick={() => setValue("transaction_type", type, { shouldValidate: true })}
                className={[
                  "group relative flex flex-col items-start p-3.5 rounded border text-left",
                  "transition-colors duration-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500",
                  selected
                    ? "border-blue-400 bg-blue-50"
                    : "border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50",
                ].join(" ")}
              >
                {selected && (
                  <span className="absolute top-2 right-2 w-3.5 h-3.5 rounded-full bg-blue-500 flex items-center justify-center">
                    <Check className="w-2 h-2 text-white" strokeWidth={3} />
                  </span>
                )}

                {/* Icon */}
                <div
                  className={[
                    "w-8 h-8 rounded-md flex items-center justify-center mb-3 transition-colors duration-100",
                    selected
                      ? "bg-blue-500"
                      : "bg-gray-100 group-hover:bg-gray-200",
                  ].join(" ")}
                >
                  <Icon className={`w-4 h-4 ${selected ? "text-white" : "text-gray-500"}`} />
                </div>

                {/* Label */}
                <span className={`text-xs font-semibold leading-tight ${selected ? "text-blue-800" : "text-gray-800"}`}>
                  {meta.title}
                </span>

                <span className="hidden sm:block text-[11px] text-gray-400 mt-1 leading-relaxed line-clamp-2">
                  {meta.description}
                </span>
              </button>
            );
          })}
        </div>

        {errors.transaction_type && (
          <p className="mt-3 flex items-center gap-1.5 text-xs text-red-500">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            {errors.transaction_type.message}
          </p>
        )}
      </Panel>

      {/* ── Core Transaction Details ───────────────────────────────────────── */}
      <Panel label="Transaction Details">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <FInput
            label="Transaction ID"
            required
            placeholder="TXN-XXXXXXXXXX"
            error={errors.transaction_id?.message}
            {...register("transaction_id")}
          />
          <FInput
            label="Merchant / Payee"
            required
            placeholder="Amazon, Zomato, HDFC Bank…"
            error={errors.merchant?.message}
            {...register("merchant")}
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
                render={({ field }) => (
                  <select
                    value={field.value}
                    onChange={(e) => field.onChange(e.target.value)}
                    className="border border-r-0 border-gray-200 rounded-l-lg px-2.5 py-2.5 text-sm bg-gray-50 text-gray-600 focus:outline-none font-mono"
                  >
                    {["INR", "USD", "EUR", "GBP", "AED"].map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                )}
              />
              <input
                type="number"
                step="0.01"
                min="0.01"
                placeholder="0.00"
                {...register("amount")}
                className={[
                  "flex-1 border rounded-r-lg px-3 py-2.5 text-sm text-gray-900 font-mono",
                  "focus:outline-none focus:ring-2 transition-colors",
                  errors.amount
                    ? "border-red-400 bg-red-50/50 focus:ring-red-500/20"
                    : "border-gray-200 focus:ring-blue-500/20 focus:border-blue-500",
                ].join(" ")}
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
            {...register("transaction_date")}
          />
          <FInput
            label="Transaction Time"
            type="time"
            help="Approximate time if exact is unknown"
            {...register("transaction_time")}
          />
        </div>
      </Panel>

      {/* ── Type-Specific Metadata ─────────────────────────────────────────── */}
      {config && txType && (
        <Panel label={`${txType} — Metadata`}>
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

            <AdvisoryNote text={config.contextHelp} />
          </div>
        </Panel>
      )}

    </div>
  );
}
