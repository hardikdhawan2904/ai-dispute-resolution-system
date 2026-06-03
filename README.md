# Intelligent Transaction Dispute Resolution Platform

An AI-assisted BFSI dispute platform for intake, dispute understanding, investigation planning, operational routing, and customer/internal case tracking.

The long-term product vision is a multi-agent dispute intelligence system spanning intake, verification, merchant intelligence, evidence collection, compliance, synthesis, decisioning, and learning loops. The current implementation focuses on the first working slice of that architecture: a production-shaped 2-agent workflow backed by FastAPI, LangGraph, Groq, SQLAlchemy, and a Next.js frontend.

## Current Scope

Implemented today:

- Public dispute submission with file upload and OCR/text extraction
- Agent 1: dispute understanding and classification
- Rule-based post-processing for tags, priority, queue, SLA, and manual-review flags
- Agent 2: investigation planning using database-backed historical lookups
- Persistence of case records, audit logs, and workflow snapshots
- Internal operations dashboards and customer-safe tracking views

Planned / represented in the broader workflow vision, but not yet implemented as dedicated agents:

- Separate user verification / trust analysis agent
- Merchant intelligence agent as a standalone layer
- Dedicated evidence intelligence agent
- Dedicated compliance / policy agent
- Fusion/orchestrator agent
- Final chargeback decision agent
- Learning and adaptation agent

## End-to-End Workflow

The system currently works in this order:

1. A customer or ops user submits a dispute from the frontend.
2. The backend validates the form, generates a case ID, and extracts text from uploaded documents.
3. Agent 1 analyzes the submission and classifies the dispute.
4. The workflow applies deterministic enrichment rules on top of Agent 1 output.
5. Agent 2 reads Agent 1 output and gathers historical intelligence from the database.
6. The backend computes operational fields such as priority, queue, SLA deadline, and manual-review flags.
7. The final case, investigation plan, workflow trace, and audit logs are saved in the database.
8. Customer tracking pages and internal dashboards read from the stored case data.

## Current Agent Architecture

### Agent 1: Dispute Understanding Agent

Purpose:

- Understand what the customer is claiming
- Classify the dispute into a canonical category
- Detect fraud suspicion
- Evaluate evidence relevance
- Produce confidence, risk tags, and structured reasoning

Inputs:

- Customer details
- Transaction details
- Dispute reason
- Customer free-text complaint
- Fraud/supporting metadata
- OCR or extracted text from uploaded documents

Outputs:

- `dispute_category`
- `fraud_suspicion`
- `customer_intent_summary`
- `confidence_score`
- `confidence_factors`
- `risk_tags`
- `structured_reasoning`
- `evidence_match`
- `evidence_match_note`

Important implementation note:

- The graph still has LangGraph agent/tool-loop structure, but the current runtime pre-computes tool outputs server-side and uses the LLM mainly for synthesis into final JSON.

### Agent 2: Investigation Intelligence Agent

Purpose:

- Build the investigation plan after classification is complete
- Gather historical customer, merchant, and dispute intelligence
- Recommend the right queue, next steps, and required documents

Inputs:

- Structured output from Agent 1

Database-backed lookups:

- Customer dispute history
- Merchant complaint history
- Duplicate dispute checks
- Related case resolution trends
- Required documents by dispute type

Outputs:

- `recommended_queue`
- `queue_confidence`
- `investigation_complexity`
- `manual_review_required`
- `customer_risk_profile`
- `merchant_risk_profile`
- `duplicate_found`
- `related_cases`
- `required_documents`
- `recommended_steps`
- `investigation_summary`

Important implementation note:

- Agent 2 currently pre-runs its investigation tools in parallel before the final LLM synthesis step.

## Data Flow

At a high level, data moves like this:

`Frontend form -> FastAPI route -> DisputeService -> LangGraph workflow -> Agent 1 -> workflow enrichment -> Agent 2 -> service-level operational rules -> database -> internal/customer views`

### Frontend to Backend

The public dispute submission flow sends:

- Customer information
- Transaction information
- Dispute reason and complaint text
- Fraud-supporting metadata
- Uploaded evidence files

Evidence files are saved and processed before the AI analysis step so the extracted text can be included in the same workflow run.

### Backend to Agent 1

Agent 1 receives:

- `dispute_input`
- `document_texts`

It returns the first structured AI analysis of the case.

### Agent 1 to Agent 2

Agent 2 does not start from raw frontend data. It starts from the structured output of Agent 1 and treats that as the authoritative understanding of the case.

### Database Interaction

The database plays two roles:

- Historical memory for Agent 2 investigation lookups
- Final storage for processed dispute cases

The system persists:

- The final dispute case record
- Agent outputs and metadata
- Investigation plan
- Audit logs
- Workflow state snapshots

## Main Platform Layers

### Frontend

- Next.js 14 application
- Public dispute submission flow
- Customer dashboard and dispute tracking
- Internal operations dashboards

### Backend API

- FastAPI service
- Public and authenticated routes
- WebSocket updates for internal review dashboards
- Customer-safe tracking endpoints

### Workflow Layer

- LangGraph workflow for intake, validation, dispute understanding, reasoning, investigation, and structured output

### Persistence Layer

- SQLAlchemy ORM
- SQLite by default for local development
- PostgreSQL-compatible configuration for production migration

## Tech Stack

### Backend

- FastAPI
- LangGraph
- LangChain
- Groq
- SQLAlchemy
- Pydantic
- Tenacity
- pdfplumber / PyMuPDF / pytesseract / Pillow / openpyxl

### Frontend

- Next.js 14
- React 18
- TypeScript
- Tailwind CSS
- React Hook Form
- Zod

## Project Structure

Top-level modules:

- `backend/` - API, agents, workflow, services, database, prompts, utils
- `frontend/` - Next.js app for customer and ops interfaces
- `samples/` - sample assets and data used during development

Within the backend:

- `agents/` - current AI agents
- `workflows/` - LangGraph orchestration
- `services/` - deterministic business logic and persistence orchestration
- `database/` - engine and ORM models
- `api/` - route layer
- `schemas/` - request/response models
- `utils/` - helpers, logging, extraction

## Local Development

### Backend

From `backend/`:

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload
```

Backend default URL:

- `http://localhost:8000`

### Frontend

From `frontend/`:

```bash
npm install
npm run dev
```

Frontend default URL:

- `http://localhost:3000`

Useful routes:

- Public submit flow: `/submit-dispute`
- Customer dashboard: `/customer/dashboard`
- Ops dashboard: `/ops/dashboard`
- Internal review board: `/internal-review`

## Environment Notes

The backend expects environment configuration for items such as:

- `DATABASE_URL`
- `GROQ_API_KEY`
- optional LLM overrides like `LLM_MODEL`
- OCR/Tesseract path if needed on Windows

The frontend typically uses:

- `NEXT_PUBLIC_API_URL`

## What This README Reflects

This README documents the current implemented system, not only the target architecture shown in the workflow diagram.

That means:

- The platform vision is broader than the current codebase
- Only 2 agents are active today
- Several boxes in the full workflow are currently represented by deterministic services rather than separate agents
- The existing system is already end-to-end functional for dispute intake, classification, investigation planning, persistence, and review
