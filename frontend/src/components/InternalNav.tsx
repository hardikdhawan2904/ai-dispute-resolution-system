"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export default function InternalNav() {
  const pathname = usePathname();

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0B1120] border-b border-slate-700">
      <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 h-14 flex items-center gap-8">

        {/* Brand */}
        <Link href="/internal-review" className="flex items-center gap-2.5 shrink-0">
          <div className="flex items-center justify-center w-7 h-7 bg-slate-800 border border-slate-700 rounded">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <rect x="1" y="1" width="5" height="5" rx="1" fill="#2563EB" />
              <rect x="8" y="1" width="5" height="5" rx="1" fill="#2563EB" opacity="0.6" />
              <rect x="1" y="8" width="5" height="5" rx="1" fill="#2563EB" opacity="0.6" />
              <rect x="8" y="8" width="5" height="5" rx="1" fill="#2563EB" opacity="0.3" />
            </svg>
          </div>
          <div className="hidden sm:block">
            <div className="text-xs font-semibold text-slate-50 tracking-tight">
              Dispute Management
            </div>
            <div className="text-[10px] text-slate-500 font-medium tracking-wider uppercase">
              Operations Console
            </div>
          </div>
        </Link>

        {/* Nav links */}
        <div className="flex items-center h-full">
          <Link
            href="/internal-review"
            className={cn(
              "text-xs font-medium px-3 h-full flex items-center border-b-2 transition-colors",
              pathname.startsWith("/internal-review")
                ? "border-blue-600 text-slate-50"
                : "border-transparent text-slate-500 hover:text-slate-300"
            )}
          >
            Case Queue
          </Link>
        </div>

        {/* Right side */}
        <div className="ml-auto flex items-center gap-4">
          <div className="hidden sm:flex items-center gap-1.5 text-[11px] text-slate-500">
            <div className="w-1.5 h-1.5 rounded-full bg-green-700" />
            Systems Operational
          </div>
          <Link
            href="/submit-dispute"
            className="text-[11px] text-slate-400 border border-slate-700 rounded px-3 py-1 transition-all hover:text-white hover:border-slate-500"
          >
            Customer Portal
          </Link>
        </div>
      </div>
    </nav>
  );
}
