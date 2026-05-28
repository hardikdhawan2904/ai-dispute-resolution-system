"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Shield, LayoutDashboard, FileText, AlertTriangle,
  Search, ClipboardCheck, BookOpen, GitBranch, BarChart2, LogOut, Monitor,
  Layers,
} from "lucide-react";
import { getUser, clearAuth, ROLE_LABEL } from "@/lib/auth";
import { cn } from "@/lib/utils";

const ALL_NAV = [
  { href: "/internal-review",    label: "Live Review",    icon: Monitor,          roles: ["FRAUD_ANALYST","DISPUTE_INVESTIGATOR","COMPLIANCE_OFFICER","OPERATIONS_ADMIN"] },
  { href: "/ops/dashboard",      label: "Dashboard",      icon: LayoutDashboard,  roles: ["FRAUD_ANALYST","DISPUTE_INVESTIGATOR","COMPLIANCE_OFFICER","OPERATIONS_ADMIN"] },
  { href: "/ops/disputes",       label: "Cases",          icon: FileText,         roles: ["FRAUD_ANALYST","DISPUTE_INVESTIGATOR","COMPLIANCE_OFFICER","OPERATIONS_ADMIN"] },
  { href: "/ops/queues",         label: "Queues",         icon: Layers,           roles: ["FRAUD_ANALYST","DISPUTE_INVESTIGATOR","COMPLIANCE_OFFICER","OPERATIONS_ADMIN"] },
  { href: "/ops/search",         label: "Search",         icon: Search,           roles: ["FRAUD_ANALYST","DISPUTE_INVESTIGATOR","COMPLIANCE_OFFICER","OPERATIONS_ADMIN"] },
  { href: "/ops/fraud",          label: "Fraud",          icon: AlertTriangle,    roles: ["FRAUD_ANALYST","OPERATIONS_ADMIN"] },
  { href: "/ops/investigations", label: "Investigations", icon: GitBranch,        roles: ["DISPUTE_INVESTIGATOR","OPERATIONS_ADMIN"] },
  { href: "/ops/compliance",     label: "Compliance",     icon: ClipboardCheck,   roles: ["COMPLIANCE_OFFICER","OPERATIONS_ADMIN"] },
  { href: "/ops/audit",          label: "Audit Trail",    icon: BookOpen,         roles: ["COMPLIANCE_OFFICER","OPERATIONS_ADMIN"] },
  { href: "/ops/workflows",      label: "Workflows",      icon: GitBranch,        roles: ["FRAUD_ANALYST","DISPUTE_INVESTIGATOR","COMPLIANCE_OFFICER","OPERATIONS_ADMIN"] },
  { href: "/ops/analysis",       label: "Analytics",     icon: BarChart2,        roles: ["FRAUD_ANALYST","DISPUTE_INVESTIGATOR","COMPLIANCE_OFFICER","OPERATIONS_ADMIN"] },
];

export default function OpsNav() {
  const pathname = usePathname();
  const router   = useRouter();
  const user     = getUser();

  const navItems = ALL_NAV.filter((item) =>
    !user || item.roles.includes(user.role)
  );

  function logout() { clearAuth(); router.push("/login"); }

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-bfsi-border bg-bfsi-navy/95 backdrop-blur-sm">
      <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 h-16 flex items-center gap-6">
        {/* Brand */}
        <Link href="/internal-review" className="flex items-center gap-2.5 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-bfsi-gold/10 border border-bfsi-gold/30 flex items-center justify-center">
            <Shield className="w-4 h-4 text-bfsi-gold" />
          </div>
          <div className="hidden sm:block">
            <div className="text-sm font-semibold text-bfsi-text leading-none">DisputeAI</div>
            <div className="text-[10px] text-bfsi-text-dim mt-0.5">Operations Platform</div>
          </div>
        </Link>

        {/* Nav items — scrollable on mobile */}
        <div className="flex-1 flex items-center gap-1 overflow-x-auto no-scrollbar">
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || (href !== "/internal-review" && pathname.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-2 rounded-md text-xs font-medium whitespace-nowrap transition-all duration-200",
                  active
                    ? "bg-bfsi-gold/10 text-bfsi-gold border border-bfsi-gold/20"
                    : "text-bfsi-text-muted hover:text-bfsi-text hover:bg-bfsi-muted"
                )}
              >
                <Icon className="w-3.5 h-3.5 shrink-0" />
                <span className="hidden md:inline">{label}</span>
              </Link>
            );
          })}
        </div>

        {/* Right — status + user */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="hidden lg:flex items-center gap-1.5 text-xs text-bfsi-text-dim">
            <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            AI Online
          </div>
          {user && (
            <div className="flex items-center gap-2 border-l border-bfsi-border pl-3">
              <div className="hidden sm:block text-right">
                <p className="text-xs font-medium text-bfsi-text leading-none">{user.name}</p>
                <p className="text-[10px] text-bfsi-text-dim mt-0.5">{ROLE_LABEL[user.role]}</p>
              </div>
              <button
                onClick={logout}
                className="p-1.5 rounded text-bfsi-text-dim hover:text-bfsi-text hover:bg-bfsi-muted transition-all"
                title="Sign out"
              >
                <LogOut className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
