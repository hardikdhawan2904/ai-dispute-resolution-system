# BFSI Dispute Resolution System - Agent Documentation Index

**Last Updated**: 2026-06-14  
**System Version**: 1.0

---

## 📚 Quick Navigation

### Main Documentation Files

| Document | Purpose | Location |
|----------|---------|----------|
| **Comprehensive Guide** | Full system architecture, all agents, workflows, error handling | [AGENTS_COMPREHENSIVE_GUIDE.md](AGENTS_COMPREHENSIVE_GUIDE.md) |
| **Agent 1: ARIA** | Dispute Understanding Agent — intake & classification | [agents/dispute_agent/README.md](agents/dispute_agent/README.md) |
| **Agent 2: IIA** | Investigation Intelligence Agent — historical analysis | [agents/investigation_agent/README.md](agents/investigation_agent/README.md) |
| **Agent 3: FRA** | Fraud Reasoning Agent — pattern analysis | [agents/fraud_reasoning_agent/README.md](agents/fraud_reasoning_agent/README.md) |
| **Agent 4: EIA** | Evidence Intelligence Agent — document verification | [agents/evidence_agent/README.md](agents/evidence_agent/README.md) |
| **Agent 5: WOA** | Orchestration Workflow Agent — case routing | [agents/orchestration_agent/README.md](agents/orchestration_agent/README.md) |

---

## 🎯 Agent Overview

### Agent 1: ARIA - Dispute Understanding Agent
**Role**: First contact point — dispute classification & fraud risk scoring  
**Input**: Raw dispute form submission  
**Output**: fraud_suspicion, priority, confidence_score, risk_tags  
**Tools**: 
- `assess_transaction_context()` — RBI/NPCI risk baseline
- `score_fraud_indicators()` — Fraud probability calculation
**Key Metrics**: 
- Amount tier (RBI Liability Tiers)
- Off-hours detection (11 PM–5 AM)
- Fraud score (0-10+)
- Confidence score (0-1)

**Quick Start**: [Read ARIA README](agents/dispute_agent/README.md)

---

### Agent 2: IIA - Investigation Intelligence Agent
**Role**: Historical analysis & risk profiling  
**Input**: Agent 1 output (fraud_suspicion, dispute category)  
**Output**: investigation_plan, complexity, confidence  
**Data**: 526+ historical disputes + 11,000+ transactions  
**Tools**: 
- `lookup_customer_history()` — Customer risk profile
- `check_merchant_risk()` — Merchant reputation
- `detect_velocity_patterns()` — Transaction frequency anomalies
- `analyze_transaction_anomalies()` — Spending & off-hours patterns
- `cross_reference_dispute_history()` — Similar case guidance
**Key Metrics**: 
- Customer fraud rate (%)
- Merchant complaint count
- Velocity breach status
- Investigation complexity (LOW/MEDIUM/HIGH)

**Quick Start**: [Read IIA README](agents/investigation_agent/README.md)

---

### Agent 3: FRA - Fraud Reasoning Agent
**Role**: Fraud pattern analysis & anomaly detection  
**Input**: Agent 1, 2 output  
**Output**: fraud_probability, fraud_risk_level, reasoning_brief  
**Tools** (pre-executed):
- `detect_transaction_anomalies()` — Off-hours, velocity
- `evaluate_location_velocity()` — Geovelocity breaches
- `analyze_spending_behavior()` — Z-score analysis
**Key Metrics**: 
- Fraud probability (0-1 scale)
- Risk level (LOW/MEDIUM/HIGH/CRITICAL)
- Anomaly flags
- Z-score computation

**Quick Start**: [Read FRA README](agents/fraud_reasoning_agent/README.md)

---

### Agent 4: EIA - Evidence Intelligence Agent
**Role**: Evidence verification & document requirement tracking  
**Input**: Agents 1, 2, 3 + uploaded documents  
**Output**: evidence_strength, completeness_score, missing_docs  
**Tools**: 
- `evaluate_evidence_completeness()` — Document scorecard
- `identify_missing_evidence()` — Gap analysis
- `validate_evidence_consistency()` — Cross-check details
- `assess_document_authenticity()` — Fraud detection
- `determine_evidence_strength()` — Final assessment
**Key Metrics**: 
- Completeness % (0-100)
- Consistency score (0-100)
- Authenticity flag (HIGH/MEDIUM/LOW)
- Evidence strength (HIGH/MEDIUM/LOW)

**Quick Start**: [Read EIA README](agents/evidence_agent/README.md)

---

### Agent 5: WOA - Orchestration Workflow Agent
**Role**: Case routing & workflow coordination  
**Input**: All prior agents' outputs  
**Output**: workflow_plan, assigned_queue, assigned_analyst, SLA  
**Tools** (deterministic):
- `evaluate_case_complexity()` — Complexity tier
- `determine_required_agents()` — Specialist routing
- `recommend_workflow_path()` — Execution sequence
- `assess_escalation_need()` — Management escalation
- `estimate_workload()` — Analyst capacity
- `determine_next_execution_step()` — Dependency tracking
**Key Metrics**: 
- Complexity (LOW/MEDIUM/HIGH/CRITICAL)
- Required agents list
- SLA deadline
- Analyst level needed
- Estimated hours

**Quick Start**: [Read WOA README](agents/orchestration_agent/README.md)

---

## 📊 Data Flow Architecture

```
CUSTOMER DISPUTE SUBMISSION
         │
         ▼
    ┌─────────────────────┐
    │  Agent 1: ARIA      │ Classification
    │  fraud_suspicion    │ Risk Scoring
    │  priority, tags     │ Confidence
    └─────────┬───────────┘
              │
              ▼
    ┌─────────────────────┐
    │  Agent 2: IIA       │ History Analysis
    │  investigation_plan │ Risk Profiling
    └─────────┬───────────┘
              │
              ▼
    ┌─────────────────────┐
    │  Agent 5: WOA       │ Case Orchestration
    │  workflow_plan      │ Routing Decisions
    └─────────┬───────────┘
              │
        ┌─────┴─────┐
        ▼           ▼
    ┌────────┐  ┌──────────┐
    │Agent 3 │  │ Agent 4  │
    │  FRA   │  │   EIA    │
    │ Fraud  │  │Evidence  │
    └────┬───┘  └────┬─────┘
         │           │
         └─────┬─────┘
               ▼
      INVESTIGATION QUEUE
     (Fraud/Merchant/Compliance)
```

---

## 🔍 Key Concepts

### RBI Liability Tiers (Agent 1)
- **₹0–10K**: Standard processing
- **₹10K–50K**: Heightened scrutiny
- **₹50K–200K**: Immediate escalation to senior officer
- **₹200K–1M**: Mandatory investigation
- **>₹1M**: Executive-level review

### Fraud Scoring (Agents 1, 3)
**Tier-1 Indicators** (each = +8.0):
- OTP shared with third party
- Bank impersonation (vishing)
- SIM swap suspected

**Tier-2 Indicators** (each = +4.0):
- Remote access tool installed
- Phishing link clicked

**Tier-3 Indicators** (each = +2.5):
- Card lost/stolen
- Device lost/stolen

**Thresholds**:
- ≥8.0 → CRITICAL
- 5–8 → HIGH
- 2–5 → MEDIUM
- <2 → LOW

### Investigation Complexity (Agent 2)
- **LOW**: Simple refund claims, first-time customers
- **MEDIUM**: Moderate fraud signals, some history
- **HIGH**: High-value disputes, multiple signals
- **CRITICAL**: Very high value, identity theft patterns

### Evidence Completeness (Agent 4)
- **>80%**: HIGH (proceeding with confidence)
- **50–80%**: MEDIUM (may request additional docs)
- **<50%**: LOW (blocks investigation until complete)

### Case Complexity (Agent 5)
- **LOW**: Amount <₹10K, no fraud, single category
- **MEDIUM**: Amount ₹10K–₹200K, moderate signals
- **HIGH**: Amount >₹200K OR multiple risk tags
- **CRITICAL**: Amount >₹1M OR identity theft indicators

---

## ⚙️ Configuration Files

### Agent Configuration (agent.yaml)
Each agent has its own `agent.yaml` containing:
```yaml
agent:
  name: Agent Full Name
  version: "X.0"
  llm:
    model: claude-3-5-sonnet-20241022
    temperature: 0.3
    max_tokens: 2048
  langgraph:
    pipeline:
      entry_point: "agent"
      agent_tools: [list of tools]
```

**Locations**:
- Agent 1: [agents/dispute_agent/agent.yaml](agents/dispute_agent/agent.yaml)
- Agent 2: [agents/investigation_agent/agent.yaml](agents/investigation_agent/agent.yaml)
- Agent 3: [agents/fraud_reasoning_agent/agent.yaml](agents/fraud_reasoning_agent/agent.yaml)
- Agent 4: [agents/evidence_agent/agent.yaml](agents/evidence_agent/agent.yaml)
- Agent 5: [agents/orchestration_agent/agent.yaml](agents/orchestration_agent/agent.yaml)

---

## 📈 Metrics & Observability

### Key Metrics Tracked
```json
{
  "agent_name": "Agent 1: ARIA",
  "execution_metrics": {
    "duration_ms": 2847,
    "llm_calls": 1,
    "tool_calls": 2,
    "retry_count": 0,
    "timestamp": "2026-06-14T11:46:29Z"
  },
  "output_metrics": {
    "fraud_probability": 0.92,
    "confidence_score": 0.92,
    "priority": "CRITICAL",
    "tools_used": ["assess_transaction_context", "score_fraud_indicators"]
  }
}
```

### Monitoring Dashboard Queries
```
Total cases processed:           SELECT COUNT(*) FROM dispute_cases
Average processing time:         SELECT AVG(updated_at - created_at)
Fraud detection rate:            SELECT COUNT(*) WHERE fraud_suspicion=true
High-priority cases:             SELECT COUNT(*) WHERE priority='CRITICAL'
Average confidence score:        SELECT AVG(confidence_score)
Tool execution times:            SELECT tool_name, AVG(duration_ms)
Agent failure rate:              SELECT COUNT(*) WHERE error IS NOT NULL
```

---

## 🚨 Error Handling

### Common Scenarios

| Scenario | Handler | Fallback |
|----------|---------|----------|
| Database connection fails | Retry 3x with backoff | Set fallback_mode=true, requires_manual_review=true |
| LLM timeout | Return after 30s | Use deterministic heuristics from tool results |
| Missing required field | Validate input first | Return 400 error before agent execution |
| Document upload fails | Log error, continue | Flag in document_requests as pending |
| Tool execution error | Catch exception | Return conservative estimate, log warning |

---

## 📖 Usage Examples

### Example 1: Unauthorized UPI Transaction
```
Input:
  customer_comment: "I didn't do this transaction"
  otp_shared: true
  fraud_selected: true
  amount: ₹50,000
  time: 23:30 (off-hours)

Agent 1 Output:
  fraud_suspicion: true
  priority: CRITICAL
  confidence_score: 0.92
  
Agent 2 Output:
  investigation_complexity: HIGH
  required_documents: [UPI_LOG, OTP_RECORDS, DEVICE_HISTORY]
  
Agent 3 Output:
  fraud_probability: 0.85
  fraud_risk_level: CRITICAL
  
Agent 4 Output:
  evidence_strength: HIGH
  completeness: 90%
  
Agent 5 Output:
  workflow_plan: [FRAUD_AGENT, EVIDENCE_AGENT]
  assigned_queue: FRAUD_INVESTIGATION_HIGH_PRIORITY
  analyst_level: SENIOR
  sla_hours: 8
```

### Example 2: Refund Not Received
```
Input:
  customer_comment: "I paid for the product but didn't receive it"
  fraud_selected: false
  amount: ₹5,000
  merchant: Amazon

Agent 1 Output:
  dispute_category: "Refund Not Received"
  fraud_suspicion: false
  priority: MEDIUM
  confidence_score: 0.55
  
Agent 2 Output:
  investigation_complexity: LOW
  required_documents: [PURCHASE_PROOF, PAYMENT_RECEIPT]
  customer_risk_level: LOW
  merchant_risk_level: LOW
  
Agent 5 Output:
  workflow_plan: [MERCHANT_AGENT]
  assigned_queue: MERCHANT_DISPUTE_STANDARD
  analyst_level: JUNIOR
  sla_hours: 24
```

---

## 🔗 Related Documents

- [Database Schema](database/README.md)
- [API Documentation](api/README.md)
- [Frontend Guide](../frontend/README.md)
- [Deployment Guide](../README.md)

---

## 📞 Support

For questions about specific agents or the system architecture:

1. **Agent-specific issues**: Check the agent's individual README
2. **System architecture**: See [AGENTS_COMPREHENSIVE_GUIDE.md](AGENTS_COMPREHENSIVE_GUIDE.md)
3. **Data dependencies**: Review the Data Flow section above
4. **Configuration**: Check agent.yaml files
5. **Error investigation**: Search `logs/` directory for agent_name

