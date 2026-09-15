"""Deterministic medical-safety guardrails applied before and after AI calls."""

import re


MEDICAL_DISCLAIMER = (
    "**Medical safety note:** This is general health information, not a diagnosis "
    "or a substitute for care from a qualified clinician. Do not start, stop, or "
    "change medicines or treatment based only on this response."
)

URGENT_CARE_MESSAGE = (
    "**Seek urgent medical care now.** Your message may describe an emergency. "
    "Call your local emergency number or go to the nearest emergency department. "
    "Do not wait for an AI assessment or try to manage severe symptoms on your own."
)

_URGENT_PATTERNS = (
    r"\b(chest pain|chest pressure|crushing chest)\b",
    r"\b(trouble breathing|difficulty breathing|cannot breathe|can'?t breathe|severe shortness of breath)\b",
    r"\b(face droop|slurred speech|one[- ]sided weakness|sudden weakness)\b",
    r"\b(unconscious|passed out|fainted|unresponsive)\b",
    r"\b(seizure|convulsion)\b",
    r"\b(severe bleeding|bleeding won'?t stop|vomiting blood|coughing blood)\b",
    r"\b(overdose|poisoned|poisoning)\b",
    r"\b(suicidal|kill myself|end my life|self[- ]harm)\b",
)


def needs_urgent_care(message):
    """Return whether a message contains a clear, high-risk red flag."""
    if not isinstance(message, str):
        return False
    return any(re.search(pattern, message, flags=re.IGNORECASE) for pattern in _URGENT_PATTERNS)


def urgent_care_response(message):
    """Return fixed emergency guidance without sending sensitive text to an LLM."""
    if needs_urgent_care(message):
        return URGENT_CARE_MESSAGE
    return None


def add_medical_disclaimer(response):
    """Attach the standard boundary once to a normal AI-generated response."""
    if not isinstance(response, str) or not response.strip():
        return response
    normalized_response = response.lower().replace("**", "")
    if "medical safety note:" in normalized_response:
        return response
    return f"{response.rstrip()}\n\n---\n{MEDICAL_DISCLAIMER}"
