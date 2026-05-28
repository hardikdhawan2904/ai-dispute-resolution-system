"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Search, Filter, Plus, X, Loader2, ChevronRight, AlertTriangle, Brain, Shield } from "lucide-react";
import { listCases, submitDispute } from "@/lib/api";
import type { DisputeCase, DisputeSubmissionInput, TransactionType } from "@/types";
import { cn, getPriorityColor, getStatusColor, formatCurrency, formatConfidence, getConfidenceColor } from "@/lib/utils";
import RiskTags from "@/components/dispute/RiskTags";
import ConfidenceScore from "@/components/dispute/ConfidenceScore";
import toast from "react-hot-toast";

const TRANSACTION_TYPES: TransactionType[] = ["Credit Card","Debit Card","UPI","Net Banking","Wallet","POS","ATM","Online Purchase","International"];
const DISPUTE_REASONS = ["Unauthorized Transaction","Duplicate Transaction","Refund Not Received","Product Not Received","Subscription Abuse","ATM Cash Issue","Merchant Dispute","Other"];
const PRIORITIES = ["CRITICAL","HIGH","MEDIUM","LOW"];
const STATUSES   = ["Dispute Raised","Under Investigation","Pending Documents","Escalated","Resolved","Rejected","Closed"];

const EMPTY_FORM: DisputeSubmissionInput = {
  customer_name:"",customer_id:"",email:"",phone:"",transaction_id:"",transaction_type:"UPI",
  merchant:"",amount:0,currency:"INR",transaction_date:"",transaction_time:"",
  customer_comment:"",dispute_reason:"Unauthorized Transaction",fraud_selected:false,
};

export default function OpsDisputesPage() {
  const searchParams = useSearchParams();
  const [cases, setCases]               = useState<DisputeCase[]>([]);
  const [total, setTotal]               = useState(0);
  const [loading, setLoading]           = useState(true);
  const [search, setSearch]             = useState("");
  const [filterPriority, setPriority]   = useState("");
  const [filterStatus, setStatus]       = useState("");
  const [showForm, setShowForm]         = useState(searchParams.get("new") === "1");
  const [form, setForm]                 = useState<DisputeSubmissionInput>(EMPTY_FORM);
  const [submitting, setSubmitting]     = useState(false);

  useEffect(() => {
    setLoading(true);
    listCases({ limit: 200, priority: filterPriority || undefined, status: filterStatus || undefined })
      .then((r) => { setCases(r.cases); setTotal(r.total); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [filterPriority, filterStatus]);

  const filtered = cases.filter((c) =>
    !search ||
    c.case_id.toLowerCase().includes(search.toLowerCase()) ||
    c.merchant.toLowerCase().includes(search.toLowerCase()) ||
    c.customer_id.toLowerCase().includes(search.toLowerCase()) ||
    (c.customer_name ?? "").toLowerCase().includes(search.toLowerCase())
  );

  const set = (k: keyof DisputeSubmissionInput, v: unknown) => setForm((p) => ({ ...p, [k]: v }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await submitDispute({ ...form, amount: Number(form.amount) });
      toast.success(`Case ${res.case_id} created — AI analysis complete`);
      setShowForm(false);
      setForm(EMPTY_FORM);
      const r = await listCases({ limit: 200 });
      setCases(r.cases); setTotal(r.total);
    } catch (err: any) {
      toast.error(err.message || "Submission failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-1 h-5 bg-bfsi-gold rounded-full" />
            <span className="text-xs text-bfsi-gold font-semibold tracking-widest uppercase">Case Management</span>
          </div>
          <h1 className="text-2xl font-bold text-bfsi-text">Dispute Cases <span className="text-bfsi-text-dim font-normal text-lg">({total})</span></h1>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="btn-gold flex items-center gap-2">
          <Plus className="w-4 h-4" />
          New Dispute Intake
        </button>
      </div>

      {/* Intake form */}
      {showForm && (
        <div className="bfsi-card bfsi-card-accent p-6 mb-6">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-bfsi-gold" />
              <h2 className="font-semibold text-bfsi-text">New Dispute Intake — AI Analysis</h2>
            </div>
            <button onClick={() => setShowForm(false)} className="text-bfsi-text-dim hover:text-bfsi-text"><X className="w-4 h-4" /></button>
          </div>
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                { key:"customer_name", label:"Customer Name", type:"text", placeholder:"Full legal name" },
                { key:"customer_id",   label:"Customer ID",   type:"text", placeholder:"CUST-00123" },
                { key:"email",         label:"Email",         type:"email",placeholder:"email@bank.com" },
                { key:"phone",         label:"Phone",         type:"tel",  placeholder:"+91 9876543210" },
              ].map(({ key, label, type, placeholder }) => (
                <div key={key}>
                  <label className="block text-xs text-bfsi-text-dim mb-1">{label} *</label>
                  <input type={type} className="bfsi-input" placeholder={placeholder}
                    value={(form as any)[key]} onChange={(e) => set(key as any, e.target.value)} required />
                </div>
              ))}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label className="block text-xs text-bfsi-text-dim mb-1">Transaction ID *</label>
                <input className="bfsi-input font-mono" placeholder="UPI20240315..." value={form.transaction_id} onChange={(e) => set("transaction_id", e.target.value)} required />
              </div>
              <div>
                <label className="block text-xs text-bfsi-text-dim mb-1">Transaction Type</label>
                <select className="bfsi-select" value={form.transaction_type} onChange={(e) => set("transaction_type", e.target.value as TransactionType)}>
                  {TRANSACTION_TYPES.map((t) => <option key={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-bfsi-text-dim mb-1">Merchant *</label>
                <input className="bfsi-input" placeholder="Amazon India" value={form.merchant} onChange={(e) => set("merchant", e.target.value)} required />
              </div>
              <div className="flex gap-2">
                <div className="w-20">
                  <label className="block text-xs text-bfsi-text-dim mb-1">Currency</label>
                  <select className="bfsi-select" value={form.currency} onChange={(e) => set("currency", e.target.value)}>
                    {["INR","USD","EUR","GBP"].map((c) => <option key={c}>{c}</option>)}
                  </select>
                </div>
                <div className="flex-1">
                  <label className="block text-xs text-bfsi-text-dim mb-1">Amount *</label>
                  <input type="number" className="bfsi-input" min={0.01} step={0.01} placeholder="0.00" value={form.amount || ""} onChange={(e) => set("amount", parseFloat(e.target.value) || 0)} required />
                </div>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs text-bfsi-text-dim mb-1">Date *</label>
                <input type="date" className="bfsi-input" value={form.transaction_date} onChange={(e) => set("transaction_date", e.target.value)} required />
              </div>
              <div>
                <label className="block text-xs text-bfsi-text-dim mb-1">Time</label>
                <input type="time" className="bfsi-input" value={form.transaction_time} onChange={(e) => set("transaction_time", e.target.value)} />
              </div>
              <div>
                <label className="block text-xs text-bfsi-text-dim mb-1">Dispute Reason</label>
                <select className="bfsi-select" value={form.dispute_reason} onChange={(e) => set("dispute_reason", e.target.value)}>
                  {DISPUTE_REASONS.map((r) => <option key={r}>{r}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs text-bfsi-text-dim mb-1">Customer Statement *</label>
              <textarea className="bfsi-textarea" rows={4} placeholder="Customer complaint narrative..." value={form.customer_comment} onChange={(e) => set("customer_comment", e.target.value)} required minLength={10} />
            </div>
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={form.fraud_selected} onChange={(e) => set("fraud_selected", e.target.checked)} className="accent-red-500" />
                <span className="text-sm text-bfsi-text-muted">Flag as potential fraud</span>
              </label>
              <div className="flex gap-3">
                <button type="button" onClick={() => setShowForm(false)} className="btn-ghost">Cancel</button>
                <button type="submit" disabled={submitting} className="btn-gold flex items-center gap-2">
                  {submitting ? <><Loader2 className="w-4 h-4 animate-spin" />Analyzing...</> : <><Shield className="w-4 h-4" />Submit & Analyze</>}
                </button>
              </div>
            </div>
          </form>
        </div>
      )}

      {/* Filters */}
      <div className="bfsi-card p-4 mb-5 space-y-3">
        {/* Search row */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-bfsi-text-dim" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            className="bfsi-input pl-9 text-sm w-full" placeholder="Search by case ID, merchant, customer ID…" />
        </div>

        {/* Priority chips */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] text-bfsi-text-dim uppercase tracking-wider w-14 flex-shrink-0">Priority</span>
          <button onClick={() => setPriority("")}
            className={cn("text-xs px-3 py-1 rounded-full border transition-all",
              filterPriority === "" ? "bg-bfsi-gold/20 border-bfsi-gold text-bfsi-gold font-semibold" : "border-bfsi-border text-bfsi-text-dim hover:border-bfsi-gold/40 hover:text-bfsi-text"
            )}>All</button>
          {[
            { value: "CRITICAL", cls: "border-red-500/60 text-red-400 bg-red-500/20" },
            { value: "HIGH",     cls: "border-orange-500/60 text-orange-400 bg-orange-500/20" },
            { value: "MEDIUM",   cls: "border-yellow-500/60 text-yellow-400 bg-yellow-500/20" },
            { value: "LOW",      cls: "border-green-500/60 text-green-400 bg-green-500/20" },
          ].map(({ value, cls }) => (
            <button key={value} onClick={() => setPriority(filterPriority === value ? "" : value)}
              className={cn("text-xs px-3 py-1 rounded-full border transition-all font-medium",
                filterPriority === value ? cls : "border-bfsi-border text-bfsi-text-dim hover:border-bfsi-gold/40 hover:text-bfsi-text"
              )}>{value}</button>
          ))}
        </div>

        {/* Status/Stage chips */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] text-bfsi-text-dim uppercase tracking-wider w-14 flex-shrink-0">Stage</span>
          <button onClick={() => setStatus("")}
            className={cn("text-xs px-3 py-1 rounded-full border transition-all",
              filterStatus === "" ? "bg-bfsi-gold/20 border-bfsi-gold text-bfsi-gold font-semibold" : "border-bfsi-border text-bfsi-text-dim hover:border-bfsi-gold/40 hover:text-bfsi-text"
            )}>All</button>
          {STATUSES.map((s) => (
            <button key={s} onClick={() => setStatus(filterStatus === s ? "" : s)}
              className={cn("text-xs px-3 py-1 rounded-full border transition-all",
                filterStatus === s ? "bg-bfsi-gold/20 border-bfsi-gold text-bfsi-gold font-semibold" : "border-bfsi-border text-bfsi-text-dim hover:border-bfsi-gold/40 hover:text-bfsi-text"
              )}>{s}</button>
          ))}
        </div>

        {/* Active filter summary + clear */}
        {(filterPriority || filterStatus) && (
          <div className="flex items-center gap-2 pt-1 border-t border-bfsi-border">
            <Filter className="w-3.5 h-3.5 text-bfsi-gold" />
            <span className="text-xs text-bfsi-text-muted">
              Filtering by:
              {filterPriority && <span className="ml-1 font-semibold text-bfsi-text">{filterPriority}</span>}
              {filterPriority && filterStatus && <span className="text-bfsi-text-dim"> · </span>}
              {filterStatus && <span className="font-semibold text-bfsi-text">{filterStatus}</span>}
              <span className="text-bfsi-text-dim ml-1">— {filtered.length} result{filtered.length !== 1 ? "s" : ""}</span>
            </span>
            <button onClick={() => { setPriority(""); setStatus(""); }}
              className="ml-auto text-xs text-bfsi-text-dim hover:text-bfsi-text flex items-center gap-1 transition-colors">
              <X className="w-3 h-3" /> Clear filters
            </button>
          </div>
        )}
      </div>

      {/* Cases table */}
      {loading ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => <div key={i} className="bfsi-card p-4 animate-pulse h-16" />)}
        </div>
      ) : filtered.length === 0 ? (
        <div className="bfsi-card p-12 text-center">
          <p className="text-bfsi-text-muted">No cases found</p>
        </div>
      ) : (
        <div className="bfsi-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-bfsi-border">
                  <th className="text-left text-xs text-bfsi-text-dim font-medium px-4 py-3">Case ID</th>
                  <th className="text-left text-xs text-bfsi-text-dim font-medium px-4 py-3">Customer</th>
                  <th className="text-left text-xs text-bfsi-text-dim font-medium px-4 py-3">Merchant</th>
                  <th className="text-right text-xs text-bfsi-text-dim font-medium px-4 py-3">Amount</th>
                  <th className="text-center text-xs text-bfsi-text-dim font-medium px-4 py-3">Priority</th>
                  <th className="text-center text-xs text-bfsi-text-dim font-medium px-4 py-3">Stage</th>
                  <th className="text-left text-xs text-bfsi-text-dim font-medium px-4 py-3 hidden lg:table-cell">Queue</th>
                  <th className="text-center text-xs text-bfsi-text-dim font-medium px-4 py-3">Review Score</th>
                  <th className="text-center text-xs text-bfsi-text-dim font-medium px-4 py-3">Fraud</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-bfsi-border">
                {filtered.map((c) => (
                  <tr key={c.case_id} className="hover:bg-bfsi-muted/50 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-bfsi-gold">{c.case_id.slice(-12)}</td>
                    <td className="px-4 py-3">
                      <p className="text-xs font-medium text-bfsi-text">{c.customer_name ?? "—"}</p>
                      <p className="text-[10px] text-bfsi-text-dim font-mono">{c.customer_id}</p>
                    </td>
                    <td className="px-4 py-3 text-xs text-bfsi-text-muted max-w-32 truncate">{c.merchant}</td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-bfsi-text">
                      {c.currency} {c.amount.toLocaleString("en-IN")}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full border", getPriorityColor(c.priority as any))}>
                        {c.priority}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={cn("text-[10px] px-2 py-0.5 rounded-full border", getStatusColor(c.status as any))}>
                        {c.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-left hidden lg:table-cell">
                      <span className="text-[10px] text-bfsi-text-dim font-mono">
                        {c.assigned_queue?.replace(/_/g, " ") || "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={cn("text-xs font-mono font-semibold", getConfidenceColor(c.confidence_score))}>
                        {formatConfidence(c.confidence_score)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {c.fraud_suspicion ? <AlertTriangle className="w-4 h-4 text-red-400 mx-auto" /> : <span className="text-bfsi-text-dim text-xs">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <Link href={`/ops/case/${c.case_id}`} className="text-bfsi-gold hover:text-bfsi-text transition-colors">
                        <ChevronRight className="w-4 h-4" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
