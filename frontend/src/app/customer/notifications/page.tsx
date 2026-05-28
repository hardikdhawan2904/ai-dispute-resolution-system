"use client";

import { useEffect, useState } from "react";
import { Bell, CheckCircle, Clock, FileText, AlertCircle } from "lucide-react";
import { customerListDisputes, type CustomerDispute } from "@/lib/api";

const STATUS_TO_NOTIFICATION: Record<string, { title: string; desc: string; icon: React.ElementType; color: string }> = {
  "Dispute Submitted":         { title: "Dispute received",             desc: "Your dispute has been successfully submitted and is being processed.",           icon: CheckCircle, color: "text-blue-500 bg-blue-50" },
  "Under Review":              { title: "Review in progress",           desc: "Our team has started reviewing your dispute. You will hear from us soon.",       icon: Clock,       color: "text-amber-500 bg-amber-50" },
  "Documents Requested":       { title: "Action required: Documents",   desc: "We need additional documents. Please upload them to avoid delays.",              icon: AlertCircle, color: "text-orange-500 bg-orange-50" },
  "Investigation In Progress": { title: "Investigation started",        desc: "A specialist has been assigned to investigate your dispute.",                    icon: FileText,    color: "text-purple-500 bg-purple-50" },
  "Awaiting Resolution":       { title: "Final review underway",        desc: "Your case is in final review. A decision will be communicated shortly.",        icon: Clock,       color: "text-indigo-500 bg-indigo-50" },
  "Resolved":                  { title: "Dispute resolved",             desc: "Your dispute has been resolved. Please check your email for the outcome.",      icon: CheckCircle, color: "text-green-500 bg-green-50" },
};

interface Notification { id: string; case_id: string; merchant: string; status: string; date: string; }

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading]             = useState(true);

  useEffect(() => {
    customerListDisputes().then((disputes) => {
      // Generate one notification per dispute based on current status
      const notifs = disputes.map((d: CustomerDispute) => ({
        id: `${d.case_id}-${d.status}`,
        case_id: d.case_id,
        merchant: d.merchant,
        status: d.status,
        date: d.updated_at ?? d.created_at,
      }));
      setNotifications(notifs.reverse());
    }).finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-5 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Notifications</h1>
        <p className="text-gray-500 text-sm mt-1">Updates about your dispute cases.</p>
      </div>

      {loading && <div className="text-center py-12 text-gray-400">Loading notifications...</div>}

      {!loading && notifications.length === 0 && (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm text-center py-16">
          <div className="w-12 h-12 bg-gray-100 rounded-2xl flex items-center justify-center mx-auto mb-3">
            <Bell className="w-6 h-6 text-gray-400" />
          </div>
          <p className="text-gray-700 font-medium">No notifications</p>
          <p className="text-gray-400 text-sm mt-1">You will receive updates here when there is activity on your disputes.</p>
        </div>
      )}

      {!loading && notifications.length > 0 && (
        <div className="space-y-3">
          {notifications.map((n) => {
            const meta = STATUS_TO_NOTIFICATION[n.status] ?? {
              title: "Status update", desc: `Your dispute status changed to: ${n.status}`,
              icon: Bell, color: "text-gray-500 bg-gray-50",
            };
            const Icon = meta.icon;
            return (
              <div key={n.id} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 flex gap-4">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${meta.color}`}>
                  <Icon className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-semibold text-gray-900 text-sm">{meta.title}</p>
                    <p className="text-xs text-gray-400 shrink-0">{new Date(n.date).toLocaleDateString("en-IN")}</p>
                  </div>
                  <p className="text-gray-500 text-sm mt-0.5">{meta.desc}</p>
                  <p className="text-xs text-gray-400 mt-2">
                    Dispute · <span className="font-medium text-gray-600">{n.merchant}</span> · <span className="font-mono text-xs">{n.case_id.slice(-8)}</span>
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
