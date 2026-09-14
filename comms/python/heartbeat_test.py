#!/usr/bin/env python3
"""D1 validation script (learning roadmap): confirm the ESP32<->Pi UART link
is solid BEFORE any real sensor data flows through it.

Sends nothing itself — the ESP32 side is expected to already be emitting
`heartbeat` messages every 200ms (this is firmware's default idle behavior,
see firmware/esp32/src/comms/uart_link.h). This script just listens, counts
drops/gaps/corruption, and writes a CSV log for the test/ record.

Usage:
    python3 comms/python/heartbeat_test.py --port /dev/serial0 --count 1000
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from comms.python.serial_link import SerialLink  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/serial0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--count", type=int, default=1000, help="messages to collect before stopping")
    parser.add_argument("--timeout-s", type=float, default=120.0, help="give up after this many seconds")
    parser.add_argument(
        "--out",
        default=None,
        help="CSV output path (default: test/logs/heartbeat_<timestamp>.csv)",
    )
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else Path(__file__).resolve().parents[2] / "test" / "logs" / f"heartbeat_{int(time.time())}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    link = SerialLink(args.port, baud=args.baud)
    rows: list[dict] = []

    def record(msg) -> None:
        rows.append({"seq": msg.seq, "value_ms": msg.int_value(), "t_wall": time.time()})

    link.on_message("heartbeat", record)
    link.open()
    print(f"Listening on {args.port} @ {args.baud} baud for {args.count} heartbeat messages...")

    start = time.monotonic()
    try:
        while len(rows) < args.count and (time.monotonic() - start) < args.timeout_s:
            link.poll()
    finally:
        link.close()

    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["seq", "value_ms", "t_wall"])
        writer.writeheader()
        writer.writerows(rows)

    stats = link.stats
    total_gaps = sum(stats.gaps_by_tag.values())
    print(f"\nCollected {len(rows)} heartbeat messages -> {out_path}")
    print(f"  ok:                 {stats.messages_ok}")
    print(f"  dropped (checksum): {stats.messages_dropped_checksum}")
    print(f"  dropped (malformed):{stats.messages_dropped_malformed}")
    print(f"  sequence gaps:      {total_gaps}")

    passed = len(rows) >= args.count and total_gaps == 0 and stats.messages_dropped_checksum == 0
    print("RESULT:", "PASS" if passed else "FAIL — investigate wiring/baud/grounding before proceeding")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
