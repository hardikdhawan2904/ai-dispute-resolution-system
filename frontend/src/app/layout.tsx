import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "react-hot-toast";

export const metadata: Metadata = {
  title: "BFSI Dispute Resolution Platform | AI Operations",
  description: "Enterprise AI-powered banking dispute investigation and resolution system",
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: "#14141f",
              color: "#e2e8f0",
              border: "1px solid #1e1e32",
              borderRadius: "8px",
              fontSize: "13px",
            },
            success: {
              iconTheme: { primary: "#10b981", secondary: "#14141f" },
            },
            error: {
              iconTheme: { primary: "#ef4444", secondary: "#14141f" },
            },
          }}
        />
        {children}
      </body>
    </html>
  );
}
