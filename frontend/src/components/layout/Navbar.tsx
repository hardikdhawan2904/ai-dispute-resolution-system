"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Shield, FileText, LayoutDashboard } from "lucide-react";
import { cn } from "@/lib/utils";
import { getUser, clearAuth } from "@/lib/auth";

const navItems = [
  { href: "/intake", label: "New Dispute", icon: FileText },
  { href: "/dashboard", label: "Operations", icon: LayoutDashboard },
];

const ROLE_LABELS: Record<string, string> = {
  FRAUD_ANALYST:        "Fraud Analyst",
  DISPUTE_INVESTIGATOR: "Investigator",
  COMPLIANCE_OFFICER:   "Compliance",
  OPERATIONS_ADMIN:     "Admin",
};

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const user = getUser();

  function handleLogout() {
    clearAuth();
    router.push("/login");
  }

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-bfsi-border bg-bfsi-navy/95 backdrop-blur-sm">
      <div className="max-w-screen-2xl mx-auto px-6 h-16 flex items-center justify-between">

        {/* Brand */}
        <Link href="/dashboard" className="flex items-center gap-3 group">
          <div className="w-8 h-8 rounded-md bg-bfsi-gold/10 border border-bfsi-gold/30 flex items-center justify-center group-hover:bg-bfsi-gold/20 transition-colors">
            <Shield className="w-4 h-4 text-bfsi-gold" />
          </div>
          <div>
            <div className="text-sm font-semibold text-bfsi-text leading-none">DisputeAI</div>
            <div className="text-[10px] text-bfsi-text-dim leading-none mt-0.5">BFSI Operations Platform</div>
          </div>
        </Link>

        {/* Nav Items */}
        <div className="flex items-center gap-1">
          {navItems.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-all duration-200",
                  active
                    ? "bg-bfsi-gold/10 text-bfsi-gold border border-bfsi-gold/20"
                    : "text-bfsi-text-muted hover:text-bfsi-text hover:bg-bfsi-muted"
                )}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            );
          })}
        </div>

        {/* Right side — user + status */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-xs text-bfsi-text-dim">
            <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span>AI Engine Online</span>
          </div>

          {user && (
            <div className="flex items-center gap-3 border-l border-bfsi-border pl-4">
              <div className="text-right">
                <p className="text-xs font-medium text-bfsi-text leading-none">{user.name}</p>
                <p className="text-[10px] text-bfsi-text-dim mt-0.5">{ROLE_LABELS[user.role] ?? user.role}</p>
              </div>
              <button
                onClick={handleLogout}
                className="text-xs text-bfsi-text-dim hover:text-bfsi-text transition-colors px-2 py-1 rounded hover:bg-bfsi-muted"
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
