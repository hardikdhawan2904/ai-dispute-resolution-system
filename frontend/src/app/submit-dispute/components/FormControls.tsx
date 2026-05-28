"use client";

import React, { useRef } from "react";
import { Info, AlertTriangle } from "lucide-react";

// ── FInput ─────────────────────────────────────────────────────────────────────

interface FInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  help?: string;
  required?: boolean;
}

export const FInput = React.forwardRef<HTMLInputElement, FInputProps>(
  function FInput({ label, error, help, required, className, ...rest }, ref) {
    const baseClass =
      "w-full border rounded-lg px-3 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors";
    const stateClass = error
      ? "border-red-400 bg-red-50/50 focus:ring-red-500/20 focus:border-red-400"
      : "border-gray-200 bg-white focus:ring-blue-500/20 focus:border-blue-500";

    return (
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1.5">
          {label}
          {required && <span className="text-red-500 ml-0.5">*</span>}
        </label>
        <input
          ref={ref}
          className={`${baseClass} ${stateClass} ${className ?? ""}`}
          {...rest}
        />
        {help && !error && (
          <p className="text-xs text-gray-400 mt-1">{help}</p>
        )}
        {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
      </div>
    );
  }
);

// ── FSelect ────────────────────────────────────────────────────────────────────

type SelectOption = { value: string; label: string } | string;

interface FSelectProps {
  label: string;
  error?: string;
  help?: string;
  required?: boolean;
  options: SelectOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
}

export function FSelect({
  label,
  error,
  help,
  required,
  options,
  value,
  onChange,
  placeholder,
  disabled,
}: FSelectProps) {
  const baseClass =
    "w-full appearance-none border rounded-lg px-3 py-2.5 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 transition-colors pr-8";
  const stateClass = error
    ? "border-red-400 bg-red-50/50 focus:ring-red-500/20 focus:border-red-400"
    : "border-gray-200 focus:ring-blue-500/20 focus:border-blue-500";

  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1.5">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className={`${baseClass} ${stateClass}`}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((opt) => {
            const v = typeof opt === "string" ? opt : opt.value;
            const l = typeof opt === "string" ? opt : opt.label;
            return (
              <option key={v} value={v}>
                {l}
              </option>
            );
          })}
        </select>
        <svg
          className="absolute right-2.5 top-3 w-4 h-4 text-gray-400 pointer-events-none"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </div>
      {help && !error && (
        <p className="text-xs text-gray-400 mt-1">{help}</p>
      )}
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
    </div>
  );
}

// ── FTextarea ──────────────────────────────────────────────────────────────────

interface FTextareaProps {
  label: string;
  error?: string;
  help?: string;
  required?: boolean;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
  maxLength?: number;
  minLength?: number;
}

export function FTextarea({
  label,
  error,
  help,
  required,
  value,
  onChange,
  placeholder,
  rows = 4,
  maxLength = 2000,
}: FTextareaProps) {
  const baseClass =
    "w-full border rounded-lg px-3 py-2.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors resize-none";
  const stateClass = error
    ? "border-red-400 bg-red-50/50 focus:ring-red-500/20 focus:border-red-400"
    : "border-gray-200 bg-white focus:ring-blue-500/20 focus:border-blue-500";

  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1.5">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        maxLength={maxLength}
        className={`${baseClass} ${stateClass}`}
      />
      <div className="flex items-start justify-between mt-1">
        <div>
          {help && !error && (
            <p className="text-xs text-gray-400">{help}</p>
          )}
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
        <span className="text-xs text-gray-400 shrink-0 ml-2">
          {value.length} / {maxLength}
        </span>
      </div>
    </div>
  );
}

// ── FToggle ────────────────────────────────────────────────────────────────────

interface FToggleProps {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}

export function FToggle({
  label,
  description,
  checked,
  onChange,
  disabled,
}: FToggleProps) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!checked)}
      className={`flex items-center justify-between w-full text-left p-3 rounded-lg border transition-colors ${
        checked
          ? "border-blue-200 bg-blue-50/50"
          : "border-gray-200 bg-white hover:bg-gray-50"
      } ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
    >
      <div className="flex-1 pr-4">
        <span className="text-sm font-medium text-gray-800">{label}</span>
        {description && (
          <p className="text-xs text-gray-500 mt-0.5">{description}</p>
        )}
      </div>
      {/* iOS-style toggle */}
      <div
        className={`relative w-10 h-6 rounded-full transition-colors shrink-0 ${
          checked ? "bg-blue-600" : "bg-gray-200"
        }`}
      >
        <div
          className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow-sm transition-transform ${
            checked ? "translate-x-5" : "translate-x-1"
          }`}
        />
      </div>
    </button>
  );
}

// ── FMaskedDigits ──────────────────────────────────────────────────────────────

interface FMaskedDigitsProps {
  label: string;
  error?: string;
  help?: string;
  required?: boolean;
  value: string;
  onChange: (value: string) => void;
}

export function FMaskedDigits({
  label,
  error,
  help,
  required,
  value,
  onChange,
}: FMaskedDigitsProps) {
  const inputRefs = [
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
  ];

  const digits = (value + "    ").slice(0, 4).split("");

  function handleChange(idx: number, char: string) {
    const d = char.replace(/\D/g, "").slice(-1);
    const newDigits = [...digits];
    newDigits[idx] = d || " ";
    const newVal = newDigits.join("").trimEnd();
    onChange(newVal);
    if (d && idx < 3) {
      inputRefs[idx + 1]?.current?.focus();
    }
  }

  function handleKeyDown(idx: number, e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && !digits[idx].trim() && idx > 0) {
      inputRefs[idx - 1]?.current?.focus();
    }
  }

  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1.5">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      <div className="flex items-center gap-2">
        {/* Three dots */}
        <div className="flex items-center gap-1 px-3 py-2.5 bg-gray-100 border border-gray-200 rounded-lg">
          {[0, 1, 2].map((i) => (
            <div key={i} className="w-2 h-2 rounded-full bg-gray-400" />
          ))}
          <div className="w-2 h-2 rounded-full bg-gray-400 ml-0.5" />
          <div className="w-2 h-2 rounded-full bg-gray-400 ml-0.5" />
          <div className="w-2 h-2 rounded-full bg-gray-400 ml-0.5" />
          <div className="w-2 h-2 rounded-full bg-gray-400 ml-0.5" />
          <div className="w-2 h-2 rounded-full bg-gray-400 ml-0.5" />
          <div className="w-2 h-2 rounded-full bg-gray-400 ml-0.5" />
          <div className="w-2 h-2 rounded-full bg-gray-400 ml-0.5" />
        </div>
        <span className="text-gray-400 text-sm">—</span>
        {/* 4 digit inputs */}
        {[0, 1, 2, 3].map((idx) => (
          <input
            key={idx}
            ref={inputRefs[idx]}
            type="text"
            inputMode="numeric"
            maxLength={1}
            value={digits[idx].trim()}
            onChange={(e) => handleChange(idx, e.target.value)}
            onKeyDown={(e) => handleKeyDown(idx, e)}
            className={`w-10 h-10 text-center text-sm font-mono font-semibold border rounded-lg focus:outline-none focus:ring-2 transition-colors ${
              error
                ? "border-red-400 bg-red-50/50 focus:ring-red-500/20"
                : "border-gray-200 bg-white focus:ring-blue-500/20 focus:border-blue-500"
            }`}
          />
        ))}
      </div>
      {help && !error && (
        <p className="text-xs text-gray-400 mt-1">{help}</p>
      )}
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
    </div>
  );
}

// ── SectionCard ────────────────────────────────────────────────────────────────

interface SectionCardProps {
  title?: string;
  subtitle?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  accent?: boolean;
  className?: string;
}

export function SectionCard({
  title,
  subtitle,
  children,
  className,
}: SectionCardProps) {
  return (
    <div className={`bg-white border border-gray-200 rounded ${className ?? ""}`}>
      {(title || subtitle) && (
        <div className="px-4 py-3 border-b border-gray-100">
          {title && (
            <p className="text-xs font-semibold text-gray-700">{title}</p>
          )}
          {subtitle && (
            <p className="text-[11px] text-gray-400 mt-0.5">{subtitle}</p>
          )}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}

// ── InfoBanner ─────────────────────────────────────────────────────────────────

export function InfoBanner({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-gray-500 text-[11px] leading-relaxed mt-1">
      <Info className="w-3.5 h-3.5 mt-0.5 shrink-0 text-gray-400" />
      <span>{children}</span>
    </div>
  );
}

// ── WarningBanner ──────────────────────────────────────────────────────────────

export function WarningBanner({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2.5 text-xs leading-relaxed">
      <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0 text-amber-500" />
      <span>{children}</span>
    </div>
  );
}

// ── Panel ──────────────────────────────────────────────────────────────────────

interface PanelProps {
  label: string;
  children: React.ReactNode;
  className?: string;
}

export function Panel({ label, children, className = "" }: PanelProps) {
  return (
    <div className={`bg-white border border-gray-200 rounded ${className}`}>
      <div className="px-4 py-3 border-b border-gray-100">
        <span className="text-xs font-semibold text-gray-700">{label}</span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

// ── SubSection ─────────────────────────────────────────────────────────────────

interface SubSectionProps {
  label: string;
  children: React.ReactNode;
}

export function SubSection({ label, children }: SubSectionProps) {
  return (
    <div>
      <p className="text-xs font-semibold text-gray-600 mb-2">{label}</p>
      {children}
    </div>
  );
}
