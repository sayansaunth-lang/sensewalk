#!/usr/bin/env python3
"""Computes false-positive/false-negative rates from a logged hazard
detection CSV (B2 deliverable in the learning roadmap): "a logged CSV of at
least 50 real test walks over a known pothole/curb and 50 walks over flat
ground, with your detection rule's false-positive and false-negative count
calculated from it."

Expected CSV columns (extra columns are ignored):
    detected_hazard,ground_truth_hazard   (each 0 or 1)

Usage:
    python3 test/analyze_detection_log.py test/logs/detection_log.csv
    python3 test/analyze_detection_log.py test/logs/detection_log.csv --by-column scenario
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class ConfusionCounts:
    true_positive: int = 0
    true_negative: int = 0
    false_positive: int = 0
    false_negative: int = 0

    @property
    def total(self) -> int:
        return self.true_positive + self.true_negative + self.false_positive + self.false_negative

    @property
    def false_positive_rate(self) -> float:
        negatives = self.true_negative + self.false_positive
        return self.false_positive / negatives if negatives else 0.0

    @property
    def false_negative_rate(self) -> float:
        positives = self.true_positive + self.false_negative
        return self.false_negative / positives if positives else 0.0

    @property
    def accuracy(self) -> float:
        return (self.true_positive + self.true_negative) / self.total if self.total else 0.0

    def add(self, detected: bool, truth: bool) -> None:
        if detected and truth:
            self.true_positive += 1
        elif not detected and not truth:
            self.true_negative += 1
        elif detected and not truth:
            self.false_positive += 1
        else:
            self.false_negative += 1

    def print_report(self, label: str) -> None:
        print(f"\n=== {label} (n={self.total}) ===")
        print(f"  true positive:  {self.true_positive}")
        print(f"  true negative:  {self.true_negative}")
        print(f"  false positive: {self.false_positive}  (rate: {self.false_positive_rate:.1%})")
        print(f"  false negative: {self.false_negative}  (rate: {self.false_negative_rate:.1%})")
        print(f"  accuracy:       {self.accuracy:.1%}")


def parse_bool_field(value: str) -> bool:
    return value.strip() in ("1", "true", "True", "yes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path")
    parser.add_argument(
        "--by-column",
        default=None,
        help="also break results down per distinct value of this column (e.g. 'scenario')",
    )
    args = parser.parse_args()

    overall = ConfusionCounts()
    by_group: dict[str, ConfusionCounts] = defaultdict(ConfusionCounts)

    with open(args.csv_path, newline="") as f:
        reader = csv.DictReader(f)
        if "detected_hazard" not in reader.fieldnames or "ground_truth_hazard" not in reader.fieldnames:
            print("ERROR: CSV must have 'detected_hazard' and 'ground_truth_hazard' columns", file=sys.stderr)
            return 1

        row_count = 0
        for row in reader:
            detected = parse_bool_field(row["detected_hazard"])
            truth = parse_bool_field(row["ground_truth_hazard"])
            overall.add(detected, truth)
            row_count += 1
            if args.by_column and args.by_column in row:
                by_group[row[args.by_column]].add(detected, truth)

    if row_count == 0:
        print("ERROR: no data rows found", file=sys.stderr)
        return 1

    overall.print_report("Overall")
    for group_name, counts in sorted(by_group.items()):
        counts.print_report(f"Scenario: {group_name}")

    if row_count < 100:
        print(
            f"\nNOTE: only {row_count} rows — the learning roadmap's B2 deliverable calls for "
            "50+ walks over a hazard AND 50+ over flat ground (100+ total) before trusting this rate."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
