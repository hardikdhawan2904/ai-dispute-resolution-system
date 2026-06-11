# Agent 1: Identity & Trust Intelligence Agent (ITIA)

The **Identity & Trust Intelligence Agent (ITIA)** evaluates customer registries, device history, transaction locations, and prior dispute patterns. It runs as the very first agent in the processing pipeline (right after initial intake validation and document sufficiency checks) to establish a customer profile trust baseline before downstream dispute categorization and workflow planning take place.

---

## ── Metadata & Configuration ──

* **Full Name**: Identity & Trust Intelligence Agent (ITIA)
* **Code Registry**: [identity_trust_agent](file:///d:/Transaction_dispute_agent/ai-dispute-resolution-system/backend/agents/identity_trust_agent)
* **Domain**: BFSI (Banking, Financial Services, and Insurance)
* **Framework**: LangGraph (StateGraph)
* **LLM Engine**: ChatGroq (Llama-3.1-8B-Instant, Temperature 0)

---

## ── Agent Persona ──

* **Role**: Senior Identity Verification and Behavioral Analyst.
* **Goal**: Perform identity validation, device fingerprint evaluation, and dispute behavior checks. Synthesize findings into a structured trust intelligence JSON brief.
* **Backstory**: Developed to mitigate losses from friendly fraud and account takeover (ATO) scams. By verifying client profile metadata and scanning historical velocity profiles, ITIA helps determine whether a dispute claim is verified, suspicious, or failed.
* **Constraints**:
  - Never classify the dispute category (that is Agent 2's role).
  - Never suggest manual routing queues or analyst steps (that belongs to Agents 3 & 4).
  - Base all conclusions strictly on pre-computed tool records and database values.
  - Return ONLY valid, parseable JSON with no conversational prose.

---

## ── LangGraph Pipeline Flow ──

The agent's internal Graph topology executes as a linear pre-computed pipeline to optimize response latency and enforce deterministic calibrations:

```mermaid
graph LR
    A[validate] --> B[build_context]
    B --> C[agent]
    C --> D[finalize]
```

1. **`validate` Node**: Parses input dispute details, extracts and registers the assigned Case ID.
2. **`build_context` Node**: Runs all lookup tools in parallel threads, gathers results, masks PII data, and structures the prompt payload.
3. **`agent` Node**: Invokes the ChatGroq model with the pre-assembled tool outputs for single-shot synthesis.
4. **`finalize` Node**: Parses the LLM's JSON output, stamps execution metrics, and applies deterministic server-side trust score overrides/calibrations.

---

## ── State Schema ──

The agent maintains state through `IdentityTrustAgentState` defined in [state.py](file:///d:/Transaction_dispute_agent/ai-dispute-resolution-system/backend/agents/identity_trust_agent/state.py):

* `messages`: Annotated list accumulating chat history.
* `dispute_input`: Dictionary of raw case submission details.
* `case_id`: Assigned case identifier.
* `tool_results`: Dictionary caching output results from parallel tool execution.
* `final_output`: Synthesized JSON brief returned for database persistence.
* `error`: Optional string tracking failure reasons.
* `tools_used`: List tracking executed tool names.
* `agent_metadata`: Dictionary recording agent version, model, and invocation timestamps.
* `metrics`: Execution duration and token counters.

---

## ── Database-Backed Tools ──

All tools are located in [tools.py](file:///d:/Transaction_dispute_agent/ai-dispute-resolution-system/backend/agents/identity_trust_agent/tools.py):

### 1. `verify_kyc_match`
* **Purpose**: Validates customer profile credentials against core banking customer CIF records.
* **Inputs**:
  - `customer_id` (string)
  - `name` (string)
  - `email` (string)
  - `phone` (string)
* **Output**: Match verdicts for email, name, and phone (match, mismatch, or missing).

### 2. `evaluate_device_fingerprint`
* **Purpose**: Scans transaction logs to evaluate the familiarity of the customer's device ID and geographic locations.
* **Inputs**:
  - `customer_id` (string)
  - `device_id` (string)
  - `location` (string)
* **Output**: Device history checks, location consistent flags, and transaction risk profiles.

### 3. `analyze_behavioral_patterns`
* **Purpose**: Queries dispute history databases to count prior disputes, verify resolution ratios, and detect velocity breaches.
* **Inputs**:
  - `customer_id` (string)
* **Output**: Prior dispute count, dispute velocity alerts, and friendly fraud indicators.

---

## ── Synthesized Output Schema ──

The final output is a structured JSON brief mapping the following schema:

```json
{
  "case_id": "Unique case ID string",
  "user_trust_score": 0.95,
  "behavioral_risk_score": 0.05,
  "identity_verification": "VERIFIED",
  "kyc_checks": {
    "name_match": true,
    "contact_match": true,
    "join_date": "2024-01-15"
  },
  "device_fingerprint": {
    "recognized_device": true,
    "location_consistent": true,
    "device_risk": "LOW"
  },
  "dispute_behavior": {
    "prior_dispute_count": 0,
    "velocity_breach_detected": false,
    "friendly_fraud_risk": "LOW"
  },
  "trust_reasoning": [
    "KYC match validated successfully against customer CIF records.",
    "Device fingerprint recognized with consistent location history.",
    "Zero prior disputes recorded; behavioral profile flags no anomalies."
  ],
  "trust_summary": "Customer identity matches bank registry records with a highly trusted device fingerprint and no history of dispute abuse."
}
```

---

## ── Invocation ──

The agent is exposed via a standard entry point:
* **Function**: `run_identity_trust_agent(dispute_input: dict, case_id: str) -> dict`
* **Module**: [__init__.py](file:///d:/Transaction_dispute_agent/ai-dispute-resolution-system/backend/agents/identity_trust_agent/__init__.py)
* **Callers**: Called from `dispute_workflow.py` at the `identity_trust` node, or directly from the ops re-analysis API endpoints in `ops_cases.py`.
