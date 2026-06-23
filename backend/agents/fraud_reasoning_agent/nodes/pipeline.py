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
    """Run transaction-type-aware fraud tools in parallel based on channel routing."""
    d = state["dispute_input"]
    case_id = state["case_id"]
    meta = d.get("transaction_metadata") or {}

    customer_id      = d.get("customer_id", "")
    customer_name    = d.get("customer_name", "")
    email            = d.get("email", "")
    phone            = d.get("phone", "")
    transaction_id   = d.get("transaction_id", "")
    transaction_type = d.get("transaction_type", "")
    merchant         = d.get("merchant", "")
    merchant_id      = meta.get("merchant_id") or d.get("merchant_id", "")
    amount           = float(d.get("amount", 0.0))
    currency         = d.get("currency", "INR")
    transaction_date = d.get("transaction_date", "")
    transaction_time = d.get("transaction_time", "")
    location         = meta.get("transaction_location") or d.get("location") or ""
    device_id        = meta.get("device_id") or d.get("device_id") or ""
    dispute_reason   = d.get("dispute_reason", "")

    # ── Channel routing ────────────────────────────────────────────────────────
    _txn = transaction_type.lower().strip()
    _UPI             = {"upi"}
    _INTERNET_MOBILE = {"net banking", "internet banking", "mobile banking", "imps",
                        "neft", "rtgs", "netbanking", "online transfer"}
    _CARD_POS        = {"debit card", "credit card", "debit card pos", "credit card pos"}
    _ATM             = {"atm", "atm cash", "atm withdrawal", "cash withdrawal"}

    if _txn in _UPI:
        channel = "UPI"
    elif _txn in _INTERNET_MOBILE:
        channel = "INTERNET_BANKING"
    elif _txn in _CARD_POS:
        channel = "CARD_POS"
    elif _txn in _ATM:
        channel = "ATM"
    else:
        channel = "UPI"  # safe fallback for unknown digital transactions

    # ── Build tool set per channel ─────────────────────────────────────────────
    _common_merchant = ("evaluate_merchant_risk_intelligence", {
        "merchant_id": merchant_id,
        "merchant_name": merchant,
    })
    _common_spending = ("analyze_spending_behavior", {"customer_id": customer_id, "amount": amount})
    _common_behavior = ("analyze_behavioral_patterns", {"customer_id": customer_id})
    _digital_core = {
        "detect_transaction_anomalies": (
            TOOL_REGISTRY["detect_transaction_anomalies"],
            {"customer_id": customer_id, "transaction_time": transaction_time, "transaction_date": transaction_date}
        ),
        "evaluate_location_velocity": (
            TOOL_REGISTRY["evaluate_location_velocity"],
            {"customer_id": customer_id, "location": location, "transaction_date": transaction_date, "transaction_time": transaction_time}
        ),
        "analyze_spending_behavior": (TOOL_REGISTRY["analyze_spending_behavior"], _common_spending[1]),
        "verify_kyc_match": (
            TOOL_REGISTRY["verify_kyc_match"],
            {"customer_id": customer_id, "name": customer_name, "email": email, "phone": phone, "dispute_category": d.get("dispute_category", "")}
        ),
        "evaluate_device_fingerprint": (
            TOOL_REGISTRY["evaluate_device_fingerprint"],
            {"customer_id": customer_id, "device_id": device_id, "location": location}
        ),
        "analyze_behavioral_patterns": (TOOL_REGISTRY["analyze_behavioral_patterns"], _common_behavior[1]),
        "evaluate_merchant_risk_intelligence": (TOOL_REGISTRY["evaluate_merchant_risk_intelligence"], _common_merchant[1]),
    }
    _universal_tools = {
        "evaluate_historical_fraud_victim_score": (TOOL_REGISTRY["evaluate_historical_fraud_victim_score"], {"case_id": case_id}),
        "detect_account_takeover_pattern":        (TOOL_REGISTRY["detect_account_takeover_pattern"],        {"case_id": case_id}),
        "analyze_mule_account_indicators":        (TOOL_REGISTRY["analyze_mule_account_indicators"],        {"case_id": case_id}),
        "detect_historical_case_similarity":      (TOOL_REGISTRY["detect_historical_case_similarity"],      {"case_id": case_id}),
    }

    if channel == "UPI":
        task_defs = {
            **_digital_core,
            "analyze_new_beneficiary_risk":     (TOOL_REGISTRY["analyze_new_beneficiary_risk"],     {"case_id": case_id}),
            "detect_upi_collect_request_fraud": (TOOL_REGISTRY["detect_upi_collect_request_fraud"], {"case_id": case_id}),
            "analyze_beneficiary_velocity":     (TOOL_REGISTRY["analyze_beneficiary_velocity"],     {"case_id": case_id}),
            "evaluate_upi_handle_reputation":   (TOOL_REGISTRY["evaluate_upi_handle_reputation"],   {"case_id": case_id}),
            "analyze_dormant_beneficiary_risk": (TOOL_REGISTRY["analyze_dormant_beneficiary_risk"], {"case_id": case_id}),
            **_universal_tools,
        }

    elif channel == "INTERNET_BANKING":
        task_defs = {
            **_digital_core,
            "detect_impossible_login_travel":            (TOOL_REGISTRY["detect_impossible_login_travel"],            {"case_id": case_id}),
            "analyze_device_change_large_transfer":      (TOOL_REGISTRY["analyze_device_change_large_transfer"],      {"case_id": case_id}),
            "detect_password_reset_transaction_pattern": (TOOL_REGISTRY["detect_password_reset_transaction_pattern"], {"case_id": case_id}),
            "analyze_mobile_number_change_risk":         (TOOL_REGISTRY["analyze_mobile_number_change_risk"],         {"case_id": case_id}),
            **_universal_tools,
        }

    elif channel == "CARD_POS":
        task_defs = {
            "analyze_spending_behavior": (TOOL_REGISTRY["analyze_spending_behavior"], _common_spending[1]),
            "analyze_behavioral_patterns": (TOOL_REGISTRY["analyze_behavioral_patterns"], _common_behavior[1]),
            "evaluate_merchant_risk_intelligence": (TOOL_REGISTRY["evaluate_merchant_risk_intelligence"], _common_merchant[1]),
            "analyze_card_velocity": (
                TOOL_REGISTRY["analyze_card_velocity"],
                {"customer_id": customer_id, "transaction_date": transaction_date, "transaction_time": transaction_time}
            ),
            "evaluate_atm_pos_distance": (
                TOOL_REGISTRY["evaluate_atm_pos_distance"],
                {"customer_id": customer_id, "transaction_date": transaction_date, "transaction_time": transaction_time, "location": location}
            ),
            "analyze_foreign_usage": (
                TOOL_REGISTRY["analyze_foreign_usage"],
                {"customer_id": customer_id, "merchant": merchant, "location": location}
            ),
            "analyze_card_present_anomalies": (
                TOOL_REGISTRY["analyze_card_present_anomalies"],
                {"customer_id": customer_id, "merchant": merchant, "amount": amount, "transaction_time": transaction_time}
            ),
            # Advanced card intelligence tools
            "detect_merchant_compromise_pattern":  (TOOL_REGISTRY["detect_merchant_compromise_pattern"],  {"case_id": case_id}),
            "analyze_first_time_merchant":          (TOOL_REGISTRY["analyze_first_time_merchant"],          {"case_id": case_id}),
            "evaluate_merchant_resolution_history": (TOOL_REGISTRY["evaluate_merchant_resolution_history"], {"case_id": case_id}),
            "detect_card_testing_pattern":          (TOOL_REGISTRY["detect_card_testing_pattern"],          {"case_id": case_id}),
            "analyze_multi_merchant_burst":         (TOOL_REGISTRY["analyze_multi_merchant_burst"],         {"case_id": case_id}),
            "evaluate_mcc_risk":                    (TOOL_REGISTRY["evaluate_mcc_risk"],                    {"case_id": case_id}),
            "analyze_decline_success_pattern":      (TOOL_REGISTRY["analyze_decline_success_pattern"],      {"case_id": case_id}),
            "check_refund_reversal_absence":        (TOOL_REGISTRY["check_refund_reversal_absence"],        {"case_id": case_id}),
            **_universal_tools,
        }

    else:  # ATM
        task_defs = {
            "analyze_spending_behavior": (TOOL_REGISTRY["analyze_spending_behavior"], _common_spending[1]),
            "analyze_behavioral_patterns": (TOOL_REGISTRY["analyze_behavioral_patterns"], _common_behavior[1]),
            "evaluate_merchant_risk_intelligence": (TOOL_REGISTRY["evaluate_merchant_risk_intelligence"], _common_merchant[1]),
            "analyze_atm_velocity": (
                TOOL_REGISTRY["analyze_atm_velocity"],
                {"customer_id": customer_id, "transaction_date": transaction_date, "transaction_time": transaction_time}
            ),
            "evaluate_atm_geovelocity": (
                TOOL_REGISTRY["evaluate_atm_geovelocity"],
                {"customer_id": customer_id, "transaction_date": transaction_date, "transaction_time": transaction_time, "location": location}
            ),
            "analyze_cash_withdrawal_patterns": (
                TOOL_REGISTRY["analyze_cash_withdrawal_patterns"],
                {"customer_id": customer_id, "amount": amount}
            ),
            "analyze_consecutive_atm_withdrawals": (TOOL_REGISTRY["analyze_consecutive_atm_withdrawals"], {"case_id": case_id}),
            "analyze_foreign_atm_usage":           (TOOL_REGISTRY["analyze_foreign_atm_usage"],           {"case_id": case_id}),
            "detect_sim_swap_atm_pattern":         (TOOL_REGISTRY["detect_sim_swap_atm_pattern"],         {"case_id": case_id}),
            **_universal_tools,
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
    max_workers = min(len(task_defs), 20)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_run_one, name, fn, args): name
            for name, (fn, args) in task_defs.items()
        }
        for fut in as_completed(futures):
            name, result = fut.result()
            tool_results[name] = result
            tools_used.append(name)

    # Build prompt context — include all tools that ran
    _TOOL_ORDER = [
        # Core digital
        "detect_transaction_anomalies", "evaluate_location_velocity", "analyze_spending_behavior",
        "verify_kyc_match", "evaluate_device_fingerprint", "analyze_behavioral_patterns",
        "evaluate_merchant_risk_intelligence",
        # Card POS
        "analyze_card_velocity", "evaluate_atm_pos_distance", "analyze_foreign_usage", "analyze_card_present_anomalies",
        "detect_merchant_compromise_pattern", "analyze_first_time_merchant", "evaluate_merchant_resolution_history",
        "detect_card_testing_pattern", "analyze_multi_merchant_burst", "evaluate_mcc_risk",
        "analyze_decline_success_pattern", "check_refund_reversal_absence",
        # ATM
        "analyze_atm_velocity", "evaluate_atm_geovelocity", "analyze_cash_withdrawal_patterns",
        "analyze_consecutive_atm_withdrawals", "analyze_foreign_atm_usage", "detect_sim_swap_atm_pattern",
        # UPI
        "analyze_new_beneficiary_risk", "detect_upi_collect_request_fraud", "analyze_beneficiary_velocity",
        "evaluate_upi_handle_reputation", "analyze_dormant_beneficiary_risk",
        # Internet Banking
        "detect_impossible_login_travel", "analyze_device_change_large_transfer",
        "detect_password_reset_transaction_pattern", "analyze_mobile_number_change_risk",
        # Universal
        "evaluate_historical_fraud_victim_score", "detect_account_takeover_pattern",
        "analyze_mule_account_indicators", "detect_historical_case_similarity",
    ]
    tool_section = f"\n\n## PRE-COMPUTED TOOL RESULTS (Channel: {channel})\n(All tools executed — synthesise and produce JSON now)\n"
    for name in _TOOL_ORDER:
        if name in tool_results:
            tool_section += f"\n### {name}\n{tool_results[name]}\n"

    def _flag(key: str) -> str:
        val = str(meta.get(key) or d.get(key) or "").strip().lower()
        return "Yes" if val in {"yes", "true", "1"} else "No"

    _extra = (meta.get("fraud_additional_details") or d.get("fraud_additional_details") or "").strip()
    _fraud_additional_section = f"\nCUSTOMER FRAUD NARRATIVE:\n  {_extra}\n" if _extra else ""

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
        otp_received          = _flag("otp_received"),
        otp_shared            = _flag("otp_shared"),
        bank_impersonation    = _flag("bank_impersonation"),
        remote_access         = _flag("remote_access"),
        screen_sharing        = _flag("screen_sharing"),
        sim_swap_suspected    = _flag("sim_swap_suspected"),
        unknown_beneficiary   = _flag("unknown_beneficiary"),
        phishing_link         = _flag("phishing_link"),
        card_lost             = _flag("card_lost"),
        device_lost           = _flag("device_lost"),
        fraud_selected        = "Yes" if d.get("fraud_selected") else "No",
        fraud_additional_section = _fraud_additional_section,
        case_id          = mask_id(case_id),
        created_at       = utc_now_iso(),
    ) + tool_section

    return {
        "tool_results": tool_results,
        "tools_used":   tools_used,
        "channel":      channel,
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
    channel = state.get("channel", "DIGITAL")

    # Core tool reports
    anomaly_report     = str(tool_results.get("detect_transaction_anomalies", ""))
    geovelocity_report = str(tool_results.get("evaluate_location_velocity", ""))
    spending_report    = str(tool_results.get("analyze_spending_behavior", ""))
    kyc_report         = str(tool_results.get("verify_kyc_match", ""))
    device_report      = str(tool_results.get("evaluate_device_fingerprint", ""))
    behavior_report    = str(tool_results.get("analyze_behavioral_patterns", ""))

    # New tool reports
    merchant_report      = str(tool_results.get("evaluate_merchant_risk_intelligence", ""))
    card_vel_report      = str(tool_results.get("analyze_card_velocity", ""))
    atm_pos_report       = str(tool_results.get("evaluate_atm_pos_distance", ""))
    foreign_report       = str(tool_results.get("analyze_foreign_usage", ""))
    card_anomaly_report  = str(tool_results.get("analyze_card_present_anomalies", ""))
    atm_vel_report       = str(tool_results.get("analyze_atm_velocity", ""))
    atm_geo_report       = str(tool_results.get("evaluate_atm_geovelocity", ""))
    cash_report          = str(tool_results.get("analyze_cash_withdrawal_patterns", ""))

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

    # For CARD_POS and ATM channels, device fingerprint tool does not run.
    # Default to False (not a fraud signal) rather than True (false positive).
    if channel in ("CARD_POS", "ATM"):
        unrecognized_device = False
        location_mismatch   = False
    else:
        unrecognized_device = not recognized_device
        location_mismatch   = not location_consistent

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

    # ── Parse new tool outputs ────────────────────────────────────────────────

    # Merchant risk
    merchant_blacklisted = False
    merchant_risk_level = "LOW"
    for line in merchant_report.split("\n"):
        if "Blacklisted" in line and "Yes" in line:
            merchant_blacklisted = True
        if "Merchant Risk Level" in line:
            if "CRITICAL" in line:  merchant_risk_level = "CRITICAL"
            elif "HIGH" in line:    merchant_risk_level = "HIGH"
            elif "MEDIUM" in line:  merchant_risk_level = "MEDIUM"

    # Card POS signals
    card_velocity_breach = any(
        "Velocity Breach" in line and "Yes" in line
        for line in card_vel_report.split("\n")
    )
    atm_pos_impossible = any(
        "Impossible Travel" in line and "Yes" in line
        for line in atm_pos_report.split("\n")
    )
    foreign_usage = any(
        "Foreign Usage" in line and "Yes" in line
        for line in foreign_report.split("\n")
    )

    # ATM signals
    atm_velocity_breach = any(
        "Velocity Breach" in line and "Yes" in line
        for line in atm_vel_report.split("\n")
    )
    atm_geo_breach = any(
        "Impossible Travel" in line and "Yes" in line
        for line in atm_geo_report.split("\n")
    )
    cash_anomaly = any(
        ("Large Withdrawal" in line or "Repeated Withdrawal" in line) and "Yes" in line
        for line in cash_report.split("\n")
    )

    # Fraud Probability calculation
    dispute_category = str(d.get("dispute_category") or "")
    prob = 0.0

    # Category base lift — customer asserting fraud outright
    if "unauthorized" in dispute_category.lower():
        prob += 0.15

    # Anomaly signals
    if amount_anomaly:
        prob += 0.25 if deviation_factor > 5.0 else 0.15
    if time_anomaly:         prob += 0.15
    if velocity_anomaly:     prob += 0.30
    if geovelocity_breach:   prob += 0.35
    if unrecognized_device:  prob += 0.30
    if location_mismatch:    prob += 0.20

    # Behavioral risk crossover
    if behavioral_risk_score >= 0.60: prob += 0.15

    # Signals from customer-submitted fraud metadata (strongest indicators)
    meta = d.get("transaction_metadata") or {}
    def _yes(k: str) -> bool:
        return str(meta.get(k) or "").strip().lower() in {"yes", "true", "1"}

    if _yes("bank_impersonation"):  prob += 0.30
    if _yes("remote_access"):       prob += 0.25
    if _yes("screen_sharing"):      prob += 0.20
    if _yes("otp_shared"):          prob += 0.20
    if _yes("sim_swap_suspected"):  prob += 0.20
    if _yes("phishing_link"):       prob += 0.15
    if _yes("unknown_beneficiary"): prob += 0.10
    if _yes("device_lost"):         prob += 0.10
    if _yes("card_lost"):           prob += 0.10
    if bool(d.get("fraud_selected")): prob += 0.10

    # Merchant risk signals (all channels)
    if merchant_blacklisted:                prob += 0.50
    elif merchant_risk_level == "CRITICAL": prob += 0.30
    elif merchant_risk_level == "HIGH":     prob += 0.15

    # Card POS signals
    if card_velocity_breach:  prob += 0.25
    if atm_pos_impossible:    prob += 0.35
    if foreign_usage:         prob += 0.30

    # ATM signals
    if atm_velocity_breach:   prob += 0.25
    if atm_geo_breach:        prob += 0.35
    if cash_anomaly:          prob += 0.15

    # ── Card POS advanced intelligence ───────────────────────────────────────
    _mc_report   = str(tool_results.get("detect_merchant_compromise_pattern", ""))
    _ftm_report  = str(tool_results.get("analyze_first_time_merchant", ""))
    _mrh_report  = str(tool_results.get("evaluate_merchant_resolution_history", ""))
    _ct_report   = str(tool_results.get("detect_card_testing_pattern", ""))
    _mmb_report  = str(tool_results.get("analyze_multi_merchant_burst", ""))
    _mcc_report  = str(tool_results.get("evaluate_mcc_risk", ""))
    _dsp_report  = str(tool_results.get("analyze_decline_success_pattern", ""))
    _rra_report  = str(tool_results.get("check_refund_reversal_absence", ""))

    merchant_compromise_level = "LOW"
    for _l in _mc_report.split("\n"):
        if "Risk Level" in _l:
            if "CRITICAL" in _l: merchant_compromise_level = "CRITICAL"
            elif "HIGH" in _l:   merchant_compromise_level = "HIGH"

    first_time_high_value = any("High Value First Time" in _l and "Yes" in _l for _l in _ftm_report.split("\n"))

    merchant_favor_rate = 0.0
    for _l in _mrh_report.split("\n"):
        if "Customer Favor Rate" in _l:
            try: merchant_favor_rate = float(_l.split(":")[-1].replace("%", "").strip())
            except Exception: pass

    card_testing_detected  = any("Card Testing Detected" in _l and "Yes" in _l for _l in _ct_report.split("\n"))
    merchant_burst_detected = any("Merchant Burst Detected" in _l and "Yes" in _l for _l in _mmb_report.split("\n"))

    mcc_risk_level = "LOW"
    for _l in _mcc_report.split("\n"):
        if "Category Risk Level" in _l:
            if "CRITICAL" in _l: mcc_risk_level = "CRITICAL"
            elif "HIGH" in _l:   mcc_risk_level = "HIGH"
            elif "MEDIUM" in _l: mcc_risk_level = "MEDIUM"

    decline_success_pattern = any("Pattern Detected" in _l and "Yes" in _l for _l in _dsp_report.split("\n"))
    refund_claim_unverified = any("Refund Claim Unverified" in _l and "Yes" in _l for _l in _rra_report.split("\n"))

    # Merchant compromise
    if merchant_compromise_level == "CRITICAL":  prob += 0.40
    elif merchant_compromise_level == "HIGH":    prob += 0.25

    # First-time high-value merchant
    if first_time_high_value:                    prob += 0.15

    # Historical merchant resolution pattern
    if merchant_favor_rate > 85.0:              prob += 0.25
    elif merchant_favor_rate > 70.0:            prob += 0.15

    # Card fraud patterns
    if card_testing_detected:                    prob += 0.30
    if merchant_burst_detected:                 prob += 0.25

    # MCC risk
    if mcc_risk_level == "CRITICAL":            prob += 0.20
    elif mcc_risk_level == "HIGH":              prob += 0.10

    # Decline-success and refund
    if decline_success_pattern:                 prob += 0.20
    if refund_claim_unverified:                 prob += 0.15

    # ── UPI intelligence ─────────────────────────────────────────────────────
    _nbr_report  = str(tool_results.get("analyze_new_beneficiary_risk", ""))
    _ucr_report  = str(tool_results.get("detect_upi_collect_request_fraud", ""))
    _bv_report   = str(tool_results.get("analyze_beneficiary_velocity", ""))
    _uhr_report  = str(tool_results.get("evaluate_upi_handle_reputation", ""))
    _dbr_report  = str(tool_results.get("analyze_dormant_beneficiary_risk", ""))

    new_beneficiary_risk  = any("New Beneficiary Risk" in l and "Yes" in l for l in _nbr_report.split("\n"))
    upi_collect_fraud     = any("Collect Request Detected" in l and "Yes" in l for l in _ucr_report.split("\n"))
    beneficiary_vel_flag  = any("Velocity Flag" in l and "Yes" in l for l in _bv_report.split("\n"))
    upi_reputation        = "LOW_RISK"
    for _l in _uhr_report.split("\n"):
        if "UPI Handle Reputation" in _l:
            if "HIGH_RISK" in _l:    upi_reputation = "HIGH_RISK"
            elif "MEDIUM_RISK" in _l: upi_reputation = "MEDIUM_RISK"
    dormant_beneficiary   = any("Dormant Risk" in l and "Yes" in l for l in _dbr_report.split("\n"))

    if new_beneficiary_risk:                    prob += 0.20
    if upi_collect_fraud:                       prob += 0.30
    if beneficiary_vel_flag:                    prob += 0.30
    if upi_reputation == "HIGH_RISK":           prob += 0.35
    if dormant_beneficiary:                     prob += 0.20

    # ── Internet / Mobile Banking intelligence ────────────────────────────────
    _ilt_report  = str(tool_results.get("detect_impossible_login_travel", ""))
    _dct_report  = str(tool_results.get("analyze_device_change_large_transfer", ""))
    _prt_report  = str(tool_results.get("detect_password_reset_transaction_pattern", ""))
    _mnc_report  = str(tool_results.get("analyze_mobile_number_change_risk", ""))

    impossible_login       = any("Impossible Travel" in l and "Yes" in l for l in _ilt_report.split("\n"))
    device_change_transfer = any("Risk Detected" in l and "Yes" in l for l in _dct_report.split("\n"))
    pwd_reset_pattern      = any("Pattern Detected" in l and "Yes" in l for l in _prt_report.split("\n"))
    mobile_change_risk     = any("Mobile Number Changed" in l and "Yes" in l for l in _mnc_report.split("\n"))

    if impossible_login:                        prob += 0.35
    if device_change_transfer:                  prob += 0.30
    if pwd_reset_pattern:                       prob += 0.30
    if mobile_change_risk:                      prob += 0.35

    # ── ATM advanced intelligence ─────────────────────────────────────────────
    _caw_report  = str(tool_results.get("analyze_consecutive_atm_withdrawals", ""))
    _fau_report  = str(tool_results.get("analyze_foreign_atm_usage", ""))
    _ssa_report  = str(tool_results.get("detect_sim_swap_atm_pattern", ""))

    consecutive_atm = any("Consecutive Pattern" in l and "Yes" in l for l in _caw_report.split("\n"))
    foreign_atm     = any("Foreign ATM Usage" in l and "Yes" in l for l in _fau_report.split("\n"))
    sim_swap_atm    = any("Risk Level" in l and "CRITICAL" in l for l in _ssa_report.split("\n"))

    if consecutive_atm:                         prob += 0.25
    if foreign_atm:                             prob += 0.35
    if sim_swap_atm:                            prob += 0.40

    # ── Universal intelligence ────────────────────────────────────────────────
    _hfv_report  = str(tool_results.get("evaluate_historical_fraud_victim_score", ""))
    _ato_report  = str(tool_results.get("detect_account_takeover_pattern", ""))
    _mule_report = str(tool_results.get("analyze_mule_account_indicators", ""))
    _hcs_report  = str(tool_results.get("detect_historical_case_similarity", ""))

    prior_fraud_victim = any("Victim Score" in l and ("HIGH" in l or "MEDIUM" in l) for l in _hfv_report.split("\n"))
    ato_risk_level     = "LOW"
    for _l in _ato_report.split("\n"):
        if "Account Takeover Risk" in _l:
            if "CRITICAL" in _l: ato_risk_level = "CRITICAL"
            elif "HIGH" in _l:   ato_risk_level = "HIGH"
            elif "MEDIUM" in _l: ato_risk_level = "MEDIUM"
    mule_suspected      = any("Mule Account Suspected" in l and "Yes" in l for l in _mule_report.split("\n"))
    case_similarity_high = any("Pattern Risk" in l and "HIGH" in l for l in _hcs_report.split("\n"))

    if prior_fraud_victim:                      prob += 0.15
    if ato_risk_level == "CRITICAL":            prob += 0.40
    elif ato_risk_level == "HIGH":              prob += 0.25
    if mule_suspected:                          prob += 0.40
    if case_similarity_high:                    prob += 0.20

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
    parsed["merchant_risk"] = {
        "merchant_risk_level": merchant_risk_level,
        "merchant_blacklisted": merchant_blacklisted,
    }
    parsed["channel"] = channel
    parsed["transaction_type_detected"] = d.get("transaction_type", "")
    parsed["tool_signals"] = {
        "card_velocity_breach":       card_velocity_breach,
        "atm_pos_impossible_travel":  atm_pos_impossible,
        "foreign_usage":              foreign_usage,
        "atm_velocity_breach":        atm_velocity_breach,
        "atm_geo_breach":             atm_geo_breach,
        "cash_withdrawal_anomaly":    cash_anomaly,
        # Card POS advanced intelligence
        "merchant_compromise_level":  merchant_compromise_level,
        "first_time_high_value":      first_time_high_value,
        "merchant_favor_rate":        round(merchant_favor_rate, 1),
        "card_testing_detected":      card_testing_detected,
        "merchant_burst_detected":    merchant_burst_detected,
        "mcc_risk_level":             mcc_risk_level,
        "decline_success_pattern":    decline_success_pattern,
        "refund_claim_unverified":    refund_claim_unverified,
        # UPI intelligence
        "new_beneficiary_risk":       new_beneficiary_risk,
        "upi_collect_fraud":          upi_collect_fraud,
        "beneficiary_vel_flag":       beneficiary_vel_flag,
        "upi_handle_reputation":      upi_reputation,
        "dormant_beneficiary":        dormant_beneficiary,
        # Internet Banking intelligence
        "impossible_login_travel":    impossible_login,
        "device_change_transfer":     device_change_transfer,
        "pwd_reset_pattern":          pwd_reset_pattern,
        "mobile_change_risk":         mobile_change_risk,
        # ATM advanced intelligence
        "consecutive_atm":            consecutive_atm,
        "foreign_atm_usage":          foreign_atm,
        "sim_swap_atm":               sim_swap_atm,
        # Universal intelligence
        "prior_fraud_victim":         prior_fraud_victim,
        "ato_risk_level":             ato_risk_level,
        "mule_suspected":             mule_suspected,
        "case_similarity_high":       case_similarity_high,
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
        "merchant_risk": {
            "merchant_risk_level": "LOW",
            "merchant_blacklisted": False,
        },
        "channel": "DIGITAL",
        "transaction_type_detected": "",
        "tool_signals": {
            "card_velocity_breach":    False,
            "atm_pos_impossible_travel": False,
            "foreign_usage":           False,
            "atm_velocity_breach":     False,
            "atm_geo_breach":          False,
            "cash_withdrawal_anomaly": False,
        },
        "tools_used":                 tools_used,
        "agent_metadata":             agent_metadata,
        "metrics":                    metrics
    }
