"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LayoutDashboard, FileText, Upload, Bell, LogOut, ChevronRight } from "lucide-react";
import { getUser, clearAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/customer/dashboard",     label: "Dashboard",       icon: LayoutDashboard },
  { href: "/customer/disputes",      label: "My Disputes",     icon: FileText },
  { href: "/customer/uploads",       label: "Upload Docs",     icon: Upload },
  { href: "/customer/notifications", label: "Notifications",   icon: Bell },
];

export default function CustomerNav() {
  const pathname = usePathname();
  const router   = useRouter();
  const user     = getUser();

  function logout() { clearAuth(); router.push("/login"); }

  return (
    <nav className="bg-white border-b border-gray-100 shadow-sm sticky top-0 z-50">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
        {/* Brand */}
        <Link href="/customer/dashboard" className="flex items-center gap-2.5 shrink-0">
          <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center shadow-sm">
            <span className="text-white font-bold text-sm">B</span>
          </div>
          <span className="font-semibold text-gray-900 text-sm hidden sm:block">Banking Portal</span>
        </Link>

        {/* Nav links */}
        <div className="flex items-center gap-1 overflow-x-auto no-scrollbar">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-all",
                  active
                    ? "bg-blue-50 text-blue-700"
                    : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
                )}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span className="hidden sm:inline">{label}</span>
              </Link>
            );
          })}
        </div>

        {/* User */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="hidden sm:block text-right">
            <p className="text-xs font-semibold text-gray-800 leading-none">{user?.name ?? "—"}</p>
            <p className="text-[10px] text-gray-400 mt-0.5">Customer</p>
          </div>
          <button onClick={logout} className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-all" title="Sign out">
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </nav>
  );
}
