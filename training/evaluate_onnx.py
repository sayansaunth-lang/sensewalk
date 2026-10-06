#!/usr/bin/env python3
"""Evaluate the DEPLOYED ground-hazard detector (YoloOnnxDetector: ONNX model
+ OpenCV DNN + our own letterbox/decode/NMS code) against labelled images.

train_hazard_model.py reports ultralytics' metrics on the PyTorch weights.
Those don't prove the code that actually runs on the Pi — export, preprocessing
and box decoding — is correct. This script does: any bug in letterbox/decode
shows up here as a collapse in recall or AP.

Needs only opencv-python + numpy (no PyTorch).

Usage:
    python training/evaluate_onnx.py --data-dir /data/merged --split test
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

Box = tuple[float, float, float, float]  # x1, y1, x2, y2


def iou(a: Box, b: Box) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match_image(
    preds: list[tuple[float, Box]], gts: list[Box], iou_thr: float
) -> list[tuple[float, bool]]:
    """Greedy match for one image: highest-confidence predictions claim the
    best still-unmatched ground truth. Returns [(confidence, is_true_positive)]."""
    used: set[int] = set()
    results = []
    for conf, box in sorted(preds, key=lambda p: -p[0]):
        best_i, best_iou = -1, iou_thr
        for gi, g in enumerate(gts):
            if gi in used:
                continue
            v = iou(box, g)
            if v >= best_iou:
                best_i, best_iou = gi, v
        if best_i >= 0:
            used.add(best_i)
            results.append((conf, True))
        else:
            results.append((conf, False))
    return results


def precision_recall_at(scored: list[tuple[float, bool]], n_gt: int, conf_thr: float) -> dict:
    kept = [tp for c, tp in scored if c >= conf_thr]
    tp = sum(kept)
    fp = len(kept) - tp
    fn = n_gt - tp
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / n_gt if n_gt else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}


def average_precision(scored: list[tuple[float, bool]], n_gt: int) -> float:
    """All-point interpolated AP (PASCAL VOC 2010+ style) from scored matches."""
    if n_gt == 0 or not scored:
        return 0.0
    ordered = sorted(scored, key=lambda x: -x[0])
    tps = fps = 0
    precisions, recalls = [], []
    for _, is_tp in ordered:
        tps += is_tp
        fps += not is_tp
        precisions.append(tps / (tps + fps))
        recalls.append(tps / n_gt)
    # make precision monotonically non-increasing from the right
    for i in range(len(precisions) - 2, -1, -1):
        precisions[i] = max(precisions[i], precisions[i + 1])
    ap, prev_r = 0.0, 0.0
    for p, r in zip(precisions, recalls):
        ap += (r - prev_r) * p
        prev_r = r
    return ap


def read_gt(label_path: Path, w: int, h: int) -> list[Box]:
    boxes: list[Box] = []
    if not label_path.exists():
        return boxes
    for line in label_path.read_text().splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        _, cx, cy, bw, bh = parts[0], *map(float, parts[1:])
        boxes.append(((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h))
    return boxes


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-dir", required=True, help="prepare_dataset.py output directory")
    p.add_argument("--split", default="test", choices=["train", "val", "test"])
    p.add_argument("--model", default=None)
    p.add_argument("--classes", default=None)
    p.add_argument("--conf", type=float, default=0.35, help="operating confidence threshold to report P/R/F1 at")
    p.add_argument("--iou", type=float, default=0.5)
    p.add_argument("--json-out", default=None)
    args = p.parse_args()

    import cv2

    from vision.pi.src.detector import HAZARD_CLASSES_PATH, HAZARD_ONNX_PATH, YoloOnnxDetector

    # Collect low-confidence detections so AP covers the whole PR curve; report
    # P/R/F1 separately at the real operating threshold.
    detector = YoloOnnxDetector(
        model_path=Path(args.model) if args.model else HAZARD_ONNX_PATH,
        classes_path=Path(args.classes) if args.classes else HAZARD_CLASSES_PATH,
        confidence_threshold=0.01,
    )
    root = Path(args.data_dir)
    images = sorted((root / "images" / args.split).glob("*.*"))
    if not images:
        print(f"no images in {root / 'images' / args.split}", file=sys.stderr)
        return 1

    scored: list[tuple[float, bool]] = []
    n_gt = 0
    times = []
    for img_path in images:
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]
        gts = read_gt(root / "labels" / args.split / (img_path.stem + ".txt"), w, h)
        n_gt += len(gts)
        t0 = time.perf_counter()
        dets = detector.detect(img)
        times.append((time.perf_counter() - t0) * 1000)
        preds = [(d.confidence, tuple(map(float, d.box))) for d in dets]
        scored.extend(match_image(preds, gts, args.iou))

    result = {
        "split": args.split,
        "images": len(images),
        "ground_truth_boxes": n_gt,
        "iou_threshold": args.iou,
        "AP50": round(average_precision(scored, n_gt), 4),
        "operating_point": {"conf": args.conf, **precision_recall_at(scored, n_gt, args.conf)},
        "mean_inference_ms_this_machine": round(sum(times) / len(times), 1),
    }
    print(json.dumps(result, indent=2))
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
