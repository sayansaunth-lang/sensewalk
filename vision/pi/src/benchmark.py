#!/usr/bin/env python3
"""Measure how fast the AI models actually run on THIS machine. Run it on the Pi.

The speed figures in the project report were measured on a laptop. A Raspberry Pi 3B
is much slower, and guessing is how projects end up with a demo that stutters. This
prints real numbers, with no screen or camera needed, and suggests a
--process-every-n-frames value for main.py.

    python3 vision/pi/src/benchmark.py
    python3 vision/pi/src/benchmark.py --width 320 --height 240 --runs 50
    python3 vision/pi/src/benchmark.py --image some_photo.jpg
    python3 vision/pi/src/benchmark.py --soak-seconds 600      # heat test: watch temperature / throttling

Report the numbers it prints, including when they are disappointing. That is the honest result.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, math.ceil(pct / 100 * len(ordered)) - 1))
    return ordered[k]


def time_calls(fn: Callable[[], object], runs: int, warmup: int = 3) -> dict:
    """Call fn() `warmup` times (ignored: the first calls are slow while buffers and
    caches fill) then `runs` times, returning timing statistics in milliseconds."""
    if runs < 1:
        raise ValueError("runs must be >= 1")
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    mean = statistics.fmean(samples)
    return {
        "runs": runs,
        "mean_ms": round(mean, 1),
        "median_ms": round(statistics.median(samples), 1),
        "p95_ms": round(percentile(samples, 95), 1),
        "min_ms": round(min(samples), 1),
        "max_ms": round(max(samples), 1),
        "fps": round(1000.0 / mean, 2) if mean > 0 else float("inf"),
    }


def suggest_every_n(total_ms_per_inference: float, camera_fps: float = 15.0) -> int:
    """How many camera frames to skip between inferences so processing keeps up.
    If one full inference (all models) takes 600 ms the Pi can do ~1.7 per second;
    a 15 fps camera therefore needs every ~9th frame processed."""
    if total_ms_per_inference <= 0:
        return 1
    capacity_per_s = 1000.0 / total_ms_per_inference
    return max(1, math.ceil(camera_fps / capacity_per_s))


def read_cpu_temp_c() -> Optional[float]:
    try:
        return int(Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()) / 1000.0
    except (OSError, ValueError):
        return None


def parse_throttled(output: str) -> Optional[dict]:
    """Parse `vcgencmd get_throttled` ("throttled=0x50005"). Bit 2 = currently throttled,
    bit 0 = under-voltage now, bit 16/18 = it happened since boot."""
    if "=" not in output:
        return None
    try:
        value = int(output.strip().split("=", 1)[1], 16)
    except ValueError:
        return None
    return {
        "raw": hex(value),
        "under_voltage_now": bool(value & 0x1),
        "throttled_now": bool(value & 0x4),
        "under_voltage_since_boot": bool(value & 0x10000),
        "throttled_since_boot": bool(value & 0x40000),
    }


def read_throttled() -> Optional[dict]:
    try:
        out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_throttled(out)


def make_frame(width: int, height: int, image_path: Optional[str] = None):
    import cv2
    import numpy as np

    if image_path:
        img = cv2.imread(image_path)
        if img is None:
            raise SystemExit(f"could not read image: {image_path}")
        return cv2.resize(img, (width, height))
    # A structured synthetic frame: gradients and rectangles give the detectors realistic work to do.
    frame = np.zeros((height, width, 3), np.uint8)
    frame[:] = np.linspace(40, 200, width, dtype=np.uint8)[None, :, None]
    for i in range(8):
        x, y = (i * 53) % max(1, width - 60), (i * 37) % max(1, height - 40)
        cv2.rectangle(frame, (x, y), (x + 60, y + 40), (30 + i * 25, 200 - i * 20, 90), -1)
    return frame


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--height", type=int, default=240)
    ap.add_argument("--runs", type=int, default=30, help="timed inferences per model")
    ap.add_argument("--image", default=None, help="use a real photo instead of a synthetic frame")
    ap.add_argument("--camera-fps", type=float, default=15.0, help="camera frame rate, for the suggestion")
    ap.add_argument("--soak-seconds", type=float, default=0.0, help="afterwards run both models flat-out this long and report temperature")
    ap.add_argument("--json-out", default=None, help="also write results to this JSON file")
    args = ap.parse_args()

    from vision.pi.src.detector import TFLiteSSDDetector, YoloOnnxDetector

    frame = make_frame(args.width, args.height, args.image)
    print(f"frame {args.width}x{args.height} ({'photo' if args.image else 'synthetic'}), {args.runs} timed runs per model\n")

    detectors: dict[str, object] = {}
    for name, factory in (("people/objects (TFLite)", TFLiteSSDDetector), ("pothole (ONNX)", YoloOnnxDetector)):
        try:
            detectors[name] = factory()
        except Exception as exc:  # missing model file, missing runtime, old OpenCV...
            print(f"SKIPPED {name}: {exc}")

    if not detectors:
        print("\nNo model could be loaded; nothing to measure. Run scripts/pi_setup.sh first.")
        return 1

    temp_start = read_cpu_temp_c()
    results: dict[str, dict] = {}
    for name, det in detectors.items():
        results[name] = time_calls(lambda d=det: d.detect(frame), args.runs)

    print(f"{'model':26} {'mean':>8} {'median':>8} {'p95':>8} {'max':>8} {'fps':>7}")
    for name, r in results.items():
        print(f"{name:26} {r['mean_ms']:>6.0f}ms {r['median_ms']:>6.0f}ms {r['p95_ms']:>6.0f}ms {r['max_ms']:>6.0f}ms {r['fps']:>7.2f}")

    total_ms = sum(r["mean_ms"] for r in results.values())
    n = suggest_every_n(total_ms, args.camera_fps)
    print(f"\nOne full inference (all loaded models) takes about {total_ms:.0f} ms.")
    print(f"Suggested flag for a {args.camera_fps:.0f} fps camera:  --process-every-n-frames {n}")

    summary: dict = {"frame": [args.width, args.height], "models": results, "total_ms": round(total_ms, 1), "suggested_every_n": n}

    temp_end = read_cpu_temp_c()
    if temp_start is not None:
        print(f"CPU temperature: {temp_start:.0f} C before, {temp_end:.0f} C after")
        summary["temp_c"] = {"before": temp_start, "after": temp_end}

    if args.soak_seconds > 0:
        print(f"\nSoak test: running flat-out for {args.soak_seconds:.0f} s ...")
        end = time.monotonic() + args.soak_seconds
        count, peak = 0, temp_end or 0.0
        while time.monotonic() < end:
            for det in detectors.values():
                det.detect(frame)
            count += 1
            t = read_cpu_temp_c()
            if t is not None:
                peak = max(peak, t)
        print(f"{count} full inferences in {args.soak_seconds:.0f} s, peak CPU temperature {peak:.0f} C")
        summary["soak"] = {"seconds": args.soak_seconds, "inferences": count, "peak_temp_c": peak}

    thr = read_throttled()
    if thr is not None:
        summary["throttling"] = thr
        flag = "YES - the speed above is being limited" if thr["throttled_now"] or thr["throttled_since_boot"] else "no"
        print(f"Throttled by heat/power: {flag}   (under-voltage: {'YES - check the power supply' if thr['under_voltage_since_boot'] else 'no'})")

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(summary, indent=2))
        print(f"saved {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
