# AI Dispute Resolution System

Enterprise-grade, multi-agent banking fraud and dispute resolution platform. Built for BFSI operations teams — automates dispute intake, classification, investigation, fraud detection, evidence verification, orchestration, and customer communication through 6 specialized AI agents and 48 fraud intelligence tools.

---

## Architecture

```mermaid
graph TD
    A([Customer Submission]) --> B[FastAPI Backend]
    B --> C[Intake & Validation]
    C --> D{Document Check}

    D -- Sufficient --> E["Agent 1 · ARIA\nDispute Understanding Agent"]
    D -- Insufficient --> Z([Halt: Pending Documents])

    E --> F["Agent 2 · IIA\nInvestigation Intelligence Agent"]
    F --> G["Agent 3 · WOA\nWorkflow Orchestration Agent\n─────────────────────────\nSingle source of truth for routing"]

    G -- "FRAUD_AGENT" --> H["Agent 4 · FRIA\nFraud Reasoning Agent\n─────────────────────────\n48 tools · Channel-aware"]
    G -- "EVIDENCE_AGENT" --> I["Agent 5 · EIA\nEvidence Intelligence Agent\n─────────────────────────\n5 tools"]
    G -- "No agents remaining" --> J[Structured Output Node]

    H --> G
    I --> G
    J --> K[(PostgreSQL Database)]
    K --> L([Ops Review Portal])

    E -. "Async Event" .-> M["Agent 6 · CCA\nCustomer Communication Agent"]
    K -. "Status / Analyst Action" .-> M
    M --> N([Email · Outlook SMTP])

    style A fill:#1E293B,stroke:#334155,color:#F8FAFC
    style Z fill:#1E293B,stroke:#334155,color:#F8FAFC
    style L fill:#1E293B,stroke:#334155,color:#F8FAFC
    style B fill:#0F172A,stroke:#2563EB,color:#93C5FD
    style C fill:#0F172A,stroke:#334155,color:#94A3B8
    style D fill:#0F172A,stroke:#D97706,color:#FCD34D
    style E fill:#0F172A,stroke:#2563EB,color:#93C5FD
    style F fill:#0F172A,stroke:#2563EB,color:#93C5FD
    style G fill:#0F172A,stroke:#7C3AED,color:#C4B5FD
    style H fill:#0F172A,stroke:#DC2626,color:#FCA5A5
    style I fill:#0F172A,stroke:#059669,color:#6EE7B7
    style J fill:#0F172A,stroke:#334155,color:#94A3B8
    style K fill:#0F172A,stroke:#0EA5E9,color:#7DD3FC
    style M fill:#0F172A,stroke:#EA580C,color:#FFEDD5
    style N fill:#1E293B,stroke:#334155,color:#F8FAFC
```

---

## Data Flow — Form vs Database

**Save-first architecture.** The customer form is saved to `dispute_cases` before any agent runs. All agents read from the database — never from the raw form in memory.

At submission time, key fields are overwritten from the bank's own records:
- `email`, `phone` → from `bank_customers` (never trust form values)
- `amount`, `merchant`, `transaction_type` → from `transactions` (never trust form values)

**DB-first fraud scoring (ARIA).** `score_fraud_indicators` queries `account_events` for bank-verified signals before trusting form flags. DB-verified signals carry full weight; unverifiable customer claims (otp_shared, bank_impersonation, remote_access) carry 60% weight.

---

## Agents

### Agent 1 — ARIA (Dispute Understanding Agent)

Reads the customer's dispute data from `dispute_cases` (already saved). Runs 3 pre-computed tools server-side before the LLM call.

**Tools:**
- `assess_transaction_context` — RBI liability tiers, off-hours risk, CNP channel flags, UPI/IMPS patterns (reads form metadata — factual timestamps, not interpretable customer claims)
- `score_fraud_indicators` — DB-first fraud scoring. Queries `account_events` for bank-verified signals first, falls back to form flags at 60% weight. Unverifiable claims (otp_shared, bank_impersonation, remote_access, screen_sharing, phishing_link, device_lost) are narrative context only.
- `verify_evidence_match` — OCR document text vs claimed merchant, amount, and document type

**DB-verified signals in score_fraud_indicators:**

| account_events type | Replaces form field |
|---|---|
| `SIM_SWAP_DETECTED` | `sim_swap_suspected` |
| `DEVICE_REGISTERED` + `customer_devices` | `new_device` |
| `MOBILE_NUMBER_CHANGED` | `mobile_number_changed` |
| `CARD_LOST_REPORTED` | `card_lost` |
| `CARD_BLOCKED` | `card_blocked` |
| `OTP_DELIVERED` | `otp_received` |
| `CUSTOMER_CONTACT_LOGGED` | `bank_contacted` |
| `UPI_COLLECT_REQUEST_RECEIVED` | `collect_request` |

**Fraud signal score → used for:**
1. LLM prompt context (written explanation of fraud signals)
2. `confidence_score` adjustment: CRITICAL/HIGH + correct fraud category = +0.15, MEDIUM = +0.08, wrong category = −0.12

**Outputs:** `dispute_category`, `fraud_suspicion`, `confidence_score`, `risk_tags`, `evidence_match`, `key_findings`, `case_summary`

---

### Agent 2 — IIA (Investigation Intelligence Agent)

Runs 4 database-backed tools to design a targeted investigation plan. **100% DB — no form data.**

**Tools:**
- `lookup_customer_history` — dispute frequency, fraud-flag count, chargeback ratios, risk level. Reads: `dispute_cases`, `dispute_history`
- `check_merchant_risk` — category risk, complaint volume, blacklist status, fraud rate. Reads: `merchant_profiles`, `dispute_cases`, `dispute_history`
- `find_duplicate_transaction` — identical merchant/amount/date within 72-hour window. Reads: `dispute_cases`, `transactions`
- `lookup_related_cases` — outcomes of similar historical disputes. Reads: `dispute_history`, `dispute_cases`

**Outputs:** `investigation_plan`, `required_documents`, `recommended_queue`, `investigation_complexity`, `recommended_steps`

---

### Agent 3 — WOA (Workflow Orchestration Agent)

Acts as the authoritative workflow controller. **100% DB — reads from `dispute_cases` only.** Compliance review has been removed — high-risk tags trigger escalation, not a separate agent.

**Routing logic:**
- `FRAUD_AGENT` — if `fraud_suspicion = true` OR Unauthorized Transaction / Friendly Fraud category
- `EVIDENCE_AGENT` — if document gaps exist, ATM Cash Issue, Other
- `MERCHANT_AGENT` — Merchant Dispute, Refund Not Received, Product Not Received, Subscription Abuse, Duplicate Transaction

**Tools:** `evaluate_case_complexity`, `determine_required_agents`, `recommend_workflow_path`, `assess_escalation_need`, `estimate_workload`, `determine_next_execution_step`

**`workflow_reasoning` uses factual/past tense** ("was activated", "triggered") — not future/action tense ("is required", "must be done").

**Outputs:** `workflow_path`, `required_agents`, `next_agent`, `workflow_complexity`, `escalation_required`, `analyst_level`, `estimated_investigation_hours`

---

### Agent 4 — FRIA (Fraud Reasoning Agent)

**48 fraud intelligence tools across 4 transaction channels.** All tools run in parallel via `ThreadPoolExecutor`. All numeric fraud scores are server-side deterministic. The LLM synthesises narrative reasoning only. Form fields do **not** contribute to `fraud_probability` — they appear in the LLM narrative only.

#### Channel Routing

| Channel | Transaction Types |
|---|---|
| **UPI** | UPI |
| **Internet Banking** | Net Banking, Mobile Banking, IMPS, NEFT, RTGS |
| **Card POS** | Debit Card, Credit Card |
| **ATM** | ATM, ATM Cash, Cash Withdrawal |

`device_id` is NULL for Card POS and ATM in the DB — POS terminals and ATMs are merchant/bank hardware, not customer devices.

---

#### Core Digital Tools (UPI + Internet Banking) — 7 tools

| Tool | What it detects |
|---|---|
| `detect_transaction_anomalies` | Off-hours (11PM–5AM); rapid-fire velocity (< 15 seconds gap) |
| `evaluate_location_velocity` | GPS Haversine geovelocity: MEDIUM ≥ 150 km/h (+0.15), HIGH ≥ 500 (+0.25), CRITICAL ≥ 900 (+0.35). Reads `transactions.latitude/longitude` |
| `analyze_spending_behavior` | Z-score deviation from 30-transaction baseline |
| `verify_kyc_match` | CIF comparison vs `bank_customers`; Compromise Risk HIGH for full match on Unauthorized Transaction |
| `evaluate_device_fingerprint` | Device ID history from `transactions.device_id`. NULL for Card POS/ATM |
| `analyze_behavioral_patterns` | Prior disputes (deduplicated across `dispute_cases` + `dispute_history`), 30-day velocity, friendly fraud rate |
| `evaluate_merchant_risk_intelligence` | Merchant risk tier, blacklist, fraud complaints from `merchant_profiles` |

---

#### UPI-Specific Tools — 5 tools

| Tool | Score |
|---|---|
| `analyze_new_beneficiary_risk` | First-time high-value transfer | +0.20 |
| `detect_upi_collect_request_fraud` | DB-first: `UPI_COLLECT_REQUEST_RECEIVED` in account_events | +0.30 |
| `analyze_beneficiary_velocity` | 5+ customers to same UPI ID | +0.30 |
| `evaluate_upi_handle_reputation` | 5+ fraud reports on UPI handle | +0.35 |
| `analyze_dormant_beneficiary_risk` | Beneficiary < 7 days old | +0.20 |

---

#### Internet Banking Tools — 4 tools

| Tool | Score |
|---|---|
| `detect_impossible_login_travel` | Different city within 2 hours | +0.35 |
| `analyze_device_change_large_transfer` | New device + amount > 2× average | +0.30 |
| `detect_password_reset_transaction_pattern` | Transaction after password reset | +0.30 |
| `analyze_mobile_number_change_risk` | Mobile changed before transaction | +0.35 |

---

#### Card POS Tools — 15 tools

| Tool | Score |
|---|---|
| `analyze_card_velocity` | 3+ transactions in 5 min | +0.25 |
| `evaluate_atm_pos_distance` | ATM + POS different city within 1h | +0.35 |
| `analyze_foreign_usage` | International when 90%+ history domestic | +0.30 |
| `analyze_card_present_anomalies` | Late-night / high-risk merchant / 3× average | +0.15–0.25 |
| `detect_merchant_compromise_pattern` | 10+ disputes at merchant in 7 days | +0.25–0.40 |
| `analyze_first_time_merchant` | Never used merchant + amount > 1.5× | +0.15 |
| `evaluate_merchant_resolution_history` | >70% customer-favor dispute rate | +0.15–0.25 |
| `detect_card_testing_pattern` | ≤₹50 micro-transactions before fraud | +0.30 |
| `analyze_multi_merchant_burst` | 4+ merchants in 30 minutes | +0.25 |
| `evaluate_mcc_risk` | Electronics/Travel/Crypto = HIGH risk category | +0.10–0.20 |
| `analyze_decline_success_pattern` | 2+ declined before success | +0.20 |
| `check_refund_reversal_absence` | Refund claimed but no reversal in DB | +0.15 |
| `analyze_card_entry_mode_risk` | MANUAL_ENTRY +0.30, SWIPE +0.20, TAP +0.05, CHIP +0.00. Reads `transactions.card_entry_mode` | varies |
| `detect_emv_fallback` | Customer normally uses chip but this txn was SWIPE | +0.25 |
| `analyze_contactless_abuse` | 4+ small NFC taps in 1 hour (entry_mode=TAP only) | +0.20 |

---

#### ATM Tools — 6 tools

| Tool | Score |
|---|---|
| `analyze_atm_velocity` | 3+ withdrawals in 1 hour | +0.25 |
| `evaluate_atm_geovelocity` | Different city ATM in 2 hours | +0.35 |
| `analyze_cash_withdrawal_patterns` | Amount > 3× average or 3+ in 24h | +0.15 |
| `analyze_consecutive_atm_withdrawals` | 3+ same-amount withdrawals | +0.25 |
| `analyze_foreign_atm_usage` | International when 80%+ domestic | +0.35 |
| `detect_sim_swap_atm_pattern` | SIM swap + ATM withdrawal | +0.40 |

---

#### Universal Tools — 6 tools (all channels, capped at 0.60 total)

| Tool | Score |
|---|---|
| `evaluate_historical_fraud_victim_score` | Prior fraud cases | +0.10 |
| `detect_account_takeover_pattern` | **NARRATIVE ONLY** — form-based ATO flags, no probability impact | — |
| `analyze_mule_account_indicators` | 8+ txns/24h or 5+ beneficiaries/2h | +0.30 |
| `detect_historical_case_similarity` | Same merchant + pattern in history | +0.15 |
| `detect_linked_fraud_network` | Same phone/email across 3+ disputes | +0.20 |
| `detect_rapid_case_creation` | 3+ disputes in 30 days | +0.15 |

---

#### Bank-Verified Account Intelligence — 5 tools (all channels, within universal cap)

| Tool | DB Source | Score |
|---|---|---|
| `verify_account_takeover_sequence` | `account_events` — weighted ATO chain (SIM_SWAP=3.0, ACCOUNT_LOCKED=2.5, FRAUD_ALERT=2.5, MOBILE_CHANGED=2.0, ...) | +0.10–0.30 |
| `verify_device_intelligence` | `customer_devices` — device trust, age, large transfer | +0.15–0.40 |
| `verify_mobile_change` | `account_events.MOBILE_NUMBER_CHANGED` within 7 days | +0.35 |
| `verify_new_beneficiary_activity` | `beneficiaries` table — known vs unknown payee | +0.10 |
| `validate_customer_security_claims` | Cross-ref form claims vs `account_events` | narrative only |

---

#### Fraud Probability Formula

```
fraud_probability = clamp(channel_signals + min(0.60, universal_signals), 0.00, 1.00)

Channel signals (examples):
  Unauthorized Transaction base         +0.15
  Amount anomaly 2×–5×                  +0.15
  Amount anomaly > 5×                   +0.25
  Geovelocity CRITICAL (≥ 900 km/h)     +0.35
  Unrecognized device (digital only)    +0.30
  Card entry MANUAL_ENTRY               +0.30
  EMV fallback detected                 +0.25
  Merchant blacklisted                  +0.50
  Merchant CRITICAL risk                +0.30
  (+ all channel-specific tool scores above)

Universal signals (capped at 0.60):
  Bank-verified ATO sequence HIGH       +0.20
  Bank-verified ATO sequence CRITICAL   +0.30
  New device + large transfer (CRITICAL)+0.40
  Mule account indicators               +0.30
  (+ other universal tool scores above)

Risk Levels:  LOW < 0.15 · MEDIUM < 0.40 · HIGH < 0.75 · CRITICAL ≥ 0.75
```

---

### Agent 5 — EIA (Evidence Intelligence Agent)

Audits evidence completeness and consistency. **100% DB — reads from `dispute_cases` and `document_requests`.**

**Tools:**
- `evaluate_evidence_completeness` — required docs vs fulfilled requests + upload count
- `identify_missing_evidence` — unfulfilled customer document gaps
- `validate_evidence_consistency` — amount/merchant/date vs original `transactions` record
- `assess_evidence_strength` — weighted: ARIA verdict + completeness + IIA data quality
- `determine_next_document_request` — next formal document request (deduplicates pending)

**Outputs:** `evidence_completeness`, `evidence_strength`, `missing_documents`, `investigation_blocked`, `recommended_document_requests`

---

### Agent 6 — CCA (Customer Communication Agent)

Generates and delivers professional HTML email notifications. Fires asynchronously — never blocks the workflow.

**8 notification types:**

| Type | Trigger |
|---|---|
| `CASE_RECEIVED` | Case submitted (auto, once) |
| `INVESTIGATION_STARTED` | IIA completes (auto, once) |
| `DOCUMENT_REQUESTED` | Analyst creates document request |
| `CASE_RESOLVED` | Case resolved/closed/rejected |
| `CASE_REJECTED` | Case rejected |
| `CASE_REOPENED` | Case reopened |
| `STATUS_CHANGED` | Major status transition |
| `DOCUMENTS_RECEIVED` | Customer uploads documents |

Internal-only transitions (FRAUD_REVIEW_STARTED, EVIDENCE_REVIEW_COMPLETED) are suppressed from auto-sending.

**Delivery:** Outlook SMTP (`smtp.office365.com:587` TLS). Demo mode redirects all mail to `NOTIFICATION_EMAIL`.

---

## Database Tables

| Table | Records | Purpose |
|---|---|---|
| `dispute_cases` | 5 live | Active dispute cases with full agent output |
| `dispute_history` | 600+ | Pre-seeded historical resolved cases |
| `bank_customers` | 1,000 | Customer CIF records |
| `transactions` | 11,000+ | Full transaction history with GPS coords, device_id, card_entry_mode |
| `merchant_profiles` | ~500 | Bank merchant risk profiles |
| `account_events` | 5,705 | Bank security events (SIM_SWAP, DEVICE_REGISTERED, OTP_DELIVERED, etc.) |
| `customer_devices` | 7,494 | Registered customer devices with trust status |
| `beneficiaries` | 9,347 | Known payees per customer |
| `audit_logs` | grows | Immutable event log |
| `communication_logs` | grows | Sent email records |
| `document_requests` | grows | Analyst document requests |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI |
| Agent orchestration | LangGraph + LangChain |
| LLM engine | Groq — `llama-3.1-8b-instant` |
| Database | PostgreSQL, SQLAlchemy ORM (pool: 30 base / 60 overflow, timeout 60s) |
| Document extraction | PyMuPDF, pytesseract (OCR) |
| LLM resilience | Tenacity (exponential backoff, 3 retries) |
| Frontend | Next.js 14 App Router, React 18, TypeScript |
| Forms | React Hook Form + Zod |
| Real-time | WebSocket (live case status push) |
| Email | smtplib TLS (Outlook SMTP) |
| Priority engine | Deterministic post-workflow computation |

---

## Key Design Decisions

**DB-first fraud scoring, not form-first.**
ARIA's `score_fraud_indicators` queries `account_events` before trusting any customer form flag. Bank-verified events (SIM_SWAP_DETECTED, OTP_DELIVERED, CARD_LOST_REPORTED, etc.) carry full scoring weight. Unverifiable customer claims (otp_shared, bank_impersonation, remote_access) carry 60% weight and are narrative context only.

**Social engineering signals appear in narrative, not in score.**
`otp_shared`, `bank_impersonation`, `remote_access`, `screen_sharing`, `phishing_link` — these represent human interactions (phone calls, verbal OTP sharing) that no bank system can record. They inform the LLM's written explanation of the fraud but do not contribute to `fraud_probability`.

**FRIA is channel-aware — 48 tools, 4 channels.**
Card POS and ATM get different tool sets than UPI and Internet Banking. Device fingerprint and KYC match are disabled for Card POS/ATM at the DB level (`device_id = NULL`, `card_entry_mode` column only populated for card transactions). The Fraud Review tab adapts per channel — Identity Status shows for digital, Card Authentication shows for Card POS.

**LLM produces narrative — deterministic code produces numbers.**
`fraud_probability`, `confidence_score`, `trust_score`, and all risk levels are computed server-side. The LLM is given pre-computed tool results and asked to explain them. Post-processing corrects known LLM errors: strips score weights from findings, corrects merchant tier misattribution.

**GPS Haversine geovelocity — not string matching.**
Location velocity uses actual lat/lng coordinates from `transactions.latitude/longitude`. Haversine distance calculation gives speed in km/h. Thresholds: MEDIUM ≥ 150, HIGH ≥ 500, CRITICAL ≥ 900 km/h. Card POS/ATM have NULL coordinates (merchant location, not customer GPS).

**Universal tool contribution is capped at 0.60.**
Universal signals run on all channels. Without a cap, they could make channel-specific tools irrelevant. Channel tools always contribute meaningfully on top.

**WOA is the single routing authority. COMPLIANCE_AGENT removed.**
High-risk tags (VELOCITY_BREACH, OTP_COMPROMISED, DEVICE_MISMATCH) now trigger escalation to a senior analyst — not a separate compliance agent. WOA routes to three agents only: FRAUD_AGENT, EVIDENCE_AGENT, MERCHANT_AGENT.

**Behavioral patterns are deduplicated.**
Cases appearing in both `dispute_cases` (live) and `dispute_history` (resolved) are counted once using `case_id` deduplication before computing velocity.

**CCA is noise-controlled.**
One-shot types (CASE_RECEIVED, INVESTIGATION_STARTED, CASE_RESOLVED) fire at most once per case. STATUS_CHANGED fires only for major customer-visible transitions.

---

## Project Structure

```
ai-dispute-resolution-system/
├── backend/
│   ├── agents/
│   │   ├── dispute_agent/          # Agent 1 — ARIA (3 tools, DB-first scoring)
│   │   ├── investigation_agent/    # Agent 2 — IIA (4 tools, 100% DB)
│   │   ├── orchestration_agent/    # Agent 3 — WOA (6 tools, 3-agent routing)
│   │   ├── fraud_reasoning_agent/  # Agent 4 — FRIA (48 tools, channel-aware)
│   │   ├── evidence_agent/         # Agent 5 — EIA (5 tools, 100% DB)
│   │   └── communication_agent/    # Agent 6 — CCA (SMTP email)
│   ├── api/
│   │   ├── main.py                 # FastAPI entry point
│   │   └── routes/                 # disputes, ops_cases, ops_analytics,
│   │                               # queues, auth, communications, dispute_tracking
│   ├── database/
│   │   ├── database.py             # SQLAlchemy engine, session, auto-migrations
│   │   └── models.py               # ORM: 13 tables including account_events,
│   │                               # customer_devices, beneficiaries, transactions
│   ├── prompts/                    # LLM system prompts per agent
│   ├── schemas/                    # Pydantic request/response models
│   ├── services/                   # Priority, SLA, queue, document rules,
│   │                               # communication, email, analytics
│   ├── workflows/
│   │   └── dispute_workflow.py     # LangGraph compiled graph (recursion_limit=50)
│   └── utils/                      # Helpers, logger, PII masking, OCR extractor
└── frontend/
    └── src/
        ├── app/
        │   ├── submit-dispute/     # Customer dispute submission (multi-step form)
        │   ├── internal-review/    # Ops analyst queue + case workspace
        │   └── track/              # Customer tracking portal
        ├── components/             # Shared UI components
        ├── hooks/                  # WebSocket hook
        ├── lib/                    # API client, auth, utilities
        └── types/                  # TypeScript interfaces
```

---

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL
- Groq API key — [console.groq.com](https://console.groq.com)
- Tesseract OCR — [github.com/tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract)

### Backend

```bash
cd backend
python -m venv venv

# Windows
.\venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

Create `backend/.env`:
```env
GROQ_API_KEY=your_groq_api_key_here
DATABASE_URL=postgresql://user:password@localhost:5432/dispute_resolution
LLM_MODEL=llama-3.1-8b-instant
LLM_TEMPERATURE=0
LLM_MAX_TOKENS=1024
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe

# Email — Agent 6 CCA (Outlook)
SMTP_SERVER=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=your_email@outlook.com
SMTP_PASSWORD=your_password
NOTIFICATION_EMAIL=your_email@outlook.com

API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true
SECRET_KEY=change-this-in-production
```

Initialize the database and start the server:
```bash
# Create all tables + run auto-migrations
python -c "from database.database import init_db; init_db()"

# Start the server
uvicorn api.main:app --reload
```

API at `http://localhost:8000` · Swagger at `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend at `http://localhost:3000`

---

## Portals

| Portal | URL | Audience |
|---|---|---|
| Dispute Submission | `http://localhost:3000/submit-dispute` | Customer |
| Case Tracking | `http://localhost:3000/track/{case_id}` | Customer |
| Ops Queue | `http://localhost:3000/internal-review` | Analyst |
| Case Workspace | `http://localhost:3000/internal-review/{case_id}` | Analyst |
| API Docs | `http://localhost:8000/docs` | Developer |

---

## Ops Workspace Tabs

| Tab | Content |
|---|---|
| Case Analysis | Classification, confidence, risk tags, evidence match, key findings |
| Investigation | IIA plan, customer history, merchant intelligence, recommended steps |
| Fraud Review | Channel badge, fraud probability, trust score, card authentication (Card POS), identity status (digital), channel-specific fraud signals, bank-verified ATO events |
| Evidence Review | Completeness %, consistency check, missing docs |
| Case Coordination | WOA workflow path, agent progression, investigation rationale, SLA |
| Evidence | Uploaded files — images open in lightbox, PDFs open in new tab |
| Audit Trail | Full immutable event log |
| Communications | All customer emails with HTML iframe preview, auto-refreshes after status change |

**Fraud Review is channel-aware:**
- Card POS / ATM → shows Card Authentication Intelligence, hides Identity Verification and Account Security Intelligence (when ATO = LOW)
- UPI / Internet Banking → shows Identity Verification, Device Intelligence, Account Security Intelligence

---

## API Reference

```
POST   /api/disputes/submit-public                  Submit dispute with file uploads
GET    /api/disputes/cases                          List cases (filter: status/priority/category/fraud)
GET    /api/disputes/cases/{case_id}                Full case detail
PUT    /api/disputes/cases/{case_id}/status         Update case status
POST   /api/disputes/{case_id}/upload-documents     Customer uploads additional documents
GET    /api/disputes/track/{case_id}                Customer-safe tracking (no internal data)
GET    /api/disputes/stats                          Dashboard statistics
GET    /api/disputes/document-requirements          Required docs for dispute type

GET    /api/ops/cases/{case_id}/notes               Get analyst notes
POST   /api/ops/cases/{case_id}/notes               Add analyst note
GET    /api/ops/cases/{case_id}/document-requests   Get document requests
POST   /api/ops/cases/{case_id}/document-requests   Create document request
GET    /api/ops/cases/{case_id}/uploads             List uploaded evidence files
POST   /api/ops/cases/{case_id}/reanalyse           Re-run full agent pipeline

GET    /api/communications/{case_id}                All communications for a case
POST   /api/communications/{case_id}/send           Manually trigger a communication

GET    /api/ops/analytics                           Ops analytics and stats
WS     /ws/disputes                                 Real-time case status push
```

---

## Dispute Categories

| Category | Routing |
|---|---|
| Unauthorized Transaction | FRAUD_AGENT → EVIDENCE_AGENT |
| Friendly Fraud | FRAUD_AGENT → EVIDENCE_AGENT |
| Duplicate Transaction | EVIDENCE_AGENT |
| Refund Not Received | EVIDENCE_AGENT → MERCHANT_AGENT |
| Merchant Dispute | EVIDENCE_AGENT → MERCHANT_AGENT |
| ATM Cash Issue | EVIDENCE_AGENT |
| Subscription Abuse | FRAUD_AGENT → EVIDENCE_AGENT |
| Product Not Received | EVIDENCE_AGENT → MERCHANT_AGENT |
| Other | EVIDENCE_AGENT |

---

## RBI Liability Tiers

| Amount | Handling |
|---|---|
| ₹0 – ₹10,000 | Standard processing |
| ₹10,000 – ₹50,000 | Heightened scrutiny |
| ₹50,000 – ₹2,00,000 | Senior officer escalation |
| ₹2,00,000 – ₹10,00,000 | Mandatory investigation |
| > ₹10,00,000 | Executive-level review |
