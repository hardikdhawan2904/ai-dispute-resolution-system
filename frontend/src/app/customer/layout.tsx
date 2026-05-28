"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getUser, isCustomer } from "@/lib/auth";
import CustomerNav from "@/components/customer/CustomerNav";

export default function CustomerLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    const user = getUser();
    if (!user) { router.replace("/login"); return; }
    if (!isCustomer()) { router.replace("/ops/dashboard"); return; }
  }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      <CustomerNav />
      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        {children}
      </main>
    </div>
  );
}
