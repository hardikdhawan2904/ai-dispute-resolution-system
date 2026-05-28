"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getUser, isBankStaff } from "@/lib/auth";
import OpsNav from "@/components/ops/OpsNav";

export default function OpsLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    const user = getUser();
    if (!user) { router.replace("/login"); return; }
    if (!isBankStaff()) { router.replace("/submit-dispute"); return; }
  }, []);

  return (
    <div className="min-h-screen bg-bfsi-black">
      <OpsNav />
      <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 pt-24 pb-16">
        {children}
      </main>
    </div>
  );
}
