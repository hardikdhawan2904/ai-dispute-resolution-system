"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function TrackSearchPage() {
  const router = useRouter();
  const [caseId, setCaseId] = useState("");
  const [error, setError]   = useState("");

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const id = caseId.trim().toUpperCase();
    if (!id) { setError("Please enter a case reference."); return; }
    if (!id.startsWith("CASE-")) { setError("Case references start with CASE-"); return; }
    router.push(`/track/${id}`);
  };

  return (
    <div style={{
      minHeight: "100vh", backgroundColor: "#0F172A",
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center",
      fontFamily: "system-ui, sans-serif", padding: "1rem",
    }}>
      <div style={{ width: "100%", maxWidth: 440 }}>

        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "#F8FAFC", letterSpacing: "0.5px" }}>
            SecureBank
          </div>
          <div style={{ fontSize: "0.7rem", color: "#64748B", letterSpacing: "1.5px", textTransform: "uppercase", marginTop: 4 }}>
            Dispute Resolution Centre
          </div>
        </div>

        {/* Card */}
        <div style={{ backgroundColor: "#1E293B", border: "1px solid #334155", borderRadius: 10, padding: "2rem" }}>
          <h1 style={{ margin: "0 0 0.375rem", fontSize: "1.15rem", fontWeight: 700, color: "#F8FAFC" }}>
            Track Your Dispute
          </h1>
          <p style={{ margin: "0 0 1.5rem", fontSize: "0.8rem", color: "#64748B" }}>
            Enter your case reference number to check the status of your dispute.
          </p>

          <form onSubmit={handleSearch}>
            <label style={{ display: "block", fontSize: "0.68rem", fontWeight: 600, color: "#94A3B8", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "0.375rem" }}>
              Case Reference
            </label>
            <input
              type="text"
              value={caseId}
              onChange={e => { setCaseId(e.target.value); setError(""); }}
              placeholder="CASE-000529"
              style={{
                width: "100%", boxSizing: "border-box",
                padding: "0.75rem 1rem", fontSize: "0.9rem",
                backgroundColor: "#0F172A", border: `1px solid ${error ? "#EF4444" : "#334155"}`,
                borderRadius: 6, color: "#F8FAFC", outline: "none",
                fontFamily: "monospace", letterSpacing: "0.05em",
              }}
            />
            {error && <div style={{ fontSize: "0.7rem", color: "#EF4444", marginTop: "0.375rem" }}>{error}</div>}

            <button
              type="submit"
              style={{
                marginTop: "1rem", width: "100%",
                padding: "0.75rem", fontSize: "0.85rem", fontWeight: 600,
                backgroundColor: "#1a5f9e", color: "#fff",
                border: "none", borderRadius: 6, cursor: "pointer",
              }}
            >
              Search →
            </button>
          </form>
        </div>

        <div style={{ textAlign: "center", marginTop: "1.5rem", fontSize: "0.68rem", color: "#334155" }}>
          For assistance, contact us at 1800-XXX-XXXX (toll free)
        </div>
      </div>
    </div>
  );
}
