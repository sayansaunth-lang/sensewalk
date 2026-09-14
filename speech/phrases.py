"""Fixed alert-phrase vocabulary (E1 in the learning roadmap).

Short, fixed phrases instead of generated sentences — this keeps
trigger-to-sound latency low and predictable, which matters for a hazard
alert. Keys here are what fusion/state_machine.py's Decision.alert_phrase_key
points at; keep the two in sync.

Severity drives both the buzzer fallback pattern (speech/buzzer_fallback.py)
and which phrase wins if two would otherwise fire close together.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Severity(IntEnum):
    INFO = 1
    WARNING = 2
    CRITICAL = 3


@dataclass(frozen=True)
class Phrase:
    key: str
    text: str
    severity: Severity


# Ordered roughly by how often they should fire in practice — most common
# nominal-warning phrases first, most severe last for readability.
VOCABULARY: dict[str, Phrase] = {
    "sign_read": Phrase("sign_read", "{text}", Severity.INFO),
    "person_close": Phrase("person_close", "Person close ahead", Severity.WARNING),
    "obstacle_close": Phrase("obstacle_close", "Obstacle close, stopping", Severity.CRITICAL),
    "pothole_ahead": Phrase("pothole_ahead", "Pothole ahead, stopping", Severity.CRITICAL),
    "fall_alert": Phrase("fall_alert", "Fall detected, sending alert", Severity.CRITICAL),
    "brake_released": Phrase("brake_released", "Clear, walking", Severity.INFO),
}


def render(key: str, **kwargs) -> str:
    """Format a phrase for speaking. OCR's sign_read phrase takes `text=`
    (the OCR'd string) — every other phrase ignores kwargs entirely, so it's
    always safe to call render(key, text=snapshot.ocr_text)."""
    phrase = VOCABULARY.get(key)
    if phrase is None:
        raise KeyError(f"unknown alert phrase key: {key!r}")
    return phrase.text.format(**kwargs) if "{" in phrase.text else phrase.text


def severity_of(key: str) -> Severity:
    phrase = VOCABULARY.get(key)
    if phrase is None:
        raise KeyError(f"unknown alert phrase key: {key!r}")
    return phrase.severity
