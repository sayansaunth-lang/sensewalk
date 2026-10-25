"""Pre-recorded voice clips for the alert phrases.

If a clip exists for a phrase key it is played instead of the synthesised voice (the same sound
every time, instantly, with no text-to-speech engine needed). A phrase with no clip, or a clip that
fails to play, falls back to the text-to-speech in tts.py, so an alert is never silent just because
an audio file or player is missing.

The clips are in speech/audio/ (WAV, mono, 22.05 kHz). To change a clip, replace the file; to
assign a clip to another phrase, edit CLIP_FOR_PHRASE. See speech/audio/README.md.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path
from typing import Optional

AUDIO_DIR = Path(__file__).resolve().parent / "audio"

# phrase key (speech/phrases.py) -> clip file in speech/audio/
CLIP_FOR_PHRASE: dict[str, str] = {
    "pothole_ahead": "pothole_detected.wav",        # "Alert. Pothole detected ahead. Reduce speed."
    "ground_hazard_seen": "pothole_detected.wav",   # same clip: the vision model's ground hazard is a pothole
    "obstacle_close": "obstacle_warning.wav",       # "Warning, obstacle detected ahead. Slow down."
    "brake_released": "road_clear.wav",             # "Road ahead is clear."
    "vehicle_ahead": "vehicle_ahead.wav",           # "Caution. Vehicle detected ahead. Maintain safe distance."
    "traffic_ahead": "traffic_ahead.wav",           # "Traffic ahead. Drive carefully."
}


def load_clips(audio_dir: Path = AUDIO_DIR) -> dict[str, Path]:
    """Phrase key -> existing clip path. Keys whose file is missing are left out (TTS covers them)."""
    clips: dict[str, Path] = {}
    for key, filename in CLIP_FOR_PHRASE.items():
        path = audio_dir / filename
        if path.is_file():
            clips[key] = path
    return clips


class ClipPlayer:
    """Plays clips in the background so the vision loop never waits for a 4-5 second sentence.

    One clip at a time. A new clip is dropped if something at least as urgent is still playing, and
    interrupts it if it is more urgent (an obstacle warning cuts off "road ahead is clear").
    """

    def __init__(self) -> None:
        self._handle = None
        self._busy_until = 0.0
        self._severity = 0

    # -- platform backends (overridden in tests) --
    def _start(self, path: Path):
        """Start playing without blocking. Returns a handle for _stop(), or None if impossible."""
        if sys.platform.startswith("win"):
            import winsound

            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            return "winsound"
        if sys.platform == "darwin":
            cmd = ["afplay", str(path)]
        else:
            player = shutil.which("aplay") or shutil.which("paplay")
            if player is None:
                return None
            cmd = [player, "-q", str(path)] if player.endswith("aplay") else [player, str(path)]
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _stop(self, handle) -> None:
        if handle == "winsound":
            import winsound

            winsound.PlaySound(None, winsound.SND_PURGE)
        elif handle is not None:
            try:
                handle.terminate()
            except Exception:
                pass

    @staticmethod
    def _duration_s(path: Path) -> float:
        try:
            with wave.open(str(path), "rb") as w:
                return w.getnframes() / float(w.getframerate())
        except Exception:
            return 5.0

    def play(self, path: Path, severity: int = 0, now: Optional[float] = None) -> bool:
        """True if the clip started or was deliberately skipped for a more urgent one that is still
        playing. False only if playback is impossible, so the caller can fall back to text-to-speech."""
        now = time.monotonic() if now is None else now
        if now < self._busy_until:
            if severity <= self._severity:
                return True  # something at least as urgent is already speaking
            self._stop(self._handle)
        try:
            handle = self._start(path)
        except Exception:
            return False
        if handle is None:
            return False
        self._handle = handle
        self._severity = severity
        self._busy_until = now + self._duration_s(path)
        return True


_PLAYER = ClipPlayer()


def play_clip(path: Path, severity: int = 0) -> bool:
    return _PLAYER.play(path, severity)


def describe(clips: dict[str, Path]) -> Optional[str]:
    return ", ".join(sorted(clips)) if clips else None
