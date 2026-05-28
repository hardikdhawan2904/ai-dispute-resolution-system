import type { ReactNode } from "react";
import InternalNav from "@/components/InternalNav";

export default function InternalReviewLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-bfsi-black">
      <InternalNav />
      <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 pt-24 pb-16">
        {children}
      </main>
    </div>
  );
}
