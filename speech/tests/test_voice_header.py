"""The camera board's embedded voice clips (voice_clips.h) must stay in step with speech/audio/*.wav."""
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("miniaudio")

TOOL = Path(__file__).resolve().parents[2] / "firmware" / "esp32_arduino_ide" / "tools" / "make_voice_header.py"
spec = importlib.util.spec_from_file_location("make_voice_header", TOOL)
mvh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mvh)


def test_mulaw_roundtrip_error_is_small():
    import numpy as np

    t = np.arange(0, 16000) / 16000.0
    sig = (12000 * np.sin(2 * np.pi * 440 * t)).astype(int)
    back = np.array([mvh.ulaw2lin(mvh.lin2ulaw(int(s))) for s in sig])
    snr = 10 * np.log10((sig.astype(float) ** 2).mean() / ((sig - back).astype(float) ** 2).mean())
    assert snr > 30


def test_mulaw_reference_values():
    # standard G.711: 0xFF/0x7F are zero, 0x80/0x00 are the positive/negative maximum
    assert mvh.ulaw2lin(0xFF) == 0 and mvh.ulaw2lin(0x7F) == 0
    assert mvh.ulaw2lin(0x80) == 32124 and mvh.ulaw2lin(0x00) == -32124


def test_generated_header_is_up_to_date():
    current = mvh.OUT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert current == mvh.build(), "voice_clips.h is stale: run firmware/esp32_arduino_ide/tools/make_voice_header.py"
