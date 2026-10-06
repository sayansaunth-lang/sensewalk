#!/usr/bin/env python3
"""Merge one or more YOLO-format hazard datasets into one clean, leak-free
train/val/test dataset for training the SENSEWALK ground-hazard detector.

Why this exists instead of just pointing the trainer at the raw downloads:

1. Raw public datasets contain junk. One real source used for this project
   had non-label text (a stray cover letter) inside a labels file. Every
   label line is validated here; malformed lines are dropped and counted.
2. Roboflow-style exports contain augmented copies of the same photo. If a
   copy lands in train and another in validation, the reported accuracy is
   inflated (the model has effectively seen the validation image). Images
   are clustered by perceptual hash and each cluster is kept whole inside a
   single split, so validation numbers mean something.
3. Different sources use different class ids for the same thing. A
   per-source class map normalises them into one shared class list.

Usage:
    python training/prepare_dataset.py \\
        --source a=/data/datasetA --source b=/data/datasetB \\
        --out /data/merged --classes pothole

A source directory must contain <split>/images and <split>/labels for any of
train / valid / val / test (the original split is ignored — everything is
pooled and re-split by cluster). Source class ids default to "0 -> first
class"; override with --class-map SRC:SRC_ID=NAME (repeatable).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
SPLIT_NAMES = ("train", "valid", "val", "test")
NEAR_DUPLICATE_MAX_HAMMING = 6  # of 64 bits; catches resized/re-encoded/augmented copies


@dataclass
class Sample:
    source: str
    image_path: Path
    boxes: list[tuple[int, float, float, float, float]]  # (class_id, cx, cy, w, h) normalised
    sha1: str = ""
    dhash: int = 0


@dataclass
class PrepReport:
    images_seen: int = 0
    images_kept: int = 0
    images_dropped_no_valid_boxes: int = 0
    images_dropped_exact_duplicate: int = 0
    label_lines_dropped: int = 0
    clusters: int = 0
    per_split: dict = field(default_factory=dict)


def parse_label_file(path: Path, class_map: dict[str, int]) -> tuple[list[tuple[int, float, float, float, float]], int]:
    """Returns (valid_boxes, dropped_line_count). A line is valid only if it is
    exactly `class cx cy w h` with a known class and all coordinates in [0, 1]
    with positive width/height."""
    boxes: list[tuple[int, float, float, float, float]] = []
    dropped = 0
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return boxes, 0
    for raw in text.splitlines():
        parts = raw.split()
        if not parts:
            continue
        if len(parts) != 5 or parts[0] not in class_map:
            dropped += 1
            continue
        try:
            cx, cy, w, h = (float(v) for v in parts[1:])
        except ValueError:
            dropped += 1
            continue
        if not (0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0 and 0.0 < w <= 1.0 and 0.0 < h <= 1.0):
            dropped += 1
            continue
        boxes.append((class_map[parts[0]], cx, cy, w, h))
    return boxes, dropped


def dhash64(image_path: Path) -> int:
    """64-bit difference hash — robust to resizing, re-encoding, and mild
    brightness/contrast changes, which is what augmented copies look like."""
    import cv2

    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return 0
    small = cv2.resize(img, (9, 8), interpolation=cv2.INTER_AREA)
    bits = 0
    for row in range(8):
        for col in range(8):
            bits = (bits << 1) | int(small[row, col] > small[row, col + 1])
    return bits


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def cluster_by_similarity(samples: list[Sample], max_hamming: int = NEAR_DUPLICATE_MAX_HAMMING) -> list[list[int]]:
    """Union-find over samples whose hashes are within max_hamming bits."""
    parent = list(range(len(samples)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(samples)):
        for j in range(i + 1, len(samples)):
            if hamming(samples[i].dhash, samples[j].dhash) <= max_hamming:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri

    groups: dict[int, list[int]] = {}
    for i in range(len(samples)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def split_clusters(
    clusters: list[list[int]], fractions: tuple[float, float, float], seed: int
) -> dict[str, list[int]]:
    """Assign whole clusters to train/val/test, aiming for the requested image
    fractions. Deterministic for a given seed."""
    rng = random.Random(seed)
    order = list(range(len(clusters)))
    rng.shuffle(order)
    total = sum(len(c) for c in clusters)
    targets = {"train": fractions[0] * total, "val": fractions[1] * total, "test": fractions[2] * total}
    assigned: dict[str, list[int]] = {"train": [], "val": [], "test": []}
    counts = {"train": 0, "val": 0, "test": 0}
    for ci in order:
        # place the cluster in the split currently furthest below its target
        name = max(targets, key=lambda s: targets[s] - counts[s])
        assigned[name].extend(clusters[ci])
        counts[name] += len(clusters[ci])
    return assigned


def collect_source(
    name: str, root: Path, class_map: dict[str, int], report: PrepReport
) -> list[Sample]:
    samples: list[Sample] = []
    for split in SPLIT_NAMES:
        img_dir, lbl_dir = root / split / "images", root / split / "labels"
        if not img_dir.is_dir():
            continue
        for img in sorted(img_dir.iterdir()):
            if img.suffix.lower() not in IMAGE_EXTS:
                continue
            report.images_seen += 1
            boxes, dropped = parse_label_file(lbl_dir / (img.stem + ".txt"), class_map)
            report.label_lines_dropped += dropped
            if not boxes:
                report.images_dropped_no_valid_boxes += 1
                continue
            samples.append(Sample(source=name, image_path=img, boxes=boxes))
    return samples


def prepare(
    sources: dict[str, Path],
    out_dir: Path,
    classes: list[str],
    class_maps: dict[str, dict[str, int]] | None = None,
    fractions: tuple[float, float, float] = (0.8, 0.1, 0.1),
    seed: int = 0,
) -> PrepReport:
    report = PrepReport()
    all_samples: list[Sample] = []
    for name, root in sources.items():
        cmap = (class_maps or {}).get(name, {"0": 0})
        all_samples.extend(collect_source(name, root, cmap, report))

    # exact duplicates (same bytes, e.g. the same file present in two sources)
    unique: list[Sample] = []
    seen_sha: set[str] = set()
    for s in all_samples:
        s.sha1 = hashlib.sha1(s.image_path.read_bytes()).hexdigest()
        if s.sha1 in seen_sha:
            report.images_dropped_exact_duplicate += 1
            continue
        seen_sha.add(s.sha1)
        s.dhash = dhash64(s.image_path)
        unique.append(s)

    clusters = cluster_by_similarity(unique)
    report.clusters = len(clusters)
    assignment = split_clusters(clusters, fractions, seed)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    for split, idxs in assignment.items():
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)
        for n, i in enumerate(idxs):
            s = unique[i]
            stem = f"{s.source}_{n:05d}"
            shutil.copy2(s.image_path, out_dir / "images" / split / f"{stem}{s.image_path.suffix.lower()}")
            lines = "\n".join(f"{c} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for c, cx, cy, w, h in s.boxes)
            (out_dir / "labels" / split / f"{stem}.txt").write_text(lines + "\n")
        report.per_split[split] = {
            "images": len(idxs),
            "boxes": sum(len(unique[i].boxes) for i in idxs),
        }
    report.images_kept = len(unique)

    names_yaml = "[" + ", ".join(f"'{c}'" for c in classes) + "]"
    (out_dir / "data.yaml").write_text(
        f"path: {out_dir.resolve().as_posix()}\n"
        "train: images/train\nval: images/val\ntest: images/test\n"
        f"nc: {len(classes)}\nnames: {names_yaml}\n"
    )
    (out_dir / "prep_report.json").write_text(json.dumps(report.__dict__, indent=2, default=str))
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", action="append", required=True, metavar="NAME=PATH")
    p.add_argument("--out", required=True)
    p.add_argument("--classes", nargs="+", default=["pothole"])
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    sources: dict[str, Path] = {}
    for item in args.source:
        name, _, path = item.partition("=")
        if not path or not Path(path).is_dir():
            print(f"ERROR: bad --source {item!r} (directory not found)", file=sys.stderr)
            return 1
        sources[name] = Path(path)

    report = prepare(sources, Path(args.out), args.classes, seed=args.seed)
    print(json.dumps(report.__dict__, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
