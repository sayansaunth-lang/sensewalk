"""Offline text-to-speech (E1 in the learning roadmap).

pyttsx3 wraps eSpeak (Linux/Pi) or SAPI5 (Windows) — fully offline, no
network dependency, which matters for a hazard alert that must work with
zero internet connectivity. Import is lazy so the rest of the codebase
(fusion, vision logic) can be imported/tested on a machine without pyttsx3
or a working audio device.
"""
from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import phrases


@dataclass
class LatencyRecord:
    phrase_key: str
    trigger_to_sound_ms: float


class AlertSpeaker:
    """Speaks alert phrases from the fixed vocabulary. Falls back to a
    no-op (logged, not raised) if pyttsx3 or the audio device isn't
    available, so a bench test without speakers attached doesn't crash the
    whole pipeline — the piezo buzzer fallback (buzzer_fallback.py) is the
    real hard fallback for that case."""

    def __init__(self, rate: int = 175) -> None:
        self._engine = None
        self._rate = rate
        self._last_spoken_at: dict[str, float] = {}
        self.latency_log: list[LatencyRecord] = []
        try:
            import pyttsx3

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", rate)
        except Exception as exc:  # pragma: no cover - depends on host audio stack
            print(f"[speech.tts] pyttsx3 unavailable ({exc}); running with speech disabled")

    @property
    def available(self) -> bool:
        return self._engine is not None

    def speak(self, phrase_key: str, min_repeat_interval_s: float = 3.0, **kwargs) -> Optional[LatencyRecord]:
        """Speak a phrase by vocabulary key. Repeats of the same key within
        min_repeat_interval_s are suppressed so a sustained hazard doesn't
        spam the same sentence every frame."""
        last = self._last_spoken_at.get(phrase_key)
        now = time.monotonic()
        if last is not None and (now - last) < min_repeat_interval_s:
            return None
        self._last_spoken_at[phrase_key] = now

        text = phrases.render(phrase_key, **kwargs)
        trigger_time = time.monotonic()

        if self._engine is None:
            print(f"[speech.tts] (disabled) would say: {text!r}")
            return None

        self._engine.say(text)
        self._engine.runAndWait()
        latency_ms = (time.monotonic() - trigger_time) * 1000

        record = LatencyRecord(phrase_key=phrase_key, trigger_to_sound_ms=latency_ms)
        self.latency_log.append(record)
        return record

    def write_latency_log(self, path: Path) -> None:
        """E1 deliverable: a measured latency table for at least 5 alert
        phrases. Call after a bench session covering the whole vocabulary."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["phrase_key", "trigger_to_sound_ms"])
            for record in self.latency_log:
                writer.writerow([record.phrase_key, f"{record.trigger_to_sound_ms:.1f}"])
