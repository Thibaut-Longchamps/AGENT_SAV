SUSPICIOUS_PATTERNS = (
    "ignore all previous instructions",
    "ignore previous instructions",
    "system prompt",
    "reveal your prompt",
    "refund the customer immediately",
)


def detect_prompt_injection(text: str) -> list[str]:
    """Return the suspicious patterns found in an untrusted document."""
    normalized = text.casefold()
    return [pattern for pattern in SUSPICIOUS_PATTERNS if pattern in normalized]
