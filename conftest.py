"""Ensures the repo root is importable as the base for the fusion/, speech/,
comms/python/, and vision/pi/src/ packages regardless of how pytest is
invoked (plain `pytest`, `python -m pytest`, or from CI)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
