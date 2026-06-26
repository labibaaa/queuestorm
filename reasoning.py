from typing import Optional
import re
from datetime import datetime, timezone, timedelta


CASE_TYPE_MAP = {
    "wrong_transfer": [
        "wrong", "wrong number", "wrong person", "wrong recipient",
        "sent to wrong", "mistake transfer", "wrong transfer", "wrong mobile",
        "ভুল নম্বর", "ভুল transfer", "wrong e pathiye", "vul number",
        "vul nambor", "wrong pathiyechi", "ভুল পাঠিয়েছি",
    ],
    "payment_failed": [
        "payment failed", "failed", "deducted but", "money gone", "balance deducted",
        "not received", "payment not", "transaction failed", "cut but",
        "টাকা কাটা গেছে", "balance কেটে নিয়েছে", "payment hoyni",
        "taka kata geche", "payment jay nai", "failed hoyeche",
    ],
    "refund_request": [
        "refund", "money back", "return my money", "get my money back",
        "return the amount", "reimburse",
        "টাকা ফেরত", "taka ferat", "feret dao", "ফেরত চাই",
        "taka ferot", "money ferat chai",
    ],
    "duplicate_payment": [
        "charged twice", "deducted twice", "paid twice", "double charge",
        "duplicate", "two times", "debited twice",
        "দুইবার কাটা", "duibar kata", "double deduct", "dui bar payment",
        "২ বার", "2 bar katse",
    ],
    "merchant_settlement_delay": [
        "settlement", "not settled", "settlement delay", "merchant payment",
        "sales not", "not received settlement",
        "settlement আসেনি", "settlement pay ni", "merchant payment aseni",
    ],
    "agent_cash_in_issue": [
        "cash in", "cash-in", "agent", "deposited", "not reflected",
        "balance not updated", "agent sent", "bkash agent",
        "cash in hoyni", "agent e diyechi", "balance আসেনি",
        "agent theke", "cash in korsi kintu", "এজেন্ট",
    ],
    "phishing_or_social_engineering": [
        "fraud", "scam", "phishing", "someone called", "fake call",
        "asked for otp", "asked for pin", "suspicious", "bkash call",
        "someone asked", "pin share", "otp share", "social engineering",
        "phone kore pin চেয়েছে", "otp niyeche", "fake bkash call",
        "bkash er lok bole", "pin share korte", "প্রতারণা",
    ],
}

DEPARTMENT_MAP = {
    "wrong_transfer": "dispute_resolution",
    "payment_failed": "payments_ops",
    "refund_request": "dispute_resolution",
    "duplicate_payment": "payments_ops",
    "merchant_settlement_delay": "merchant_operations",
    "agent_cash_in_issue": "agent_operations",
    "phishing_or_social_engineering": "fraud_risk",
    "other": "customer_support",
}

SEVERITY_MAP = {
    "wrong_transfer": "high",
    "payment_failed": "medium",
    "refund_request": "medium",
    "duplicate_payment": "high",
    "merchant_settlement_delay": "medium",
    "agent_cash_in_issue": "high",
    "phishing_or_social_engineering": "critical",
    "other": "low",
}

HUMAN_REVIEW_MAP = {
    "wrong_transfer": True,
    "payment_failed": True,
    "refund_request": False,
    "duplicate_payment": True,
    "merchant_settlement_delay": False,
    "agent_cash_in_issue": True,
    "phishing_or_social_engineering": True,
    "other": False,
}


def classify_case_type(complaint: str) -> str:
    complaint_lower = complaint.lower()
    scores = {}
    for case_type, keywords in CASE_TYPE_MAP.items():
        score = sum(1 for kw in keywords if kw in complaint_lower)
        if score > 0:
            scores[case_type] = score
    if not scores:
        return "other"
    return max(scores, key=scores.get)


def find_relevant_transaction(complaint: str, transaction_history: list) -> Optional[str]:
    if not transaction_history:
        return None

    complaint_lower = complaint.lower()

    amount_matches = re.findall(r'\b(\d{2,6})\b', complaint)
    complaint_amounts = set(int(a) for a in amount_matches)

    time_cues_today = any(w in complaint_lower for w in ["today", "just now", "আজকে", "ekhon"])
    time_cues_yesterday = any(w in complaint_lower for w in ["yesterday", "গতকাল", "kal"])

    now = datetime.now(timezone.utc)
    today_date = now.date()
    yesterday_date = (now - timedelta(days=1)).date()

    scored = []
    for txn in transaction_history:
        score = 0

        txn_amount = txn.get("amount", 0)
        if complaint_amounts and txn_amount in complaint_amounts:
            score += 3

        try:
            txn_dt = datetime.fromisoformat(txn["timestamp"].replace("Z", "+00:00"))
            txn_date = txn_dt.date()
            if time_cues_today and txn_date == today_date:
                score += 2
            elif time_cues_yesterday and txn_date == yesterday_date:
                score += 2
        except Exception:
            pass

        counterparty = txn.get("counterparty", "")
        if counterparty and counterparty.replace("+88", "") in complaint:
            score += 4
        if counterparty and counterparty in complaint:
            score += 4

        if txn.get("status") == "failed" and any(
            w in complaint_lower for w in ["failed", "not received", "didn't receive", "deducted"]
        ):
            score += 2
        if txn.get("status") == "pending" and any(
            w in complaint_lower for w in ["pending", "not reflected", "not showing", "not received"]
        ):
            score += 2

        scored.append((score, txn["transaction_id"]))

    scored.sort(key=lambda x: -x[0])

    if len(scored) == 1 and scored[0][0] == 0:
        return scored[0][1]

    if scored[0][0] > 0:
        if len(scored) == 1:
            return scored[0][1]
        if scored[0][0] > scored[1][0]:
            return scored[0][1]
        return None

    return None


def compute_evidence_verdict(
    complaint: str,
    transaction_history: list,
    relevant_txn_id: Optional[str],
    case_type: str
) -> str:
    if not transaction_history:
        return "insufficient_data"

    if relevant_txn_id is None:
        return "insufficient_data"

    txn = next((t for t in transaction_history if t["transaction_id"] == relevant_txn_id), None)
    if not txn:
        return "insufficient_data"

    complaint_lower = complaint.lower()

    if case_type == "wrong_transfer":
        counterparty = txn.get("counterparty", "")
        same_counterparty_count = sum(
            1 for t in transaction_history if t.get("counterparty") == counterparty
        )
        if same_counterparty_count >= 3:
            return "inconsistent"

    if case_type == "payment_failed" and txn.get("status") == "completed":
        if any(w in complaint_lower for w in ["failed", "not received", "didn't go through"]):
            return "inconsistent"

    if txn.get("status") == "failed" and case_type == "payment_failed":
        return "consistent"
    if txn.get("status") == "pending" and case_type in ["agent_cash_in_issue", "merchant_settlement_delay"]:
        return "consistent"
    if txn.get("status") == "completed" and case_type == "wrong_transfer":
        return "consistent"
    if txn.get("status") == "completed" and case_type == "duplicate_payment":
        return "consistent"
    if txn.get("status") == "completed" and case_type == "refund_request":
        return "consistent"

    return "consistent"


def check_duplicate_payment(transaction_history: list) -> Optional[str]:
    payments = [t for t in transaction_history if t.get("type") == "payment"]
    for i in range(len(payments)):
        for j in range(i + 1, len(payments)):
            a, b = payments[i], payments[j]
            if (
                a.get("amount") == b.get("amount") and
                a.get("counterparty") == b.get("counterparty") and
                a.get("status") == "completed" and
                b.get("status") == "completed"
            ):
                try:
                    ta = datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00"))
                    tb = datetime.fromisoformat(b["timestamp"].replace("Z", "+00:00"))
                    diff = abs((tb - ta).total_seconds())
                    if diff < 120:
                        return b["transaction_id"] if tb > ta else a["transaction_id"]
                except Exception:
                    pass
    return None


def detect_language(text: str) -> str:
    bangla_chars = sum(1 for c in text if '\u0980' <= c <= '\u09FF')
    total_alpha = sum(1 for c in text if c.isalpha())
    if total_alpha == 0:
        return "en"
    bangla_ratio = bangla_chars / total_alpha
    if bangla_ratio > 0.6:
        return "bn"
    elif bangla_ratio > 0.1:
        return "mixed"
    return "en"


def analyze(ticket: dict) -> dict:
    complaint = ticket.get("complaint", "")
    transaction_history = ticket.get("transaction_history") or []

    case_type = classify_case_type(complaint)

    if case_type == "duplicate_payment":
        dup_id = check_duplicate_payment(transaction_history)
        relevant_txn_id = dup_id if dup_id else find_relevant_transaction(complaint, transaction_history)
    else:
        relevant_txn_id = find_relevant_transaction(complaint, transaction_history)

    evidence_verdict = compute_evidence_verdict(complaint, transaction_history, relevant_txn_id, case_type)

    severity = SEVERITY_MAP.get(case_type, "low")
    department = DEPARTMENT_MAP.get(case_type, "customer_support")

    human_review = HUMAN_REVIEW_MAP.get(case_type, False)
    if evidence_verdict == "inconsistent" or severity == "critical":
        human_review = True

    return {
        "case_type": case_type,
        "relevant_transaction_id": relevant_txn_id,
        "evidence_verdict": evidence_verdict,
        "severity": severity,
        "department": department,
        "human_review_required": human_review,
    }