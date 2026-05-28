"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Shield, Monitor } from "lucide-react";
import { cn } from "@/lib/utils";

export default function InternalNav() {
  const pathname = usePathname();

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-bfsi-border bg-bfsi-navy/95 backdrop-blur-sm">
      <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 h-16 flex items-center gap-6">
        <Link href="/internal-review" className="flex items-center gap-2.5 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-bfsi-gold/10 border border-bfsi-gold/30 flex items-center justify-center">
            <Shield className="w-4 h-4 text-bfsi-gold" />
          </div>
          <div className="hidden sm:block">
            <div className="text-sm font-semibold text-bfsi-text leading-none">DisputeAI</div>
            <div className="text-[10px] text-bfsi-text-dim mt-0.5">Internal Review</div>
          </div>
        </Link>

        <div className="flex items-center gap-1">
          <Link
            href="/internal-review"
            className={cn(
              "flex items-center gap-1.5 px-3 py-2 rounded-md text-xs font-medium transition-all",
              pathname.startsWith("/internal-review")
                ? "bg-bfsi-gold/10 text-bfsi-gold border border-bfsi-gold/20"
                : "text-bfsi-text-muted hover:text-bfsi-text hover:bg-bfsi-muted"
            )}
          >
            <Monitor className="w-3.5 h-3.5" />
            <span>Review Dashboard</span>
          </Link>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <div className="hidden sm:flex items-center gap-1.5 text-xs text-bfsi-text-dim">
            <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            AI Online
          </div>
          <Link
            href="/submit-dispute"
            className="text-xs text-bfsi-text-dim hover:text-bfsi-gold transition-colors border border-bfsi-border hover:border-bfsi-gold/40 px-3 py-1.5 rounded-md"
          >
            Customer Form →
          </Link>
        </div>
      </div>
    </nav>
  );
}
