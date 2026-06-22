# AI Dispute Resolution System

Enterprise-grade, multi-agent platform for banking transaction dispute resolution. Built for BFSI operations teams — automates dispute intake, fraud detection, evidence verification, investigation planning, and customer communication through a cooperative pipeline of 6 specialized AI agents.

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

    G -- "workflow_path includes\nFRAUD_AGENT" --> H["Agent 4 · FRIA\nFraud Reasoning Agent\n─────────────────────────\n6 tools in parallel"]
    G -- "workflow_path includes\nEVIDENCE_AGENT" --> I["Agent 5 · EIA\nEvidence Intelligence Agent\n─────────────────────────\n5 tools"]
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

**WOA is the single source of truth.** It decides which specialist agents run based on dispute category, fraud signals, and evidence gaps. Specialist agents only execute when WOA explicitly routes to them.

---

## Agents

### Agent 1 — ARIA (Dispute Understanding Agent)

Reads the dispute form, transaction metadata, and OCR-extracted document text. Produces the primary classification that all downstream agents build upon.

**Tools (pre-computed, deterministic):**
- `assess_transaction_context` — RBI liability tiers, off-hours risk, CNP channels
- `score_fraud_indicators` — OTP sharing, SIM swap, phishing, remote access, device loss
- `verify_evidence_match` — OCR document text vs claimed merchant and amount
- `compute_confidence_score` — calibrated confidence from all tool findings

**Outputs:** `dispute_category`, `fraud_suspicion`, `confidence_score`, `risk_tags`, `evidence_match`, `structured_reasoning`

---

### Agent 2 — IIA (Investigation Intelligence Agent)

Runs 4 database-backed tools against live customer, merchant, and case history before designing an investigation plan.

**Tools:**
- `lookup_customer_history` — dispute frequency, chargeback ratios, risk profile
- `check_merchant_risk` — category risk, complaint counts, blacklist status
- `find_duplicate_transaction` — identical merchant/amount/date within 72-hour window
- `lookup_related_cases` — outcomes of similar historical disputes

**Outputs:** `investigation_plan`, `required_documents`, `recommended_queue`, `investigation_complexity`, `recommended_steps`

---

### Agent 3 — WOA (Workflow Orchestration Agent)

Acts as the workflow controller. Runs after IIA, before any specialist agents. Its `workflow_path` is the authoritative execution plan — no other agent can modify it.

**Routing logic:**
- Adds `FRAUD_AGENT` if `fraud_suspicion = true` OR category is fraud-related
- Adds `EVIDENCE_AGENT` if document gaps exist
- Adds `MERCHANT_AGENT` if merchant dispute category
- Adds `COMPLIANCE_AGENT` for regulatory flags

**Tools (deterministic — LLM used for reasoning only):**
- `evaluate_case_complexity` — value tiers, risk tags, investigation complexity
- `determine_required_agents` — specialist routing decision
- `recommend_workflow_path` — ordered execution sequence
- `assess_escalation_need` — supervisor approval triggers
- `estimate_workload` — analyst seniority level and hours estimate
- `determine_next_execution_step` — tracks completed vs remaining agents

**Outputs:** `workflow_path`, `required_agents`, `next_agent`, `workflow_complexity`, `escalation_required`, `analyst_level`, `sla_hours`

---

### Agent 4 — FRIA (Fraud Reasoning Agent)

Only runs when WOA includes `FRAUD_AGENT` in the workflow path. Runs 6 tools in parallel via `ThreadPoolExecutor`. All numeric scores are server-side deterministic — the LLM synthesises narrative only.

**Tools (parallel execution):**
- `detect_transaction_anomalies` — off-hours flag, rapid-fire velocity (< 15 seconds between transactions)
- `evaluate_location_velocity` — geovelocity breach with city-level normalization (Mumbai vs Mumbai MH treated as same city)
- `analyze_spending_behavior` — Z-score deviation from customer's spending baseline
- `verify_kyc_match` — CIF record comparison; flags Compromise Risk HIGH for Unauthorized Transaction disputes where all fields match (fraudster may have device access)
- `evaluate_device_fingerprint` — device ID familiarity, location consistency
- `analyze_behavioral_patterns` — friendly fraud indicator from dispute history

**Fraud Probability (server-side deterministic):**
```
Unauthorized Transaction base             +0.15
Amount anomaly (2×–5× average)           +0.15
Amount anomaly (> 5× average)            +0.25
Time anomaly (off-hours 11 PM – 5 AM)   +0.15
Rapid-fire velocity breach (< 15s)       +0.30
Geovelocity breach (impossible travel)   +0.35
Unrecognized device                      +0.30
Location mismatch                        +0.20
KYC Compromise Risk HIGH                 +0.20
High behavioral risk score (≥ 0.60)      +0.15
```

**Fraud Risk Levels:** LOW < 0.15 · MEDIUM < 0.40 · HIGH < 0.75 · CRITICAL ≥ 0.75

**Outputs:** `fraud_probability`, `fraud_risk_level`, `user_trust_score`, `behavioral_risk_score`, `identity_verification`

---

### Agent 5 — EIA (Evidence Intelligence Agent)

Audits evidence completeness and transaction consistency. Separates customer-obtainable documents from bank-obtainable documents — only customer gaps affect completeness score and `investigation_blocked`.

**Tools:**
- `evaluate_evidence_completeness` — required docs vs fulfilled requests + upload credits
- `identify_missing_evidence` — unfulfilled customer document gaps
- `validate_evidence_consistency` — amount/merchant/date vs original transaction record
- `assess_evidence_strength` — weighted score: Agent 1 verdict + completeness + Agent 2 data quality
- `determine_next_document_request` — next document to formally request (deduplicates pending requests)

**Outputs:** `evidence_completeness`, `evidence_strength`, `missing_documents`, `bank_pending_documents`, `investigation_blocked`, `recommended_document_requests`

---

### Agent 6 — CCA (Customer Communication Agent)

Generates professional HTML email notifications for dispute lifecycle events. Fires asynchronously — never blocks the main workflow. All internal AI metrics, agent names, fraud scores, and risk signals are stripped before sending.

**Email triggers:**
| Event | Notification Type |
|---|---|
| Dispute submitted | CASE_RECEIVED |
| Case moves to Under Investigation | INVESTIGATION_STARTED |
| Analyst creates document request | DOCUMENT_REQUESTED |
| FRIA completes fraud review | FRAUD_REVIEW_STARTED |
| EIA completes evidence review | EVIDENCE_REVIEW_COMPLETED |
| Case resolved / rejected / closed | CASE_RESOLVED |
| Any other status change | STATUS_CHANGED |

**CASE_RECEIVED and CASE_RESOLVED** are one-shot — fire at most once per case automatically. Manual resend always available from the Communications tab.

**Delivery:** Outlook SMTP (`smtp.office365.com:587` TLS) or Gmail (`smtp.gmail.com:587`). All emails in demo mode redirect to `NOTIFICATION_EMAIL`.

**Outputs:** `subject`, `body` (HTML), `recipient`, `status` (SENT/FAILED), `sent_at` — all persisted to `communication_logs`.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI |
| Agent orchestration | LangGraph + LangChain |
| LLM engine | Groq — `llama-3.1-8b-instant` |
| Database | PostgreSQL, SQLAlchemy ORM |
| Document extraction | PyMuPDF, pytesseract (OCR) |
| LLM resilience | Tenacity (exponential backoff, 3 retries) |
| Frontend | Next.js 14 App Router, React 18, TypeScript |
| Forms | React Hook Form + Zod |
| Real-time | WebSocket (live case status push) |
| Email | smtplib TLS (Outlook / Gmail) |
| Priority engine | Deterministic post-workflow computation |

---

## Key Design Decisions

**WOA is the single source of truth.**
No specialist agent can change the workflow path. When WOA excludes `FRAUD_AGENT`, the Fraud Review tab is hidden in the UI. When it re-includes it, all fraud scores are recomputed from scratch.

**LLM produces narrative — deterministic code produces numbers.**
Confidence scores, fraud probability, evidence completeness, priority, and SLA deadlines are all computed server-side. The LLM is trusted for classification and reasoning text only.

**KYC match is context-aware.**
A full name/email/phone match in an Unauthorized Transaction dispute raises `Compromise Risk: HIGH` — the fraudster has device access and can trivially supply all three fields. A full match is not treated as VERIFIED in that context.

**Velocity breach uses time gaps, not daily counts.**
Two transactions less than 15 seconds apart = velocity breach. Three transactions in a day = normal card usage. The old 3-per-day threshold generated false positives for legitimate users.

**Location normalization prevents geovelocity false positives.**
"Mumbai" and "Mumbai, MH" are treated as the same city. "Andheri, Mumbai" resolves to Mumbai. Transactions with unknown/missing location are skipped rather than flagged.

**Priority is computed post-workflow, never by the LLM.**
`priority_engine.py` runs after all agents complete and derives `CRITICAL / HIGH / MEDIUM / LOW` from a weighted formula across amount, fraud signals, complexity, and SLA state.

**PII is masked before it reaches the LLM.**
Customer names, IDs, and free-text comments are masked via `utils/pii_masking.py` before inclusion in any prompt.

**CCA never exposes internal details.**
Email bodies are built from fixed HTML templates — no LLM generation of email content. Agent names, fraud probability, trust scores, workflow paths, and queue assignments never appear in customer-facing output.

---

## Project Structure

```
ai-dispute-resolution-system/
├── backend/
│   ├── agents/
│   │   ├── dispute_agent/          # Agent 1 — ARIA
│   │   ├── investigation_agent/    # Agent 2 — IIA
│   │   ├── orchestration_agent/    # Agent 3 — WOA
│   │   ├── fraud_reasoning_agent/  # Agent 4 — FRIA
│   │   ├── evidence_agent/         # Agent 5 — EIA
│   │   └── communication_agent/    # Agent 6 — CCA
│   ├── api/
│   │   ├── main.py                 # FastAPI entry point + router registration
│   │   └── routes/                 # disputes, ops_cases, ops_analytics,
│   │                               # queues, auth, communications, dispute_tracking
│   ├── database/
│   │   ├── database.py             # SQLAlchemy engine, session, migrations
│   │   └── models.py               # ORM models (DisputeCase, CommunicationLog, etc.)
│   ├── prompts/                    # System prompts per agent
│   ├── schemas/                    # Pydantic request/response models
│   ├── services/                   # Priority, SLA, queue, document rules,
│   │                               # communication, email, analytics
│   ├── workflows/
│   │   └── dispute_workflow.py     # LangGraph compiled graph
│   └── utils/                      # Helpers, logger, PII masking, OCR extractor
└── frontend/
    └── src/
        ├── app/
        │   ├── submit-dispute/     # Customer dispute submission portal
        │   ├── internal-review/    # Ops analyst case queue + workspace
        │   └── track/              # Customer case tracking portal
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

# Email (CCA — Agent 6)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
NOTIFICATION_EMAIL=your_email@gmail.com

API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true
SECRET_KEY=change-this-in-production
```

Initialize the database and start the server:
```bash
# Create all tables (auto-migration included)
python -c "from database.database import init_db; init_db()"

# Start the server
uvicorn api.main:app --reload
```

API available at `http://localhost:8000` · Swagger docs at `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend available at `http://localhost:3000`

---

## Portals

| Portal | URL | Audience |
|---|---|---|
| Dispute Submission | `http://localhost:3000/submit-dispute` | Customer |
| Case Tracking | `http://localhost:3000/track` | Customer |
| Case Status | `http://localhost:3000/track/{case_id}` | Customer |
| Ops Queue | `http://localhost:3000/internal-review` | Analyst |
| Case Workspace | `http://localhost:3000/internal-review/{case_id}` | Analyst |
| API Docs | `http://localhost:8000/docs` | Developer |

---

## Ops Workspace Tabs

| Tab | Visible when | Content |
|---|---|---|
| Case Analysis | Always | Dispute classification, confidence, risk tags, evidence match |
| Investigation | Always | Agent 2 plan, required documents, complexity score |
| Fraud Review | WOA included FRAUD_AGENT | Fraud probability, trust score, identity verification, behavioral risk |
| Evidence Review | Always | Completeness %, consistency check, missing docs, document provenance |
| Case Coordination | Always | WOA workflow path, agent progression, SLA tracker |
| Evidence | Always | Uploaded files with preview |
| Audit Trail | Always | Full immutable event log |
| Communications | Always | All customer email notifications with full HTML preview |
| Advanced Diagnostics | Always (collapsed) | LangGraph execution trace, tool timings |

---

## Customer Tracking Portal

The `/track/{case_id}` portal is publicly accessible and shows only customer-safe information:

- **Progress bar** — 4 stages: Received → Investigation → Review → Resolution
- **Next Action Required** — pending document list with upload deadline
- **Document upload** — customer can submit files directly; marks document requests as fulfilled
- **Case timeline** — customer-visible audit events (duplicates removed)
- **Dispute details** — merchant, amount, transaction type, submission date

**Hidden from customers:** agent names, fraud probability, trust scores, internal queues, analyst assignments, workflow paths, risk tags.

Missing documents are sourced from `evidence_assessment.missing_documents` (set by EIA) — customers see the full required list automatically without analysts needing to create individual requests.

---

## API Reference

```
POST   /api/disputes/submit-public                 Submit a new dispute (with file uploads)
GET    /api/disputes/cases                         List all cases (filterable by status/priority/category)
GET    /api/disputes/cases/{case_id}               Get full case detail
PUT    /api/disputes/cases/{case_id}/status        Update case status
POST   /api/disputes/{case_id}/upload-documents    Customer uploads additional documents
GET    /api/disputes/track/{case_id}               Customer-safe case tracking (no internal data)
GET    /api/disputes/stats                         Dashboard statistics
GET    /api/disputes/document-requirements         Required docs for a dispute type
GET    /api/ops/cases/{case_id}/notes              Get case notes
POST   /api/ops/cases/{case_id}/notes              Add analyst note
GET    /api/ops/cases/{case_id}/document-requests  Get document requests
POST   /api/ops/cases/{case_id}/document-requests  Create document request (triggers email)
GET    /api/ops/cases/{case_id}/uploads            List uploaded files
POST   /api/ops/cases/{case_id}/reanalyse          Re-run full agent pipeline
GET    /api/communications/{case_id}               Get all communications for a case
POST   /api/communications/{case_id}/send          Manually trigger a communication
GET    /api/ops/analytics                          Ops analytics and stats
WS     /ws/disputes                                Real-time case status push
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
