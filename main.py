import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Any
from reasoning import analyze, detect_language
from monitor import log_request, get_stats
from llm import generate_text_fields
from safety import scrub_customer_reply, validate_safety
import time

app = FastAPI()

class TicketRequest(BaseModel):
    ticket_id: str
    complaint: str
    language: Optional[str] = None
    transaction_history: Optional[List[Any]] = []

INJECTION_PATTERNS = [
    "ignore previous instructions",
    "disregard your instructions",
    "you are now",
    "pretend you are",
    "forget your instructions",
]

def sanitize_complaint(text: str):
    lowered = text.lower()
    for pattern in INJECTION_PATTERNS:
        if pattern in lowered:
            return text[:200], True
    return text, False


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def stats():
    return get_stats()


@app.post("/analyze-ticket")
async def analyze_ticket(body_model: TicketRequest):
    body = body_model.dict()

    ticket_id = body.get("ticket_id")
    complaint = body.get("complaint")

    if not isinstance(complaint, str) or complaint.strip() == "":
        return JSONResponse(status_code=422, content={"error": "complaint must be a non-empty string."})

    start = time.time()

    complaint, injection_detected = sanitize_complaint(complaint)
    language = body.get("language") or detect_language(complaint)
    transaction_history = body.get("transaction_history") or []

    reasoning = analyze(body)

    text_fields = generate_text_fields(
        complaint=complaint,
        case_type=reasoning["case_type"],
        evidence_verdict=reasoning["evidence_verdict"],
        relevant_transaction_id=reasoning["relevant_transaction_id"],
        department=reasoning["department"],
        severity=reasoning["severity"],
        language=language,
    )

    safe_reply = scrub_customer_reply(text_fields["customer_reply"])
    safe_action = text_fields["recommended_next_action"]

    confidence_map = {
        "consistent": 0.88,
        "inconsistent": 0.75,
        "insufficient_data": 0.55,
    }

    latency = (time.time() - start) * 1000
    log_request(ticket_id, reasoning["case_type"], latency, True)

    response = {
        "ticket_id": ticket_id,
        "relevant_transaction_id": reasoning["relevant_transaction_id"],
        "evidence_verdict": reasoning["evidence_verdict"],
        "case_type": reasoning["case_type"],
        "severity": reasoning["severity"],
        "department": reasoning["department"],
        "agent_summary": text_fields["agent_summary"],
        "recommended_next_action": safe_action,
        "customer_reply": safe_reply,
        "human_review_required": reasoning["human_review_required"],
        "confidence": confidence_map.get(reasoning["evidence_verdict"], 0.7),
        "reason_codes": [reasoning["case_type"], reasoning["evidence_verdict"]],
    }

    return JSONResponse(status_code=200, content=response)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "Internal server error. Please try again."})


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)