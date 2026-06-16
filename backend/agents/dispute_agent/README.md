# Dispute Understanding Agent (ARIA) — Agent 1

**Role**: Dispute intake, classification, and initial triage risk analysis  
**Model**: Groq `llama-3.1-8b-instant` (via ChatGroq)  
**Entry Point**: `validate`  
**Framework**: LangGraph (StateGraph)  

---

## 🎯 Purpose

ARIA is the classification and understanding core of the dispute resolution system. It analyzes customer-submitted dispute information, processes transaction details, and executes a ReAct agent-tools loop to:
- Classify inbound disputes into exactly one of **9 canonical dispute categories**.
- Determine if **fraud suspicion** is present (`true`/`false`).
- Assign an initial **priority level** (CRITICAL, HIGH, MEDIUM, LOW) based on the transaction amount and fraud signals.
- Generate semantic **risk tags** to guide downstream processing.
- Calculate a calibrated **confidence score** representing LLM self-assessed certainty.
- Produce a structured JSON case record for DB storage and analyst queue ingestion.

---

## 📋 Workflow

```
┌──────────────────────────────────────┐
│  Customer Submits Dispute Form      │
│  (comment, fraud_selected, evidence)│
└────────────┬─────────────────────────┘
             │
       [validate Node]
  (Extract case_id & verify fields)
             │
     [build_evidence Node]
  (Format fraud checklist & OCR block)
             │
       [agent Node] ◄────────────────┐
  (Groq ReAct loop - LLM reasoning)  │
             │                       │
      (Has tool call?)               │
       /          \                  │
     (Yes)        (No)               │
     /              \                │
[tools Node]   [finalize Node]       │
(Run tool)    (Parse LLM JSON,      │
     │         stamp DB metadata)    │
     └───────────────┴───────────────┘
```

ARIA runs after the `fraud_reasoning` node within the main workflow (`dispute_workflow.py`). It receives the raw inputs alongside pre-computed flags, processes them, and passes its output to the `reasoning` node for tag enrichment.

---

## ── Agent Persona ──

* **Role**: Senior AI Dispute Analyst.
* **Goal**: Triage, categorize, and verify evidence-match status for all inbound customer dispute cases.
* **Backstory**: Built to eliminate manual triage inconsistencies, enforce RBI dispute compliance, and accelerate initial fraud containment.
* **Constraints**:
  - Grounded in factual analysis only — never provide legal or financial advice.
  - Never fabricate transaction details or metadata not present in the inputs.
  - Return **ONLY** a valid parseable JSON dictionary matching the specified output schema — no markdown, no conversational prose.
  - Express uncertainty numerically via `confidence_score` (between `0.10` and `1.00`).

---

## ── LangGraph Pipeline Flow ──

ARIA's internal StateGraph consists of the following nodes:
1. **`validate`**: Resolves the `case_id` and checks for mandatory intake parameters. Set as the entry point from `agent.yaml`.
2. **`build_evidence`**: Formats the fraud checklist and structures OCR document blocks as prompts.
3. **`agent`**: Invokes the LLM (Groq `llama-3.1-8b-instant`) to reason and decide whether to call understanding tools or output the final JSON record.
4. **`tools`**: Runs the requested understanding tools (`ToolNode`).
5. **`finalize`**: Validates the LLM's final JSON output structure and stamps server-owned metadata.

---

## ── State Schema ──

The agent manages internal state using `DisputeAgentState` defined in [state.py]:
* `messages`: Annotated message list accumulating the ReAct tool call/response history.
* `dispute_input`: Dict of raw intake form parameters.
* `document_texts`: List of string segments extracted from uploaded documents.
* `case_id`: The system-assigned unique Case ID.
* `supporting_evidence`: Formatted checklist of active fraud indicators.
* `document_section`: Pre-formatted document OCR text passed to the LLM.
* `final_case`: The completed, parsed case record JSON.
* `error`: Tracks execution errors, if any.
* `tools_used`: Tracks tools executed in the ReAct loop.
* `agent_metadata`: Statically includes agent name, version, model, and duration.
* `metrics`: tracks LLM calls, tool calls, and duration in milliseconds.

---

## ── Understanding Tools ──

ARIA has access to **4 deterministic understanding tools** defined in [tools.py] They perform calculations in-memory without database queries to prevent historical bias in classification:

### 1. `assess_transaction_context`
- **Purpose**: Evaluates transaction risk profiles based on amount tiers (RBI circular 2017 thresholds), off-hours anomalies, card-not-present (CNP) channels, and international merchants.
- **Inputs**: `amount`, `transaction_type`, `merchant`, `transaction_date`, `transaction_time`
- **Output**: Structured risk report containing risk signals and liability advice.

### 2. `score_fraud_indicators`
- **Purpose**: Scans comments and metadata checklists for fraud keywords. Calibrated to Indian Cyber Crime Coordination Centre (I4C) taxomony (e.g. OTP sharing, vishing impersonations, remote access, sim swap).
- **Inputs**: `customer_comment`, `otp_received`, `otp_shared`, `bank_impersonation`, `remote_access`, `phishing_link`, `sim_swap_suspected`, `card_lost`, `device_lost`, `bank_contacted`, `card_blocked`
- **Output**: Composite fraud signal level (`NONE` | `LOW` | `MEDIUM` | `HIGH` | `CRITICAL`) and RBI liability recommendation.

### 3. `verify_evidence_match`
- **Purpose**: Verifies whether submitted document text corroborates the customer's claimed amount, merchant name, and dispute description.
- **Inputs**: `document_text`, `claimed_amount`, `claimed_merchant`, `dispute_description`
- **Output**: Matching verdict (`MATCH` | `PARTIAL_MATCH` | `MISMATCH` | `NO_DOCUMENTS` | `CANNOT_VERIFY`) and explanation.

### 4. `compute_confidence_score`
- **Purpose**: Calibrates final classification certainty using completeness, fraud signal consistency, document verdicts, and internal contradictions.
- **Inputs**: `fields_complete`, `comment_quality`, `fraud_signal_level`, `fraud_category_consistent`, `evidence_verdict`, `has_contradictions`
- **Output**: Final confidence score (between `0.10` and `1.00`).

---

## ── Canonical Categories & Priorities ──

### Canonical Dispute Categories (RBI/NPCI Framework)
* **Unauthorized Transaction**: Customer denies initiating or authorizing the transaction.
* **Duplicate Transaction**: Customer was charged multiple times for a single purchase.
* **Refund Not Received**: Merchant promised a refund but funds were not credited.
* **Product Not Received**: Customer paid for goods/services but never received them.
* **Subscription Abuse**: Customer cancelled a recurring subscription but charges continued.
* **ATM Cash Issue**: ATM debited customer's account but failed to dispense cash.
* **Merchant Dispute**: Disagreement over quality, billing amount, or merchant service.
* **Friendly Fraud**: Dispute initiated by customer for a legitimate charge they forgot or regret.
* **Other**: Non-standard dispute categories.

### Priority Matrix
* **CRITICAL**: Confirmed fraud suspicion AND amount > ₹50,000, OR identity theft indicators.
* **HIGH**: Fraud suspicion is present, OR amount > ₹50,000, OR multiple high-risk tags.
* **MEDIUM**: Amount ₹10,000–₹50,000, OR standard merchant/refund disputes.
* **LOW**: Low-value merchant complaints with simple resolution paths.

---

## ── Invocation ──

* **Function**: `run_dispute_agent(dispute_input: dict, document_texts: List[str], case_id: str) -> dict`
* **Module**: [__init__.py]
* **Callers**:
  - `workflows/dispute_workflow.py` → `dispute_understanding_node`
  - `api/routes/ops_cases.py` → manual re-analysis trigger endpoint
