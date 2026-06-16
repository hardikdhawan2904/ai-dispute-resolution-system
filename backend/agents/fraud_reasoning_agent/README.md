# Fraud Reasoning Agent (FRIA) — Agent 3

**Role**: Fraud analytics, anomaly detection, identity verification, and trust score calibration  
**Model**: Groq `llama-3.1-8b-instant` (via ChatGroq)  
**Entry Point**: `validate` → `build_context` → `agent` → `finalize`  
**Framework**: LangGraph (StateGraph)  

---

## 🎯 Purpose

FRIA is the behavioral security audit engine of the system. It runs dynamically after the Orchestration Agent (Agent 5) when scheduled in the workflow execution plan to analyze transactions and customer history to determine fraud probability and verify user trust. The agent calls **6 database-backed tools** to check:
- **Transaction Timing Anomalies**: Late-night transactions (11 PM - 5 AM I4C fraud window).
- **Geographic Velocity Anomalies**: Physical impossibility of travel between consecutive transactions.
- **Spending Behavior Outliers**: Z-score statistical deviations in purchase amounts.
- **Identity & KYC Matching**: Verification of name, email, and phone against CIF records.
- **Device Fingerprints**: Risk level of the transaction device ID and geographic consistency.
- **Dispute History & Velocity**: Short-term dispute frequency and resolution favor profiles to identify friendly fraud.

FRIA synthesizes these checks into a detailed **Fraud & Trust Brief** to calibrate user risk before classification.

---

## 📋 Workflow

```
┌──────────────────────────────────────┐
│  Customer Submits Dispute Form      │
│  (case details & transaction ID)    │
└────────────┬─────────────────────────┘
             │
       [validate Node]
  (Extract case_id & verify input)
             │
     [build_context Node]
  (Pre-execute all 6 tools in parallel,  
   aggregate reports, mask PII data)
             │
       [agent Node]
  (Groq LLM reads reports, synthesizes  
   fraud findings & trust profile)
             │
      [finalize Node]
  (Validate response JSON structure,   
   stamp DB metadata, save results)
```

FRIA executes dynamically at the `fraud_reasoning` node when directed by the orchestrator. It processes case and transaction data directly from the DB, saves the behavioral fraud analytics brief back to the DB, and loops back to the `orchestration` node.

---

## ── Agent Persona ──

* **Role**: Senior Fraud Analytics and Behavioral AI Expert.
* **Goal**: Conduct transaction anomalies, location velocities, spending patterns, device fingerprints, KYC, and historical dispute behavior audits.
* **Backstory**: Deployed to block Account Takeover (ATO) attacks, telecom SIM swap fraud, vishing scams, and friendly fraud. By comparing transactional ledger patterns against historical averages, it creates calibrated risk weights.
* **Constraints**:
  - **Never classify** the dispute category (that is Agent 1's role).
  - **Never suggest** routing queues or analyst execution steps (that belongs to Agents 2 & 5).
  - Base all conclusions strictly on pre-computed database lookup tool inputs — no hallucinated facts.
  - Return **ONLY** a valid parseable JSON dictionary matching the specified output schema — no markdown, no conversational prose.

---

## ── LangGraph Pipeline Flow ──

FRIA's StateGraph consists of:
1. **`validate`**: Resolves the Case ID and ensures the required customer identifier is present.
2. **`build_context`**: Deterministically executes all 6 tools in parallel and formats their textual reports into a single prompt section.
3. **`agent`**: Invokes Groq `llama-3.1-8b-instant` to synthesize the aggregated tool findings into a coherent risk and trust assessment.
4. **`finalize`**: Validates structural JSON integrity and saves results to the DB.

---

## ── State Schema ──

The agent manages state via `FraudReasoningAgentState` defined in [state.py](file:///d:/Transaction_dispute_agent/ai-dispute-resolution-system/backend/agents/fraud_reasoning_agent/state.py):
* `messages`: Annotated message list accumulating chat history.
* `dispute_input`: Dict of raw intake form parameters.
* `case_id`: Current Case ID.
* `tool_results`: Dictionary caching output results from parallel tool execution.
* `final_output`: Synthesized JSON brief returned for DB persistence.
* `error`: Tracks execution errors.
* `tools_used`: Tracks executed tool names.
* `agent_metadata`: Includes agent name, version, model, and duration.
* `metrics`: Tracks LLM calls, tool calls, and duration.

---

## ── Database-Backed Tools ──

FRIA has access to **6 deterministic tools** defined in [tools.py](file:///d:/Transaction_dispute_agent/ai-dispute-resolution-system/backend/agents/fraud_reasoning_agent/tools.py) that query transactions, customer data, and dispute tables:

### 1. `detect_transaction_anomalies`
- **Purpose**: Checks if transaction was processed in off-hours (11 PM - 5 AM) and scans transaction counts for the customer in the last 24 hours to check for velocity breaches.
- **Inputs**: `customer_id`, `transaction_time`, `transaction_date`
- **Output**: Anomaly report with Off-Hours Flag and 24h Transaction Count.

### 2. `evaluate_location_velocity`
- **Purpose**: Scans transaction history to check geovelocity feasibility (impossible travel distance between successive transactions under 4 hours).
- **Inputs**: `customer_id`, `location`, `transaction_date`, `transaction_time`
- **Output**: Travel feasibility flag, speed calculations, and geographical risk.

### 3. `analyze_spending_behavior`
- **Purpose**: Evaluates statistical deviation (Z-score) of the disputed amount relative to the customer's typical historical average spend.
- **Inputs**: `customer_id`, `amount`
- **Output**: Deviation factor, average spend, standard deviation, and spend status.

### 4. `verify_kyc_match`
- **Purpose**: Compares dispute submission fields (name, email, phone) against the bank's internal KYC database record.
- **Inputs**: `customer_id`, `name`, `email`, `phone`
- **Output**: Verification status (`VERIFIED` | `SUSPICIOUS` | `FAILED`) and match flags.

### 5. `evaluate_device_fingerprint`
- **Purpose**: Audits login logs to check if the transaction device ID has history for this customer and whether the location matches typical profiles.
- **Inputs**: `customer_id`, `device_id`, `location`
- **Output**: Device risk rating (`LOW` | `MEDIUM` | `HIGH`) and recognition indicators.

### 6. `analyze_behavioral_patterns`
- **Purpose**: Checks customer's historical dispute counts, dispute frequency in the last 30 days (velocity), and historical resolution favor rates (percentage resolved in favor of merchant) to detect friendly fraud indicators.
- **Inputs**: `customer_id`
- **Output**: Prior dispute counts, velocity alerts, and friendly fraud risk status.

---

## ── Output Schema ──

The final output is a structured JSON brief mapping the following schema:

```json
{
  "case_id": "Unique case ID string",
  "fraud_probability": 0.85,
  "fraud_risk_level": "HIGH",
  "anomaly_detection": {
    "amount_anomaly": true,
    "time_anomaly": false,
    "velocity_anomaly": true
  },
  "device_location_risk": {
    "unrecognized_device": true,
    "location_mismatch": true
  },
  "spending_history_analysis": {
    "average_amount": 1250.0,
    "deviation_factor": 3.1
  },
  "fraud_reasoning": [
    "Transaction amount ₹5,000 exceeds 3x customer average spend.",
    "Unrecognized device ID transacted from atypical location.",
    "Dispute velocity breach flagged with multiple claims in 24 hours."
  ],
  "fraud_summary": "High risk of fraud indicated by significant spending deviation, unrecognized device fingerprint, and velocity breaches.",
  
  "user_trust_score": 0.45,
  "behavioral_risk_score": 0.60,
  "identity_verification": "SUSPICIOUS",
  "kyc_checks": {
    "name_match": true,
    "contact_match": false,
    "join_date": "2024-05-12"
  },
  "device_fingerprint": {
    "recognized_device": false,
    "location_consistent": false,
    "device_risk": "HIGH"
  },
  "dispute_behavior": {
    "prior_dispute_count": 3,
    "velocity_breach_detected": true,
    "friendly_fraud_risk": "HIGH"
  },
  "trust_reasoning": [
    "Contact number does not match registered KYC records.",
    "First transaction using device fingerprint.",
    "Customer has filed 3 disputes in the last 30 days."
  ],
  "trust_summary": "Unrecognized device logging from mismatching coordinates combined with contact details variance and high claim velocity triggers alert."
}
```

---

## ── Invocation ──

* **Function**: `run_fraud_reasoning_agent(dispute_input: dict, case_id: str) -> dict`
* **Module**: [__init__.py](file:///d:/Transaction_dispute_agent/ai-dispute-resolution-system/backend/agents/fraud_reasoning_agent/__init__.py)
* **Callers**:
  - `workflows/dispute_workflow.py` → `fraud_reasoning_node`
  - `api/routes/ops_cases.py` → manual re-analysis trigger endpoint
