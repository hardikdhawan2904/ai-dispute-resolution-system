"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { saveAuth, getPostLoginRedirect } from "@/lib/auth";

const DEMO_CREDENTIALS = [
  { label: "Customer",          email: "customer@bank.com",     password: "customer123",  tag: "Customer Portal" },
  { label: "Fraud Analyst",     email: "analyst@bank.com",      password: "analyst123",   tag: "Operations Portal" },
  { label: "Investigator",      email: "investigator@bank.com", password: "invest123",    tag: "Operations Portal" },
  { label: "Compliance Officer",email: "compliance@bank.com",   password: "comply123",    tag: "Operations Portal" },
  { label: "Operations Admin",  email: "admin@bank.com",        password: "admin123",     tag: "Operations Portal" },
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const user = await login(email, password);
      saveAuth(user);
      router.push(getPostLoginRedirect(user.role));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-[#0f0f2a] to-slate-900 flex">
      {/* Left panel — branding */}
      <div className="hidden lg:flex w-1/2 flex-col justify-between p-12 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600/20 to-purple-600/10 pointer-events-none" />
        <div>
          <div className="flex items-center gap-3 mb-16">
            <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center">
              <span className="text-white font-bold text-lg">B</span>
            </div>
            <div>
              <div className="text-white font-bold text-xl leading-none">DisputeAI</div>
              <div className="text-blue-400 text-xs mt-0.5">BFSI Enterprise Platform</div>
            </div>
          </div>
          <h1 className="text-4xl font-bold text-white leading-tight mb-4">
            AI-Powered Dispute<br />Resolution System
          </h1>
          <p className="text-slate-400 text-lg leading-relaxed max-w-md">
            Enterprise-grade banking dispute management with LangGraph AI workflow orchestration, real-time fraud detection, and full audit compliance.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-4">
          {["LangGraph AI Workflow","Real-time Fraud Detection","Regulatory Compliance","Role-Based Security"].map((f) => (
            <div key={f} className="bg-white/5 border border-white/10 rounded-xl px-4 py-3">
              <div className="w-2 h-2 bg-blue-400 rounded-full mb-2" />
              <p className="text-white text-sm font-medium">{f}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Right panel — login form */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-md">
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div className="w-9 h-9 bg-blue-600 rounded-xl flex items-center justify-center">
              <span className="text-white font-bold">B</span>
            </div>
            <span className="text-white font-bold text-lg">DisputeAI</span>
          </div>

          <h2 className="text-2xl font-bold text-white mb-2">Welcome back</h2>
          <p className="text-slate-400 text-sm mb-8">Sign in to access your portal</p>

          <form onSubmit={handleSubmit} className="space-y-4 mb-6">
            <div>
              <label className="block text-slate-400 text-xs font-medium mb-1.5 uppercase tracking-wider">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full bg-white/5 border border-white/10 text-white rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 focus:bg-white/8 transition-all placeholder:text-slate-600"
                placeholder="your@email.com"
              />
            </div>
            <div>
              <label className="block text-slate-400 text-xs font-medium mb-1.5 uppercase tracking-wider">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full bg-white/5 border border-white/10 text-white rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 transition-all placeholder:text-slate-600"
                placeholder="••••••••"
              />
            </div>
            {error && (
              <div className="bg-red-500/10 border border-red-500/30 text-red-400 text-sm rounded-xl px-4 py-3">
                {error}
              </div>
            )}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-xl py-3 text-sm transition-all"
            >
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>

          {/* Demo accounts */}
          <div className="border-t border-white/10 pt-6">
            <p className="text-slate-500 text-xs uppercase tracking-wider mb-3">Demo accounts</p>
            <div className="space-y-1.5">
              {DEMO_CREDENTIALS.map((cred) => (
                <button
                  key={cred.email}
                  onClick={() => { setEmail(cred.email); setPassword(cred.password); setError(""); }}
                  className="w-full flex items-center justify-between px-4 py-2.5 rounded-xl bg-white/3 hover:bg-white/8 border border-white/8 transition-all group"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-1.5 h-1.5 rounded-full ${cred.tag === "Customer Portal" ? "bg-green-400" : "bg-blue-400"}`} />
                    <span className="text-slate-300 text-sm font-medium">{cred.label}</span>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full ${cred.tag === "Customer Portal" ? "bg-green-500/10 text-green-400" : "bg-blue-500/10 text-blue-400"}`}>
                    {cred.tag}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
