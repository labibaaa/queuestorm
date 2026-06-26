import re

# Words/phrases that must NEVER appear in customer_reply
FORBIDDEN_CREDENTIAL_PHRASES = [
    "your pin", "enter your pin", "share your pin",
    "your otp", "enter your otp", "provide your otp", "share your otp",
    "your password", "enter your password",
    "card number", "full card", "cvv",
    "send your pin", "give us your pin",
]

FORBIDDEN_PROMISE_PHRASES = [
    "we will refund", "you will get a refund", "we'll refund",
    "your money will be returned", "we will reverse",
    "your account will be unblocked", "we will unblock",
    "guaranteed refund", "refund has been approved",
    "we will recover", "money will be back",
]


def scrub_customer_reply(reply: str) -> str:
    """
    Post-process LLM output to catch and neutralize safety violations.
    """
    reply_lower = reply.lower()

    for phrase in FORBIDDEN_CREDENTIAL_PHRASES:
        if phrase in reply_lower:
            # Remove the sentence containing it
            reply = re.sub(
                r'[^.!?]*' + re.escape(phrase) + r'[^.!?]*[.!?]',
                '',
                reply,
                flags=re.IGNORECASE
            ).strip()

    for phrase in FORBIDDEN_PROMISE_PHRASES:
        if phrase in reply_lower:
            reply = reply.replace(
                phrase,
                "any eligible amount will be returned through official channels",
            )
            # Case-insensitive replace
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            reply = pattern.sub(
                "any eligible amount will be returned through official channels",
                reply
            )

    return reply


def validate_safety(customer_reply: str, recommended_next_action: str) -> list:
    """
    Returns list of violation types found. Empty = safe.
    """
    violations = []
    reply_lower = customer_reply.lower()
    action_lower = recommended_next_action.lower()

    for phrase in FORBIDDEN_CREDENTIAL_PHRASES:
        if phrase in reply_lower:
            violations.append("credential_request")
            break

    for phrase in FORBIDDEN_PROMISE_PHRASES:
        if phrase in reply_lower or phrase in action_lower:
            violations.append("unauthorized_promise")
            break

    return violations