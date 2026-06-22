"""
PII Redaction layer for ParaIQ.
Call redact_text(text) before any string enters claude_with_retry().
Returns (redacted_text, redaction_map) where the map lets you restore
originals server-side if needed for logging/display.
"""

import re
import uuid
from typing import Tuple, Dict

# ── Patterns ──────────────────────────────────────────────────────────────────
# Order matters: more-specific patterns before catch-alls.

_PATTERNS = [
    # SSN  123-45-6789 or 123456789
    ("SSN",        re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")),
    # EIN  12-3456789
    ("EIN",        re.compile(r"\b\d{2}-\d{7}\b")),
    # Credit card  4-4-4-4 or 16 digits
    ("CC",         re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    # Phone  (800) 555-1234 / 800-555-1234 / +1 800 555 1234
    ("PHONE",      re.compile(r"(?:\+?1[-\s.]?)?(?:\(?\d{3}\)?[-\s.]?)\d{3}[-\s.]\d{4}")),
    # Email
    ("EMAIL",      re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")),
    # Date of birth  DOB: MM/DD/YYYY or DOB: YYYY-MM-DD
    ("DOB",        re.compile(r"(?:DOB|Date of Birth|birth(?:date|day)?)[:\s]+\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", re.IGNORECASE)),
    # IP address
    ("IP",         re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    # DL / passport  broad pattern for "DL#: A12345678"
    ("ID_NUM",     re.compile(r"(?:DL|Driver.?License|Passport|License)\s*[:#\s]\s*[A-Z0-9]{6,15}", re.IGNORECASE)),
]


def redact_text(text: str) -> Tuple[str, Dict[str, str]]:
    """
    Replace PII in text with reversible tokens.
    Returns (redacted, mapping) where mapping[token] = original.
    """
    if not text:
        return text, {}

    redaction_map: Dict[str, str] = {}

    for label, pattern in _PATTERNS:
        def _replace(m, lbl=label):
            token = f"[{lbl}_{uuid.uuid4().hex[:8].upper()}]"
            redaction_map[token] = m.group(0)
            return token
        text = pattern.sub(_replace, text)

    return text, redaction_map


def restore_text(text: str, redaction_map: Dict[str, str]) -> str:
    """Reverse redaction using the map returned by redact_text()."""
    for token, original in redaction_map.items():
        text = text.replace(token, original)
    return text


def redaction_summary(redaction_map: Dict[str, str]) -> Dict[str, int]:
    """Return counts by PII type for audit logging."""
    counts: Dict[str, int] = {}
    for token in redaction_map:
        label = token.lstrip("[").split("_")[0]
        counts[label] = counts.get(label, 0) + 1
    return counts
