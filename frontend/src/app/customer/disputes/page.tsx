"use client";

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Plus, Search, Filter, ArrowRight, X, Loader2, CheckCircle } from "lucide-react";
import { customerListDisputes, customerSubmitDispute, type CustomerDispute } from "@/lib/api";
import { getUser } from "@/lib/auth";
import { cn } from "@/lib/utils";

const TRANSACTION_TYPES = ["Credit Card","Debit Card","UPI","Net Banking","Wallet","POS","ATM","Online Purchase","International"] as const;
const DISPUTE_REASONS   = ["Unauthorized Transaction","Duplicate Transaction","Refund Not Received","Product Not Received","Subscription Abuse","ATM Cash Issue","Merchant Dispute","Other"];

const STATUS_COLORS: Record<string, string> = {
  "Dispute Submitted":         "bg-blue-50 text-blue-700 border-blue-200",
  "Under Review":              "bg-amber-50 text-amber-700 border-amber-200",
  "Documents Requested":       "bg-orange-50 text-orange-700 border-orange-200",
  "Investigation In Progress": "bg-purple-50 text-purple-700 border-purple-200",
  "Awaiting Resolution":       "bg-indigo-50 text-indigo-700 border-indigo-200",
  "Resolved":                  "bg-green-50 text-green-700 border-green-200",
};

interface FormState {
  transaction_id: string;
  transaction_type: typeof TRANSACTION_TYPES[number];
  merchant: string;
  amount: string;
  currency: string;
  transaction_date: string;
  transaction_time: string;
  dispute_reason: string;
  customer_comment: string;
  fraud_selected: boolean;
}

const EMPTY: FormState = {
  transaction_id: "", transaction_type: "UPI", merchant: "", amount: "",
  currency: "INR", transaction_date: "", transaction_time: "",
  dispute_reason: "Unauthorized Transaction", customer_comment: "", fraud_selected: false,
};

export default function DisputesPage() {
  const searchParams = useSearchParams();
  const router       = useRouter();
  const user         = getUser();

  const [disputes, setDisputes]     = useState<CustomerDispute[]>([]);
  const [loading, setLoading]       = useState(true);
  const [search, setSearch]         = useState("");
  const [showForm, setShowForm]     = useState(searchParams.get("new") === "1");
  const [form, setForm]             = useState<FormState>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError]   = useState("");
  const [success, setSuccess]       = useState<{ case_id: string } | null>(null);

  useEffect(() => {
    customerListDisputes().then(setDisputes).finally(() => setLoading(false));
  }, []);

  const filtered = disputes.filter((d) =>
    d.merchant.toLowerCase().includes(search.toLowerCase()) ||
    d.transaction_id.toLowerCase().includes(search.toLowerCase()) ||
    d.status.toLowerCase().includes(search.toLowerCase())
  );

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) {
    const { name, value, type } = e.target;
    setForm((p) => ({ ...p, [name]: type === "checkbox" ? (e.target as HTMLInputElement).checked : value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!user) return;
    if (!form.customer_comment || form.customer_comment.length < 10) {
      setFormError("Please describe the issue in more detail (minimum 10 characters).");
      return;
    }
    setFormError("");
    setSubmitting(true);
    try {
      const res = await customerSubmitDispute({
        customer_name: user.name,
        customer_id: user.customer_id ?? "CUST-UNKNOWN",
        email: user.email,
        phone: "0000000000",
        transaction_id: form.transaction_id,
        transaction_type: form.transaction_type,
        merchant: form.merchant,
        amount: parseFloat(form.amount),
        currency: form.currency,
        transaction_date: form.transaction_date,
        transaction_time: form.transaction_time,
        customer_comment: form.customer_comment,
        dispute_reason: form.dispute_reason,
        fraud_selected: form.fraud_selected,
      });
      setSuccess({ case_id: res.case_id });
      setForm(EMPTY);
      const updated = await customerListDisputes();
      setDisputes(updated);
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : "Submission failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Disputes</h1>
          <p className="text-gray-500 text-sm mt-0.5">{disputes.length} dispute{disputes.length !== 1 ? "s" : ""} total</p>
        </div>
        <button
          onClick={() => { setShowForm(true); setSuccess(null); }}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition-all shadow-sm"
        >
          <Plus className="w-4 h-4" />
          Raise Dispute
        </button>
      </div>

      {/* New dispute form */}
      {showForm && (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-50 bg-blue-50">
            <h2 className="font-semibold text-blue-900">Raise a New Dispute</h2>
            <button onClick={() => { setShowForm(false); setSuccess(null); setFormError(""); }} className="text-gray-400 hover:text-gray-600">
              <X className="w-5 h-5" />
            </button>
          </div>

          {success ? (
            <div className="px-6 py-10 text-center">
              <div className="w-14 h-14 bg-green-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <CheckCircle className="w-7 h-7 text-green-600" />
              </div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">Dispute Submitted</h3>
              <p className="text-gray-500 text-sm mb-1">Your dispute has been received and is being reviewed.</p>
              <p className="text-xs text-gray-400 mb-6">Reference: <span className="font-mono font-medium">{success.case_id}</span></p>
              <div className="flex gap-3 justify-center">
                <Link href={`/customer/dispute/${success.case_id}`} className="bg-blue-600 text-white text-sm font-medium px-5 py-2.5 rounded-xl hover:bg-blue-700 transition-all">
                  Track this dispute
                </Link>
                <button onClick={() => setSuccess(null)} className="border border-gray-200 text-gray-600 text-sm font-medium px-5 py-2.5 rounded-xl hover:bg-gray-50 transition-all">
                  Raise another
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="p-6 space-y-6">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="sm:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Transaction ID *</label>
                  <input name="transaction_id" value={form.transaction_id} onChange={handleChange} required
                    className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors font-mono"
                    placeholder="e.g. TXN-2024-001234" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Transaction Type *</label>
                  <select name="transaction_type" value={form.transaction_type} onChange={handleChange}
                    className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm bg-white focus:outline-none focus:border-blue-500">
                    {TRANSACTION_TYPES.map((t) => <option key={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Merchant / Payee *</label>
                  <input name="merchant" value={form.merchant} onChange={handleChange} required
                    className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 transition-colors"
                    placeholder="e.g. Amazon India" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Amount *</label>
                  <div className="flex gap-2">
                    <select name="currency" value={form.currency} onChange={handleChange}
                      className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:outline-none focus:border-blue-500 w-24">
                      {["INR","USD","EUR","GBP"].map((c) => <option key={c}>{c}</option>)}
                    </select>
                    <input name="amount" type="number" min="0.01" step="0.01" value={form.amount} onChange={handleChange} required
                      className="flex-1 border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500"
                      placeholder="0.00" />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Transaction Date *</label>
                  <input name="transaction_date" type="date" value={form.transaction_date} onChange={handleChange} required
                    className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Reason for Dispute *</label>
                  <select name="dispute_reason" value={form.dispute_reason} onChange={handleChange}
                    className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm bg-white focus:outline-none focus:border-blue-500">
                    {DISPUTE_REASONS.map((r) => <option key={r}>{r}</option>)}
                  </select>
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1.5">Describe what happened *</label>
                  <textarea name="customer_comment" value={form.customer_comment} onChange={handleChange} rows={4} required minLength={10}
                    className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 resize-none"
                    placeholder="Explain in detail what happened with this transaction..." />
                  <p className="text-xs text-gray-400 mt-1">{form.customer_comment.length} characters (min 10)</p>
                </div>
                <div className="sm:col-span-2">
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input type="checkbox" name="fraud_selected" checked={form.fraud_selected} onChange={handleChange} className="mt-0.5 w-4 h-4 accent-red-600" />
                    <span className="text-sm text-gray-600">
                      <span className="font-medium text-red-600">I believe this is a fraudulent transaction</span> — I did not initiate or authorise it.
                    </span>
                  </label>
                </div>
              </div>
              {formError && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">{formError}</div>
              )}
              <div className="flex gap-3">
                <button type="button" onClick={() => setShowForm(false)} className="flex-1 border border-gray-200 text-gray-600 text-sm font-medium py-2.5 rounded-xl hover:bg-gray-50 transition-all">
                  Cancel
                </button>
                <button type="submit" disabled={submitting} className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm font-semibold py-2.5 rounded-xl transition-all flex items-center justify-center gap-2">
                  {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Submitting...</> : "Submit Dispute"}
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          value={search} onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-11 pr-4 py-3 bg-white border border-gray-100 rounded-xl text-sm focus:outline-none focus:border-blue-400 shadow-sm"
          placeholder="Search by merchant, transaction ID, or status..."
        />
      </div>

      {/* Cases list */}
      {loading && <div className="text-center py-12 text-gray-400">Loading your disputes...</div>}

      {!loading && filtered.length === 0 && (
        <div className="text-center py-12 bg-white rounded-2xl border border-gray-100">
          <p className="text-gray-500">No disputes found</p>
          <p className="text-gray-400 text-sm mt-1">{search ? "Try a different search term." : "You haven't raised any disputes yet."}</p>
        </div>
      )}

      {!loading && filtered.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm divide-y divide-gray-50">
          {filtered.map((d) => (
            <Link key={d.case_id} href={`/customer/dispute/${d.case_id}`}>
              <div className="flex items-center gap-4 px-6 py-4 hover:bg-gray-50/50 transition-colors cursor-pointer">
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-gray-900 text-sm">{d.merchant}</p>
                  <p className="text-gray-400 text-xs mt-0.5 truncate">{d.transaction_type} · <span className="font-mono">{d.transaction_id}</span></p>
                </div>
                <div className="text-right shrink-0 hidden sm:block">
                  <p className="font-bold text-gray-900">
                    {d.currency} {d.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </p>
                  <p className="text-gray-400 text-xs">{d.transaction_date ?? "—"}</p>
                </div>
                <span className={`text-xs font-medium px-3 py-1 rounded-full border shrink-0 ${STATUS_COLORS[d.status] ?? "bg-gray-50 text-gray-600 border-gray-200"}`}>
                  {d.status}
                </span>
                <ArrowRight className="w-4 h-4 text-gray-300 shrink-0" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
