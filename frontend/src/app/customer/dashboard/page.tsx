"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FileText, CheckCircle, Clock, AlertCircle, Plus, ArrowRight } from "lucide-react";
import { customerListDisputes, type CustomerDispute } from "@/lib/api";
import { getUser } from "@/lib/auth";

const STATUS_COLORS: Record<string, string> = {
  "Dispute Submitted":         "bg-blue-50 text-blue-700 border-blue-200",
  "Under Review":              "bg-amber-50 text-amber-700 border-amber-200",
  "Documents Requested":       "bg-orange-50 text-orange-700 border-orange-200",
  "Investigation In Progress": "bg-purple-50 text-purple-700 border-purple-200",
  "Awaiting Resolution":       "bg-indigo-50 text-indigo-700 border-indigo-200",
  "Resolved":                  "bg-green-50 text-green-700 border-green-200",
};

function StatCard({ label, value, icon: Icon, color }: {
  label: string; value: number; icon: React.ElementType; color: string;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-3 ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <p className="text-3xl font-bold text-gray-900 mb-1">{value}</p>
      <p className="text-sm text-gray-500">{label}</p>
    </div>
  );
}

export default function CustomerDashboard() {
  const user = getUser();
  const [disputes, setDisputes] = useState<CustomerDispute[]>([]);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    customerListDisputes().then(setDisputes).finally(() => setLoading(false));
  }, []);

  const total    = disputes.length;
  const active   = disputes.filter((d) => !["Resolved"].includes(d.status)).length;
  const resolved = disputes.filter((d) => d.status === "Resolved").length;
  const pending  = disputes.filter((d) => d.status === "Documents Requested").length;
  const recent   = disputes.slice(0, 5);

  return (
    <div className="space-y-6">
      {/* Greeting */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Good day, {user?.name?.split(" ")[0] ?? "there"}
          </h1>
          <p className="text-gray-500 text-sm mt-1">Here's an overview of your dispute cases.</p>
        </div>
        <Link
          href="/customer/disputes?new=1"
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-5 py-2.5 rounded-xl transition-all shadow-sm"
        >
          <Plus className="w-4 h-4" />
          <span className="hidden sm:inline">Raise Dispute</span>
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="Total Disputes"   value={total}    icon={FileText}     color="bg-blue-50 text-blue-600" />
        <StatCard label="Active Cases"     value={active}   icon={Clock}        color="bg-amber-50 text-amber-600" />
        <StatCard label="Resolved"         value={resolved} icon={CheckCircle}  color="bg-green-50 text-green-600" />
        <StatCard label="Docs Requested"   value={pending}  icon={AlertCircle}  color="bg-orange-50 text-orange-600" />
      </div>

      {/* Documents requested alert */}
      {pending > 0 && (
        <div className="bg-orange-50 border border-orange-200 rounded-2xl p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-orange-500 mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="text-orange-800 font-semibold text-sm">Documents Required</p>
            <p className="text-orange-700 text-sm mt-0.5">
              {pending} dispute{pending > 1 ? "s" : ""} require{pending === 1 ? "s" : ""} additional documents. Please upload them to avoid delays.
            </p>
          </div>
          <Link href="/customer/uploads" className="text-orange-600 hover:text-orange-700 text-sm font-semibold whitespace-nowrap">
            Upload →
          </Link>
        </div>
      )}

      {/* Recent disputes */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-50">
          <h2 className="font-semibold text-gray-900">Recent Disputes</h2>
          <Link href="/customer/disputes" className="text-blue-600 text-sm font-medium flex items-center gap-1 hover:text-blue-700">
            View all <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {loading && (
          <div className="px-6 py-12 text-center text-gray-400 text-sm">Loading your disputes...</div>
        )}

        {!loading && disputes.length === 0 && (
          <div className="px-6 py-12 text-center">
            <div className="w-12 h-12 bg-gray-100 rounded-2xl flex items-center justify-center mx-auto mb-3">
              <FileText className="w-6 h-6 text-gray-400" />
            </div>
            <p className="text-gray-700 font-medium">No disputes yet</p>
            <p className="text-gray-400 text-sm mt-1">Submit a dispute if you notice a problem with a transaction.</p>
            <Link href="/customer/disputes?new=1" className="mt-4 inline-flex items-center gap-2 bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded-xl hover:bg-blue-700 transition-all">
              <Plus className="w-4 h-4" /> Raise your first dispute
            </Link>
          </div>
        )}

        {!loading && recent.length > 0 && (
          <div className="divide-y divide-gray-50">
            {recent.map((d) => (
              <Link key={d.case_id} href={`/customer/dispute/${d.case_id}`}>
                <div className="flex items-center gap-4 px-6 py-4 hover:bg-gray-50/50 transition-colors cursor-pointer">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-gray-900 text-sm">{d.merchant}</p>
                    <p className="text-gray-400 text-xs mt-0.5 truncate">{d.transaction_type} · {d.transaction_id}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="font-semibold text-gray-900 text-sm">
                      {d.currency} {d.amount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </p>
                    <p className="text-gray-400 text-xs">{d.transaction_date ?? "—"}</p>
                  </div>
                  <span className={`text-xs font-medium px-2.5 py-1 rounded-full border shrink-0 ${STATUS_COLORS[d.status] ?? "bg-gray-50 text-gray-600 border-gray-200"}`}>
                    {d.status}
                  </span>
                  <ArrowRight className="w-4 h-4 text-gray-300 shrink-0" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Help section */}
      <div className="bg-blue-600 rounded-2xl p-6 text-white">
        <h3 className="font-semibold text-lg mb-1">Need help?</h3>
        <p className="text-blue-100 text-sm mb-4">
          Our dispute resolution team is available Monday to Saturday, 9 AM – 6 PM IST.
          Most disputes are resolved within 7–10 business days.
        </p>
        <div className="flex flex-wrap gap-3">
          <div className="bg-white/15 rounded-xl px-4 py-2 text-sm">📞 1800-000-0000 (Toll Free)</div>
          <div className="bg-white/15 rounded-xl px-4 py-2 text-sm">✉️ disputes@bank.com</div>
        </div>
      </div>
    </div>
  );
}
