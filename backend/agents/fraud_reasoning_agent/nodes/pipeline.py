"""
Fraud Reasoning Agent — Graph pipeline nodes.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from groq import RateLimitError as GroqRateLimitError
from langchain_groq import ChatGroq
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from agents.fraud_reasoning_agent.config import get_llm_config, get_agent_tool_names, load_agent_config
from agents.fraud_reasoning_agent.state import FraudReasoningAgentState
from agents.fraud_reasoning_agent.tools import TOOL_REGISTRY, _active_case_id
from prompts.fraud_prompts import SYSTEM_PROMPT, FRAUD_DATA_TEMPLATE
from utils.helpers import extract_json_from_text, utc_now_iso, generate_case_id
from utils.logger import agent_logger, log_workflow_event
from utils.pii_masking import mask_name, mask_id

# ── LLM + tools + agent identity ─────────────────────────────────────────────
_cfg        = get_llm_config()
_agent_yaml = load_agent_config()["agent"]
_AGENT_NAME = _agent_yaml["name"]
_AGENT_VER  = str(_agent_yaml["version"])
_tools = [TOOL_REGISTRY[name] for name in get_agent_tool_names()]

_llm = ChatGroq(
    model_name=os.environ.get("LLM_MODEL") or _cfg["model"],
    temperature=_cfg["temperature"],
    max_tokens=int(os.environ.get("LLM_MAX_TOKENS") or _cfg["max_tokens"]),
    api_key=os.environ.get("GROQ_API_KEY"),
)


# ── Node 1 — validate ─────────────────────────────────────────────────────────

def validate_node(state: FraudReasoningAgentState) -> dict:
    d = state["dispute_input"]
    case_id = d.get("case_id") or d.get("_preset_case_id") or generate_case_id()
    return {"case_id": case_id, "agent_start_time": time.time()}


# ── Node 2 — build_context ────────────────────────────────────────────────────

def build_context_node(state: FraudReasoningAgentState) -> dict:
    """Run transaction anomalies, geovelocity, spend deviations, KYC matches,
    device fingerprints, and behavioral dispute tools in parallel."""
    d = state["dispute_input"]
    case_id = state["case_id"]
    meta = d.get("transaction_metadata") or {}

    customer_id = d.get("customer_id", "")
    customer_name = d.get("customer_name", "")
    email = d.get("email", "")
    phone = d.get("phone", "")
    transaction_id = d.get("transaction_id", "")
    transaction_type = d.get("transaction_type", "")
    merchant = d.get("merchant", "")
    amount = float(d.get("amount", 0.0))
    currency = d.get("currency", "INR")
    transaction_date = d.get("transaction_date", "")
    transaction_time = d.get("transaction_time", "")
    location = meta.get("transaction_location") or d.get("location") or ""
    device_id = meta.get("device_id") or d.get("device_id") or ""
    dispute_reason = d.get("dispute_reason", "")

    # Pre-run tools concurrently in parallel threads
    task_defs = {
        "detect_transaction_anomalies": (
            TOOL_REGISTRY["detect_transaction_anomalies"],
            {
                "customer_id": customer_id,
                "transaction_time": transaction_time,
                "transaction_date": transaction_date
            }
        ),
        "evaluate_location_velocity": (
            TOOL_REGISTRY["evaluate_location_velocity"],
            {
                "customer_id": customer_id,
                "location": location,
                "transaction_date": transaction_date,
                "transaction_time": transaction_time
            }
        ),
        "analyze_spending_behavior": (
            TOOL_REGISTRY["analyze_spending_behavior"],
            {
                "customer_id": customer_id,
                "amount": amount
            }
        ),
        "verify_kyc_match": (
            TOOL_REGISTRY["verify_kyc_match"],
            {
                "customer_id": customer_id,
                "name": customer_name,
                "email": email,
                "phone": phone
            }
        ),
        "evaluate_device_fingerprint": (
            TOOL_REGISTRY["evaluate_device_fingerprint"],
            {
                "customer_id": customer_id,
                "device_id": device_id,
                "location": location
            }
        ),
        "analyze_behavioral_patterns": (
            TOOL_REGISTRY["analyze_behavioral_patterns"],
            {
                "customer_id": customer_id
            }
        )
    }

    def _run_one(name: str, tool_fn, args: dict) -> tuple:
        tok = _active_case_id.set(case_id)
        try:
            return name, tool_fn.invoke(args)
        except Exception as exc:
            return name, f"{name.upper()}\n  Error: Tool execution failed — {exc}"
        finally:
            _active_case_id.reset(tok)

    tool_results: dict = {}
    tools_used: list = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {
            ex.submit(_run_one, name, fn, args): name
            for name, (fn, args) in task_defs.items()
        }
        for fut in as_completed(futures):
            name, result = fut.result()
            tool_results[name] = result
            tools_used.append(name)

    # Build prompt context with tool results
    _TOOL_ORDER = [
        "detect_transaction_anomalies", "evaluate_location_velocity", "analyze_spending_behavior",
        "verify_kyc_match", "evaluate_device_fingerprint", "analyze_behavioral_patterns"
    ]
    tool_section = "\n\n## PRE-COMPUTED TOOL RESULTS\n(All tools executed — synthesise and produce JSON now)\n"
    for name in _TOOL_ORDER:
        if name in tool_results:
            tool_section += f"\n### {name}\n{tool_results[name]}\n"

    human_content = FRAUD_DATA_TEMPLATE.format(
        customer_name    = mask_name(customer_name),
        customer_id      = mask_id(customer_id),
        email            = email,
        phone            = phone,
        device_id        = mask_id(device_id) if device_id else "Not provided",
        location         = location or "Not provided",
        transaction_id   = mask_id(transaction_id, prefix_chars=8),
        transaction_type = transaction_type,
        merchant         = merchant,
        amount           = amount,
        currency         = currency,
        transaction_date = transaction_date,
        transaction_time = transaction_time,
        dispute_reason   = dispute_reason,
        case_id          = mask_id(case_id),
        created_at       = utc_now_iso(),
    ) + tool_section

    return {
        "tool_results": tool_results,
        "tools_used":   tools_used,
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]
    }


# ── Node 3 — agent ────────────────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(min=1, max=5),
    retry=retry_if_not_exception_type(GroqRateLimitError),
    reraise=True,
)
def call_model(state: FraudReasoningAgentState) -> dict:
    """Agent node — invoke Groq to synthesize risk features."""
    response = _llm.invoke(state["messages"])
    agent_logger.debug("FRIA LLM response received")
    return {"messages": [response]}


# ── Node 4 — finalize ─────────────────────────────────────────────────────────

def finalize_node(state: FraudReasoningAgentState) -> dict:
    """Parse output, validate scores, and calibrate probability/risk tiers server-side."""
    case_id = state["case_id"]
    d       = state["dispute_input"]

    start_time  = state.get("agent_start_time") or 0.0
    duration_ms = round((time.time() - start_time) * 1000, 1) if start_time else 0.0

    messages       = state.get("messages") or []
    tools_used     = list(state.get("tools_used") or [])
    llm_call_count = 1
    tool_msg_count = len(tools_used)

    metrics = {
        "total_duration_ms": duration_ms,
        "llm_calls":         llm_call_count,
        "tool_calls":        tool_msg_count,
        "retry_count":       0,
    }
    agent_metadata = {
        "name":        _AGENT_NAME,
        "version":     _AGENT_VER,
        "model":       _cfg["model"],
        "timestamp":   utc_now_iso(),
        "duration_ms": duration_ms,
    }

    # Parse JSON
    last = messages[-1] if messages else None
    raw  = last.content if last and hasattr(last, "content") else ""
    parsed = extract_json_from_text(raw) if raw else None

    if not parsed:
        agent_logger.warning("FRIA JSON parse failed — using fallback", extra={"case_id": case_id})
        parsed = _fallback_output(case_id, tools_used, agent_metadata, metrics)
        return {"final_output": parsed, "tools_used": tools_used, "agent_metadata": agent_metadata, "metrics": metrics}

    # Stamping server-owned fields
    parsed["case_id"]        = case_id
    parsed["tools_used"]     = tools_used
    parsed["agent_metadata"] = agent_metadata
    parsed["metrics"]        = metrics

    # ── Server-Side Deterministic Recalibrations ─────────────────────────────
    tool_results = state.get("tool_results") or {}
    anomaly_report = str(tool_results.get("detect_transaction_anomalies", ""))
    geovelocity_report = str(tool_results.get("evaluate_location_velocity", ""))
    spending_report = str(tool_results.get("analyze_spending_behavior", ""))
    kyc_report = str(tool_results.get("verify_kyc_match", ""))
    device_report = str(tool_results.get("evaluate_device_fingerprint", ""))
    behavior_report = str(tool_results.get("analyze_behavioral_patterns", ""))

    # Parse Anomaly Flags
    amount_anomaly = False
    for line in spending_report.split("\n"):
        if "Spending Deviation" in line and "ANOMALOUS" in line:
            amount_anomaly = True

    time_anomaly = False
    for line in anomaly_report.split("\n"):
        if "Off-Hours Flag" in line and "Yes" in line:
            time_anomaly = True

    velocity_anomaly = False
    for line in anomaly_report.split("\n"):
        if "Velocity Breach" in line and "Yes" in line:
            velocity_anomaly = True

    geovelocity_breach = False
    for line in geovelocity_report.split("\n"):
        if "Geovelocity Breach" in line and "Yes" in line:
            geovelocity_breach = True

    # Parse KYC Match
    kyc_status = "VERIFIED"
    for line in kyc_report.split("\n"):
        if "Verification" in line or "Status" in line:
            if "FAILED" in line:
                kyc_status = "FAILED"
                break
            elif "SUSPICIOUS" in line:
                kyc_status = "SUSPICIOUS"
                break

    name_match = False
    for line in kyc_report.split("\n"):
        if "Name Match" in line and "Yes" in line:
            name_match = True

    contact_match = False
    email_match = False
    phone_match = False
    for line in kyc_report.split("\n"):
        if "Email Match" in line and "Yes" in line:
            email_match = True
        if "Phone Match" in line and "Yes" in line:
            phone_match = True
    contact_match = email_match and phone_match

    join_date = "N/A"
    for line in kyc_report.split("\n"):
        if "Joining Date" in line:
            join_date = line.split(":")[-1].strip()

    # Parse Device Risk
    recognized_device = False
    for line in device_report.split("\n"):
        if "Recognised Device" in line and "Yes" in line:
            recognized_device = True

    location_consistent = False
    for line in device_report.split("\n"):
        if "Location Consistent" in line and "Yes" in line:
            location_consistent = True

    device_risk = "LOW"
    for line in device_report.split("\n"):
        if "Device Risk" in line:
            if "HIGH" in line:
                device_risk = "HIGH"
            elif "MEDIUM" in line:
                device_risk = "MEDIUM"

    unrecognized_device = not recognized_device
    location_mismatch = not location_consistent

    # Parse Dispute Behavior
    prior_disputes = 0
    for line in behavior_report.split("\n"):
        if "Prior Disputes" in line:
            try:
                prior_disputes = int(line.split(":")[-1].strip())
            except Exception:
                pass

    velocity_breach_detected = False
    for line in behavior_report.split("\n"):
        if "Velocity Breach" in line and "Yes" in line:
            velocity_breach_detected = True

    friendly_fraud_risk = "LOW"
    for line in behavior_report.split("\n"):
        if "Friendly Fraud Risk" in line:
            if "HIGH" in line:
                friendly_fraud_risk = "HIGH"
            elif "MEDIUM" in line:
                friendly_fraud_risk = "MEDIUM"

    # Recalculate spending metrics
    avg_amount = 0.0
    deviation_factor = 0.0
    for line in spending_report.split("\n"):
        if "Average Spend Amount" in line:
            try:
                avg_amount = float(line.split(":")[-1].replace("₹", "").replace(",", "").strip())
            except Exception:
                pass
        elif "Deviation Factor (Z)" in line:
            try:
                deviation_factor = float(line.split(":")[-1].strip())
            except Exception:
                pass

    # Recalculate Trust Score
    trust = 1.0
    if kyc_status == "SUSPICIOUS":    trust -= 0.30
    elif kyc_status == "FAILED":      trust -= 0.70
    
    if device_risk == "MEDIUM":       trust -= 0.20
    elif device_risk == "HIGH":       trust -= 0.50
    
    if prior_disputes >= 3:           trust -= 0.10
    if friendly_fraud_risk == "HIGH" or velocity_breach_detected: trust -= 0.20
    trust_score = round(max(0.00, min(1.00, trust)), 2)

    # Recalculate Behavioral Risk Score
    risk_score_calc = 0.0
    if prior_disputes >= 3:           risk_score_calc += 0.20
    if velocity_breach_detected:      risk_score_calc += 0.30
    if friendly_fraud_risk == "HIGH": risk_score_calc += 0.40
    if device_risk == "MEDIUM":       risk_score_calc += 0.20
    if device_risk == "HIGH":         risk_score_calc += 0.50
    if kyc_status == "SUSPICIOUS":    risk_score_calc += 0.30
    if kyc_status == "FAILED":        risk_score_calc += 0.70
    behavioral_risk_score = round(max(0.00, min(1.00, risk_score_calc)), 2)

    # Fraud Probability calculation
    prob = 0.0
    if amount_anomaly:       prob += 0.20
    if time_anomaly:         prob += 0.15
    if velocity_anomaly:     prob += 0.30
    if geovelocity_breach:   prob += 0.25
    if unrecognized_device:   prob += 0.30
    if location_mismatch:     prob += 0.20

    fraud_probability = round(max(0.00, min(1.00, prob)), 2)

    # Calibrate Risk Level
    if fraud_probability < 0.15:
        risk_level = "LOW"
    elif fraud_probability < 0.40:
        risk_level = "MEDIUM"
    elif fraud_probability < 0.75:
        risk_level = "HIGH"
    else:
        risk_level = "CRITICAL"

    # Merge verified scores into final output
    parsed["fraud_probability"] = fraud_probability
    parsed["fraud_risk_level"] = risk_level
    parsed["anomaly_detection"] = {
        "amount_anomaly": amount_anomaly,
        "time_anomaly": time_anomaly,
        "velocity_anomaly": velocity_anomaly
    }
    parsed["device_location_risk"] = {
        "unrecognized_device": unrecognized_device,
        "location_mismatch": location_mismatch
    }
    parsed["spending_history_analysis"] = {
        "average_amount": avg_amount,
        "deviation_factor": deviation_factor
    }

    # Trust intelligence attributes
    parsed["user_trust_score"] = trust_score
    parsed["behavioral_risk_score"] = behavioral_risk_score
    parsed["identity_verification"] = kyc_status
    parsed["kyc_checks"] = {
        "name_match": name_match,
        "contact_match": contact_match,
        "join_date": join_date
    }
    parsed["device_fingerprint"] = {
        "recognized_device": recognized_device,
        "location_consistent": location_consistent,
        "device_risk": device_risk
    }
    parsed["dispute_behavior"] = {
        "prior_dispute_count": prior_disputes,
        "velocity_breach_detected": velocity_breach_detected,
        "friendly_fraud_risk": friendly_fraud_risk
    }

    log_workflow_event(
        agent_logger,
        event="FRIA_FRAUD_EVALUATION_COMPLETE",
        stage="fraud_reasoning",
        case_id=case_id,
        customer_id=d.get("customer_id"),
        extra={
            "fraud_probability": fraud_probability,
            "fraud_risk_level": risk_level,
            "user_trust_score": trust_score,
            "behavioral_risk_score": behavioral_risk_score,
            "duration_ms": duration_ms
        }
    )

    return {
        "final_output": parsed,
        "tools_used":   tools_used,
        "agent_metadata": agent_metadata,
        "metrics":        metrics,
    }


def _fallback_output(
    case_id: str, tools_used: list, agent_metadata: dict, metrics: dict
) -> dict:
    """Minimal safe fallback returned if LLM fails or output cannot be parsed."""
    return {
        "case_id":                    case_id,
        "fraud_probability":          0.50,
        "fraud_risk_level":           "MEDIUM",
        "anomaly_detection": {
            "amount_anomaly":         False,
            "time_anomaly":           False,
            "velocity_anomaly":       False
        },
        "device_location_risk": {
            "unrecognized_device":    False,
            "location_mismatch":      False
        },
        "spending_history_analysis": {
            "average_amount":         0.00,
            "deviation_factor":       0.00
        },
        "fraud_reasoning": [
            "Fraud evaluation failed — JSON parse error. Falling back to default risk settings."
        ],
        "fraud_summary": "Fraud risk estimation failed. Standard safety settings assign medium risk.",
        "user_trust_score":           0.50,
        "behavioral_risk_score":      0.50,
        "identity_verification":      "SUSPICIOUS",
        "kyc_checks": {
            "name_match":             False,
            "contact_match":          False,
            "join_date":              "N/A"
        },
        "device_fingerprint": {
            "recognized_device":      False,
            "location_consistent":    False,
            "device_risk":            "MEDIUM"
        },
        "dispute_behavior": {
            "prior_dispute_count":    0,
            "velocity_breach_detected": False,
            "friendly_fraud_risk":    "MEDIUM"
        },
        "trust_reasoning": [
            "Trust evaluation failed — JSON parse error. Falling back to default risk settings."
        ],
        "trust_summary": "Trust brief generation failed. Standard safety review limits trust score.",
        "tools_used":                 tools_used,
        "agent_metadata":             agent_metadata,
        "metrics":                    metrics
    }
