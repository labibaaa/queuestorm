import time
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("queuestorm")

_stats = defaultdict(int)
_latencies = []

def log_request(ticket_id: str, case_type: str, latency_ms: float, success: bool):
    _stats["total"] += 1
    _stats[f"case_{case_type}"] += 1
    if not success:
        _stats["errors"] += 1
    _latencies.append(latency_ms)
    logger.info(f"[{ticket_id}] case={case_type} latency={latency_ms:.0f}ms success={success}")

def get_stats() -> dict:
    p95 = sorted(_latencies)[int(len(_latencies) * 0.95)] if _latencies else 0
    return {
        "total_requests": _stats["total"],
        "error_count": _stats["errors"],
        "p95_latency_ms": round(p95, 2),
        "case_distribution": {k: v for k, v in _stats.items() if k.startswith("case_")},
    }