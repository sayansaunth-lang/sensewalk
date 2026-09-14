#!/usr/bin/env python3
"""Live sensor dashboard + ground-truth-labeled CSV logger for bench/field
calibration sessions.

This is the tool that turns the learning roadmap's B2/D2 deliverables
("a logged CSV of at least 50 real test walks... with false-positive and
false-negative count calculated from it") from a description into
something the team actually runs. Connect the Pi to the ESP32 over UART,
run this during a walk, press a key to mark ground truth the instant a
hazard is physically present, and get a CSV that
test/analyze_detection_log.py can immediately consume.

Usage:
    python3 test/bench_logger.py --port /dev/serial0 --scenario pothole_15cm

While running:
    press 'h' + Enter   mark ground_truth_hazard=1 starting now
    press 'c' + Enter   clear it (ground_truth_hazard=0)
    press 'q' + Enter   stop and write the CSV

Output schema matches test/README.md's "ground/obstacle detection log":
    timestamp,scenario,tof_gnd_mm,tof_gnd_baseline_mm,detected_hazard,ground_truth_hazard
"""
from __future__ import annotations

import argparse
import csv
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comms.python.serial_link import SerialLink  # noqa: E402
from fusion.state_machine import GROUND_DROPOFF_MM  # noqa: E402


class BenchLogger:
    def __init__(self, port: str, scenario: str, baud: int = 115200) -> None:
        self.scenario = scenario
        self.rows: list[dict] = []
        self.ground_truth_hazard = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()

        self._tof_gnd_mm = 0
        self._tof_gnd_baseline_mm = 0

        self.link = SerialLink(port, baud=baud)
        self.link.on_message("tof_gnd", self._on_tof_gnd)

    def _on_tof_gnd(self, msg) -> None:
        with self._lock:
            self._tof_gnd_mm = msg.int_value()
            # Same rolling-baseline approach as fusion/state_machine.py
            # would see via firmware's tracked baseline — approximated
            # here client-side for standalone bench logging.
            if self._tof_gnd_baseline_mm == 0:
                self._tof_gnd_baseline_mm = self._tof_gnd_mm
            else:
                self._tof_gnd_baseline_mm = int(
                    (self._tof_gnd_baseline_mm * 15 + self._tof_gnd_mm) / 16
                )
            detected = int((self._tof_gnd_mm - self._tof_gnd_baseline_mm) > GROUND_DROPOFF_MM)
            self.rows.append(
                {
                    "timestamp": time.time(),
                    "scenario": self.scenario,
                    "tof_gnd_mm": self._tof_gnd_mm,
                    "tof_gnd_baseline_mm": self._tof_gnd_baseline_mm,
                    "detected_hazard": detected,
                    "ground_truth_hazard": self.ground_truth_hazard,
                }
            )

    def _input_loop(self) -> None:
        while not self._stop.is_set():
            try:
                cmd = input().strip().lower()
            except EOFError:
                break
            if cmd == "h":
                self.ground_truth_hazard = 1
                print(">>> ground truth: HAZARD marked ON")
            elif cmd == "c":
                self.ground_truth_hazard = 0
                print(">>> ground truth: hazard cleared")
            elif cmd == "q":
                self._stop.set()

    def run(self) -> None:
        self.link.open()
        input_thread = threading.Thread(target=self._input_loop, daemon=True)
        input_thread.start()

        print(f"Bench logger running for scenario={self.scenario!r}. Commands: h=mark hazard, c=clear, q=quit")
        last_print = 0.0
        while not self._stop.is_set():
            self.link.poll()
            now = time.monotonic()
            if now - last_print > 0.5:
                last_print = now
                with self._lock:
                    truth_label = "HAZARD" if self.ground_truth_hazard else "clear"
                    print(
                        f"\rtof_gnd={self._tof_gnd_mm:5d}mm  baseline={self._tof_gnd_baseline_mm:5d}mm  "
                        f"ground_truth={truth_label:7s}  rows={len(self.rows):4d}",
                        end="",
                        flush=True,
                    )
            time.sleep(0.02)

        self.link.close()
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", default="/dev/serial0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--scenario", required=True, help="e.g. pothole_15cm, flat_ground, curb_step")
    parser.add_argument("--out", default=None, help="CSV output path (default: test/logs/bench_<scenario>_<ts>.csv)")
    args = parser.parse_args()

    out_path = (
        Path(args.out)
        if args.out
        else Path(__file__).resolve().parent / "logs" / f"bench_{args.scenario}_{int(time.time())}.csv"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger = BenchLogger(args.port, args.scenario, baud=args.baud)
    logger.run()

    with out_path.open("w", newline="") as f:
        fieldnames = ["timestamp", "scenario", "tof_gnd_mm", "tof_gnd_baseline_mm", "detected_hazard", "ground_truth_hazard"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(logger.rows)

    print(f"Wrote {len(logger.rows)} rows to {out_path}")
    print(f"Analyze with: python3 test/analyze_detection_log.py {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
