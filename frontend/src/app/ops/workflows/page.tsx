"use client";

import { useEffect, useState } from "react";
import { GitBranch, CheckCircle, XCircle, RefreshCw, Clock } from "lucide-react";
import { listCases, getWorkflowStates } from "@/lib/api";
import type { DisputeCase, WorkflowState } from "@/types";
import { cn } from "@/lib/utils";

interface CaseWorkflow { case: DisputeCase; states: WorkflowState[]; }

const LANGGRAPH_NODES = ["intake","validation","dispute_understanding","reasoning","structured_output"];
const NODE_DESC: Record<string, string> = {
  intake:                "Initial case registration and data normalization",
  validation:            "Input validation and completeness checks",
  dispute_understanding: "LLM-powered dispute classification and intent analysis",
  reasoning:             "Multi-step structured reasoning chain generation",
  structured_output:     "AI output formatting and case record assembly",
};

export default function OpsWorkflowsPage() {
  const [workflows, setWorkflows]   = useState<CaseWorkflow[]>([]);
  const [loading, setLoading]       = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selected, setSelected]     = useState<CaseWorkflow | null>(null);

  useEffect(() => {
    setLoading(true);
    listCases({ limit: 20 }).then(async (r) => {
      const withStates = await Promise.all(
        r.cases.map(async (c) => {
          try {
            const ws = await getWorkflowStates(c.case_id);
            return { case: c, states: ws.workflow_states };
          } catch { return { case: c, states: [] }; }
        })
      );
      setWorkflows(withStates);
      if (withStates.length > 0) setSelected(withStates[0]);
    }).catch(console.error).finally(() => setLoading(false));
  }, [refreshKey]);

  const avgTime = (states: WorkflowState[]) => {
    const times = states.filter((s) => s.execution_time_ms).map((s) => s.execution_time_ms!);
    return times.length ? (times.reduce((a, b) => a + b, 0) / times.length).toFixed(0) : "—";
  };

  return (
    <>
      <div className="flex items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1 h-5 bg-cyan-500 rounded-full" />
            <span className="text-xs text-cyan-400 font-semibold tracking-widest uppercase">LangGraph Orchestration</span>
          </div>
          <h1 className="text-2xl font-bold text-bfsi-text">Workflow Intelligence</h1>
          <p className="text-bfsi-text-dim text-sm mt-1">LangGraph 5-node dispute workflow execution monitoring</p>
        </div>
        <button onClick={() => setRefreshKey((k) => k + 1)} className="btn-ghost flex items-center gap-2">
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} /> Refresh
        </button>
      </div>

      {/* Pipeline diagram */}
      <div className="bfsi-card p-6 mb-6">
        <p className="section-header">LangGraph Pipeline — 5-Node Architecture</p>
        <div className="flex items-center gap-0 flex-wrap">
          {LANGGRAPH_NODES.map((node, i) => (
            <div key={node} className="flex items-center">
              <div className="text-center">
                <div className="w-12 h-12 rounded-full bg-bfsi-gold/10 border border-bfsi-gold/30 flex items-center justify-center mx-auto mb-2">
                  <span className="text-bfsi-gold text-xs font-bold">{i + 1}</span>
                </div>
                <p className="text-[10px] text-bfsi-text font-mono whitespace-nowrap">{node}</p>
                <p className="text-[9px] text-bfsi-text-dim max-w-20 text-center mt-1 hidden lg:block">{NODE_DESC[node]?.split(" ").slice(0,3).join(" ")}...</p>
              </div>
              {i < LANGGRAPH_NODES.length - 1 && (
                <div className="w-8 h-0.5 bg-bfsi-gold/30 mx-1 shrink-0" />
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Case list */}
        <div className="bfsi-card overflow-hidden">
          <div className="px-4 py-3 border-b border-bfsi-border">
            <p className="section-header mb-0">Recent Executions</p>
          </div>
          {loading ? (
            <div className="p-4 space-y-2">{[...Array(5)].map((_, i) => <div key={i} className="h-12 bg-bfsi-muted rounded animate-pulse" />)}</div>
          ) : (
            <div className="divide-y divide-bfsi-border max-h-96 overflow-y-auto">
              {workflows.map((w) => {
                const allOk = w.states.every((s) => s.success);
                const isSelected = selected?.case.case_id === w.case.case_id;
                return (
                  <button key={w.case.case_id} onClick={() => setSelected(w)} className={cn(
                    "w-full text-left px-4 py-3 transition-all hover:bg-bfsi-muted",
                    isSelected && "bg-bfsi-gold/5 border-l-2 border-bfsi-gold"
                  )}>
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-xs font-mono text-bfsi-text truncate">{w.case.case_id.slice(-12)}</p>
                        <p className="text-[10px] text-bfsi-text-dim truncate">{w.case.merchant}</p>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <span className="text-[10px] text-bfsi-text-dim">{w.states.length}/{LANGGRAPH_NODES.length}</span>
                        {allOk
                          ? <CheckCircle className="w-3.5 h-3.5 text-green-400" />
                          : <XCircle className="w-3.5 h-3.5 text-red-400" />
                        }
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Node detail */}
        <div className="lg:col-span-2">
          {selected ? (
            <div className="bfsi-card p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <p className="section-header mb-0">Execution Detail</p>
                  <p className="text-xs font-mono text-bfsi-text-dim mt-1">{selected.case.case_id}</p>
                </div>
                <div className="flex items-center gap-2 text-xs text-bfsi-text-dim">
                  <Clock className="w-3.5 h-3.5" />
                  Avg: {avgTime(selected.states)}ms
                </div>
              </div>

              {selected.states.length === 0 ? (
                <p className="text-sm text-bfsi-text-dim">No workflow state data for this case.</p>
              ) : (
                <div className="space-y-3">
                  {LANGGRAPH_NODES.map((nodeName, i) => {
                    const state = selected.states.find((s) => s.node_name === nodeName);
                    return (
                      <div key={nodeName} className={cn(
                        "flex items-start gap-4 p-4 rounded-lg",
                        state?.success ? "bg-green-400/5 border border-green-400/20" :
                        state ? "bg-red-400/5 border border-red-400/20" :
                        "bg-bfsi-muted border border-bfsi-border opacity-50"
                      )}>
                        <div className={cn(
                          "w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-xs font-bold font-mono",
                          state?.success ? "bg-green-400/20 text-green-400" :
                          state ? "bg-red-400/20 text-red-400" : "bg-bfsi-muted text-bfsi-text-dim"
                        )}>
                          {i + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-sm font-mono font-semibold text-bfsi-text">{nodeName}</p>
                            <div className="flex items-center gap-2 shrink-0">
                              {state?.execution_time_ms && (
                                <span className="text-[10px] text-bfsi-text-dim font-mono">{state.execution_time_ms.toFixed(0)}ms</span>
                              )}
                              {state?.success
                                ? <CheckCircle className="w-4 h-4 text-green-400" />
                                : state
                                ? <XCircle className="w-4 h-4 text-red-400" />
                                : null
                              }
                            </div>
                          </div>
                          <p className="text-[11px] text-bfsi-text-dim mt-0.5">{NODE_DESC[nodeName]}</p>
                          {state?.error_message && (
                            <p className="text-[10px] text-red-400 mt-1 font-mono">{state.error_message}</p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : (
            <div className="bfsi-card p-12 text-center h-full flex flex-col items-center justify-center">
              <GitBranch className="w-10 h-10 text-bfsi-text-dim mb-3" />
              <p className="text-bfsi-text-muted">Select a case to view workflow execution</p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
