#!/usr/bin/env python3
"""Train SENSEWALK's ground-hazard detector (potholes today; stairs/curbs/open
drains once you have labelled data) and export it for the Raspberry Pi.

Pipeline:  prepare_dataset.py  ->  this script  ->  evaluate_onnx.py

What it does:
  1. Fine-tunes a COCO-pretrained YOLOv8n at 320x320 (small enough for a Pi 3B).
  2. Reports validation AND held-out test metrics from the trained weights.
  3. Exports ONNX (opset 12, fixed 320x320 input, simplified) — the format
     vision/pi/src/detector.py's YoloOnnxDetector runs through OpenCV's DNN
     module, so the Pi needs nothing beyond opencv-python.
  4. Writes hazard_classes.txt next to the model and a metrics JSON you can
     quote (honestly) in the final report.

Needs a GPU-enabled PyTorch + `pip install ultralytics onnx onnxslim`
(see requirements-train.txt). Train on a laptop/desktop, NOT on the Pi.

Example:
    python training/train_hazard_model.py --data /data/merged/data.yaml \\
        --weights yolov8n.pt --epochs 100 --batch 16
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT_DIR = REPO_ROOT / "vision" / "pi" / "models"
MODEL_FILENAME = "hazard_yolov8n_320.onnx"
CLASSES_FILENAME = "hazard_classes.txt"


def extract_metrics(m) -> dict:
    """Pull the headline numbers out of an ultralytics validation result."""
    b = m.box
    return {
        "precision": round(float(b.mp), 4),
        "recall": round(float(b.mr), 4),
        "mAP50": round(float(b.map50), 4),
        "mAP50_95": round(float(b.map), 4),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True, help="data.yaml from prepare_dataset.py")
    p.add_argument("--weights", default="yolov8n.pt", help="pretrained checkpoint to fine-tune")
    p.add_argument("--imgsz", type=int, default=320)
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--patience", type=int, default=25, help="early-stop after this many epochs without improvement")
    p.add_argument("--device", default=None, help="'0' for first GPU, 'cpu'; default: auto")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--evaluate-only", metavar="WEIGHTS.pt", default=None,
                   help="skip training; just evaluate and export these weights (e.g. to finish an interrupted run from its best.pt)")
    p.add_argument("--plots", action="store_true", help="save training curves (downloads a font on first use; off by default)")
    p.add_argument("--project", default=str(REPO_ROOT / "training" / "runs"))
    p.add_argument("--name", default="hazard")
    p.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR))
    p.add_argument("--results-json", default=str(REPO_ROOT / "training" / "results" / "hazard_metrics.json"))
    args = p.parse_args()

    from ultralytics import YOLO

    device = args.device
    if device is None:
        import torch

        device = "0" if torch.cuda.is_available() else "cpu"
    print(f"Training on device={device}")

    if args.evaluate_only is None:
        YOLO(args.weights).train(
            data=args.data,
            imgsz=args.imgsz,
            epochs=args.epochs,
            batch=args.batch,
            patience=args.patience,
            device=device,
            workers=args.workers,
            seed=args.seed,
            project=args.project,
            name=args.name,
            exist_ok=True,
            plots=args.plots,
        )

    best_pt = Path(args.evaluate_only) if args.evaluate_only else Path(args.project) / args.name / "weights" / "best.pt"
    best = YOLO(str(best_pt))

    val_metrics = extract_metrics(best.val(data=args.data, split="val", imgsz=args.imgsz, device=device, verbose=False))
    test_metrics = extract_metrics(best.val(data=args.data, split="test", imgsz=args.imgsz, device=device, verbose=False))
    print("validation:", val_metrics)
    print("test (held out):", test_metrics)

    exported = Path(best.export(format="onnx", imgsz=args.imgsz, opset=12, simplify=True, dynamic=False, device="cpu"))
    export_dir = Path(args.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exported, export_dir / MODEL_FILENAME)
    names = best.names  # {0: 'pothole', ...}
    (export_dir / CLASSES_FILENAME).write_text("\n".join(names[i] for i in sorted(names)) + "\n")

    results = {
        "model": MODEL_FILENAME,
        "base_weights": args.weights,
        "imgsz": args.imgsz,
        "epochs_requested": args.epochs,
        "classes": [names[i] for i in sorted(names)],
        "validation": val_metrics,
        "test_heldout": test_metrics,
        "note": "Metrics are from ultralytics' evaluator on the PyTorch weights; "
        "run evaluate_onnx.py for the deployed OpenCV-DNN path.",
    }
    out = Path(args.results_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"Wrote {export_dir / MODEL_FILENAME}, {export_dir / CLASSES_FILENAME}, {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
