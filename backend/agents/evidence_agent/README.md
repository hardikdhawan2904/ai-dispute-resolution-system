# Evidence Intelligence Agent (EIA) — Agent 4

**Role**: Evidence sufficiency audit, detail consistency validation, and document gap analysis  
**Model**: Groq `llama-3.1-8b-instant` (via ChatGroq)  
**Entry Point**: `agent` (ReAct loop) → `finalize`  
**Framework**: LangGraph (StateGraph)  

---

## 🎯 Purpose

EIA is the document audit engine of the system. It processes uploads and pending document requests to determine whether enough proof exists to proceed with the dispute. It runs conditionally when the Workflow Orchestration Agent (Agent 5) routes the case to it. The agent calls **5 database-backed tools** to:
- Verify that required documents have been uploaded or formally requested.
- Calculate an **Evidence Completeness Score (0-100%)** based on customer-obtainable documents (ignoring bank-internal files).
- Validate transaction **detail consistency** (comparing amount, merchant, date, and type across database tables and dispute fields).
- Calibrate the overall **Evidence Strength** (HIGH, MEDIUM, LOW) and compute a numerical score (0.0 - 1.0).
- Recommend the **Next Document Request** if missing required customer evidence blocks the investigation.

---

## 📋 Workflow

```
┌──────────────────────────────────────┐
│  Receives Case Info & Invocation     │
│  (case_id, required documents list)  │
└────────────┬─────────────────────────┘
             │
       [agent Node] ◄────────────────┐
  (Groq ReAct loop - LLM reasoning)  │
             │                       │
      (Has tool call?)               │
       /          \                  │
     (Yes)        (No)               │
     /              \                │
[tools Node]   [finalize Node]       │
(Run database  (Synthesize output,   │
 lookup tool)   determine next step  │
     │          and documentation)   │
     └───────────────┴───────────────┘
```

EIA is run conditionally at the `evidence` node if Agent 5 (WOA) sets `next_agent=EVIDENCE_AGENT`. It processes details, updates the Case record with the evidence assessment JSON, and marks `EVIDENCE_AGENT` as complete in the workflow plan.

---

## ── Agent Persona ──

* **Role**: Senior Evidence Analyst.
* **Goal**: Evaluate completeness, verify detail consistency, calculate evidence strength, and identify document requests needed from the customer.
* **Backstory**: Built because 40% of dispute cases stalled due to incomplete or contradictory documentation. EIA operates strictly in the evidence domain — it does not assign queues, verify fraud patterns, or decide approvals/refunds.
* **Constraints**:
  - Grounded in database facts and physical file listings — never hallucinate document files.
  - Never classify disputes or override Agent 1/2 classifications.
  - Return **ONLY** a valid parseable JSON dictionary matching the specified output schema — no markdown, no conversational prose.

---

## ── LangGraph Pipeline Flow ──

EIA's StateGraph consists of:
1. **`agent`**: Invokes Groq `llama-3.1-8b-instant` to audit the database records and determine which evidence tools to run.
2. **`tools`**: Executes the deterministic evidence validation tools (`ToolNode`).
3. **`finalize`**: Formats the final JSON assessment and saves the output to the DB.

---

## ── State Schema ──

The agent manages state via `EvidenceAgentState` defined in [state.py](file:///d:/Transaction_dispute_agent/ai-dispute-resolution-system/backend/agents/evidence_agent/state.py):
* `messages`: Message list accumulating the ReAct tool call/response history.
* `dispute_input`: Dict of raw intake form parameters.
* `document_texts`: OCR block strings.
* `case_id`: Current Case ID.
* `supporting_evidence`: checklist of active fraud indicators.
* `document_section`: Document section string passed in prompt.
* `final_case`: Synthesized case output structure.
* `error`: Tracks execution errors.
* `tools_used`: Tracks executed tools.
* `agent_metadata`: Includes agent name, version, model, and duration.
* `metrics`: Tracks LLM calls, tool calls, and duration.

---

## ── Database-Backed Tools ──

EIA has access to **5 deterministic tools** defined in [tools.py](file:///d:/Transaction_dispute_agent/ai-dispute-resolution-system/backend/agents/evidence_agent/tools.py) that query transaction details, document requests, and case folders:

### 1. `evaluate_evidence_completeness`
- **Purpose**: Computes completeness percentage (0-100%) against required customer-obtainable documents.
- **Rules**:
  - Splits required documents into customer-obtainable and bank-obtainable (e.g. server logs). Bank-obtainable files do not count against the customer's score.
  - If no requirements are defined: `evidence_match=true` yields 90% completeness, `false` yields 30%, else 50%.
  - If requirements are defined: credits completed formal requests and uploads (if `evidence_match=true`).
- **Inputs**: `case_id`
- **Output**: Completeness score percentage, note, missing customer docs list, and pending bank-obtainable docs list.

### 2. `identify_missing_evidence`
- **Purpose**: Identifies unfulfilled required customer documents and bank-obtainable files. Calculates if the missing documents block the investigation from proceeding.
- **Rules**:
  - `gaps_block_investigation` is `true` if more than 50% of the required customer documents are missing.
- **Inputs**: `case_id`
- **Output**: List of missing customer documents, pending document requests, pending bank-obtainable documents, and a blocking boolean indicator.

### 3. `validate_evidence_consistency`
- **Purpose**: Cross-checks case transaction details (amount, merchant name, type, date) against the original database transaction record.
- **Rules**:
  - Flag mismatches if the amount differs by > 1% or the merchant name deviates significantly.
  - Flags if Agent 1 marked `evidence_match=false`.
- **Inputs**: `case_id`
- **Output**: Consistency status (`Consistent` boolean), discrepancy count, and list of specific issues found.

### 4. `assess_evidence_strength`
- **Purpose**: Calculates overall evidence quality score (0.0 to 1.0) and assigns a strength level (`HIGH` | `MEDIUM` | `LOW`).
- **Scoring Weights**:
  - Base score: `0.50`
  - `evidence_match=true`: `+0.25`, `false`: `-0.20`
  - Customer completeness adjustment: up to `+/- 0.10` max (derived from `(completeness - 0.5) * 0.20`).
  - Upload file counts: `2+` files: `+0.05`, `1` file: `+0.02`.
  - Agent 2 Data Quality adjustment: `(dq_score - 0.75) * 0.10`.
  - Score >= 0.70 → `HIGH` (sufficient); >= 0.45 → `MEDIUM` (proceed with caution); else `LOW` (action required).
- **Inputs**: `case_id`
- **Output**: Strength level, numeric score, and list of contributing factors.

### 5. `determine_next_document_request`
- **Purpose**: Recommends the next document type to formally request from the customer. Checks active pending requests to avoid duplicate requests.
- **Rules**:
  - Prioritizes required customer documents from the plan that have not yet been requested or uploaded.
  - Fallback: if `evidence_match=false` and no specific required document gap exists, recommends "Additional supporting documentation".
- **Inputs**: `case_id`
- **Output**: Recommended request type and the logical reason why it is needed.

---

## ── Output Schema ──

The final output is a structured JSON assessment mapping the following fields:

```json
{
  "evidence_completeness": 77,
  "evidence_strength": "HIGH",
  "evidence_strength_score": 0.82,
  "evidence_consistent": true,
  "consistency_issues": [],
  "missing_documents": [
    "DEVICE_LOGIN_HISTORY"
  ],
  "recommended_document_requests": [
    "DEVICE_LOGIN_HISTORY"
  ],
  "investigation_blocked": false,
  "evidence_summary": [
    "Customer provided 2 of 3 required documents.",
    "Uploaded bank statement matches transaction amount ₹34,189.00 exactly.",
    "Transaction date and merchant align with the statement record."
  ],
  "review_recommendation": "Sufficient evidence to proceed with standard investigation; pending device logs should be requested.",
  "manual_evidence_review": false,
  "tool_decisions": [
    {
      "tool": "evaluate_evidence_completeness",
      "reason": "Verify baseline customer document fulfillment status."
    }
  ]
}
```

---

## ── Invocation ──

* **Function**: `run_evidence_agent(case_id: str) -> dict`
* **Module**: [__init__.py](file:///d:/Transaction_dispute_agent/ai-dispute-resolution-system/backend/agents/evidence_agent/__init__.py)
* **Callers**:
  - `workflows/dispute_workflow.py` → `evidence_node` (invoked conditionally based on Agent 5 workflow plan routing)
  - `api/routes/ops_cases.py` → POST `/{case_id}/run-evidence-agent` (manual triggers)
