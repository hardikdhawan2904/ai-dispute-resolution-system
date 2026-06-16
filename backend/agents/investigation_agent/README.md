# Investigation Intelligence Agent (IIA) — Agent 2

**Role**: Operational intelligence gathering, risk profiling, and investigation planning  
**Model**: Groq `llama-3.1-8b-instant` (via ChatGroq)  
**Entry Point**: `agent` (ReAct loop) → `finalize`  
**Framework**: LangGraph (StateGraph)  

---

## 🎯 Purpose

IIA is the investigative engine of the system. It bridges the gap between raw categorization (Agent 1) and dynamic routing orchestration (Agent 5). The agent executes an autonomous ReAct loop to query historical customer records, merchant statistics, and duplicate ledgers to:
- Build a structured **Investigation Intelligence Plan**.
- Recommend the correct **Operational Queue** (CRITICAL_QUEUE, FRAUD_QUEUE, HIGH_VALUE_QUEUE, MERCHANT_QUEUE, ATM_QUEUE, STANDARD_QUEUE) for human analysts.
- Calibrate **Queue Confidence** and list the contributing logical factors.
- Assess **Investigation Complexity** (LOW, MEDIUM, HIGH, CRITICAL) and evaluate data quality.
- Identify duplicate or overlapping claims within transaction history.
- Compile a list of **Required Documents** to request from the customer and recommend specific analyst verification steps.

---

## 📋 Workflow

```
┌──────────────────────────────────────┐
│  Receives Agent 1 Output from DB     │
│  (case_id, category, amount, etc.)   │
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
 lookup tool)   determine queue &    │
     │          document checks)     │
     └───────────────┴───────────────┘
```

IIA runs after the `dispute_understanding` and deterministic `reasoning` (tag enrichment) nodes. It pulls the enriched Case records from the database using the assigned `case_id`, runs its ReAct loop, and saves the resulting intelligence plan back to the DB before routing to the `orchestration` node.

---

## ── Agent Persona ──

* **Role**: Senior AI Investigation Planner.
* **Goal**: Gather investigative intelligence, profile risk baselines, check precedents, and structure a custom-tailored checklist brief for human dispute operations.
* **Backstory**: Designed to answer the critical questions that the customer's initial claim form cannot — such as: *What is this customer's dispute history? Is this merchant known for complaints? Has this specific transaction already been disputed? What documents are legally needed to proceed?*
* **Constraints**:
  - **Never reclassify** or override Agent 1's `dispute_category`.
  - Grounded in database facts only — never fabricate historical records or merchant profiles.
  - Return **ONLY** a valid parseable JSON dictionary matching the specified output schema — no markdown, no conversational prose.
  - Represent plan uncertainty numerically via `confidence_score` (between `0.00` and `1.00`).

---

## ── LangGraph Pipeline Flow ──

IIA's StateGraph consists of:
1. **`agent`**: Invokes Groq `llama-3.1-8b-instant` to analyze the case record and autonomously decide which database tools to call next.
2. **`tools`**: Executes the database query tools (`ToolNode`) requested by the LLM.
3. **`finalize`**: Formats the final JSON plan, applies final checks (e.g. document requirements resolved via `document_rules.py`), and saves the plan.

---

## ── State Schema ──

The agent manages state via `InvestigationAgentState` defined in [state.py]
* `messages`: Annotated message list accumulating the ReAct tool call/response history.
* `agent1_output`: Input dictionary from Agent 1 (read from DB).
* `tool_results`: Dictionary caching raw database records returned by tools.
* `investigation_findings`: Intermediate findings dictionary built during execution.
* `final_output`: Synthesized investigation plan JSON payload.
* `error`: Tracks execution errors.
* `tools_used`: Tracks tools executed in the ReAct loop.
* `agent_metadata`: Includes agent name, version, model, and duration.
* `metrics`: Tracks LLM calls, tool calls, and duration.
* `confidence_score`: IIA's self-assessed confidence in the full investigation plan.

---

## ── Database-Backed Tools ──

IIA has access to **4 deterministic database-backed tools** defined in [tools.py]. They query history ledger, live dispute cases, merchant profiles, and transaction records:

### 1. `lookup_customer_history`
- **Purpose**: Queries the historical dispute database (`dispute_history`) and live cases (`dispute_cases`) for this customer's complete record. Excludes the active case from calculations.
- **Inputs**: `customer_id`
- **Output**: Summary of total previous disputes, fraud-flag rate, recency, top dispute categories, and a customer risk level classification (`LOW` | `MEDIUM` | `HIGH`).

### 2. `check_merchant_risk`
- **Purpose**: Queries the `merchant_profiles` table for pre-computed merchant risk levels and matches merchant name against blacklists. Cross-checks all historical and live dispute cases filed against the merchant.
- **Inputs**: `merchant_name`
- **Output**: Merchant risk report containing total complaints, fraud rate, top categories, and blacklist status (`LOW` | `MEDIUM` | `HIGH` | `CRITICAL`).

### 3. `find_duplicate_transaction`
- **Purpose**: Scans transactions and dispute tables to identify overlaps:
  1. Exact transaction ID match in ledger database.
  2. Exact transaction ID match in live dispute cases.
  3. Similar customer + merchant + amount within a 72-hour window.
- **Inputs**: `transaction_id`, `customer_id`, `amount`, `merchant`
- **Output**: Overlapping duplicate indicators, linked case IDs, and analyst recommendations.

### 4. `lookup_related_cases`
- **Purpose**: Fetches historical and live case resolution statistics (resolved in favor of customer vs merchant, reject counts, average resolution days) for disputes matching the same category.
- **Inputs**: `dispute_category`, `merchant` (optional)
- **Output**: Case resolution statistics to gauge precedent.

---

## ── Operational Queue Routing ──

IIA assigns cases to operations queues according to the following matrix:
* **`CRITICAL_QUEUE`**: Confirmed fraud suspicion AND amount > ₹50,000, OR identity verification fails/suspicious.
* **`FRAUD_QUEUE`**: Fraud suspicion is true but transaction amount is below critical thresholds.
* **`HIGH_VALUE_QUEUE`**: Transaction amount exceeds ₹50,000 with no fraud suspicion.
* **`MERCHANT_QUEUE`**: Claims involving merchant disputes, refund issues, product delivery failures, or subscription abuse.
* **`ATM_QUEUE`**: Claims involving ATM cash dispenser failures.
* **`STANDARD_QUEUE`**: Low-risk / standard domestic dispute claims.

---

## ── Invocation ──

* **Function**: `run_investigation_agent(agent1_output: dict) -> dict`
* **Module**: [__init__.py]
* **Callers**:
  - `workflows/dispute_workflow.py` → `investigation_node`
  - `api/routes/ops_cases.py` → POST `/{case_id}/re-investigate` (manual analyst trigger)
