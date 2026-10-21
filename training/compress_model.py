#!/usr/bin/env python3
"""Shrink the trained pothole detector for the Raspberry Pi 3B.

Two independent reductions, both measured before being adopted (see training/README.md):

1. FP16 weights (default on): stores the weights in half precision, which halves the file.
   Accuracy was unchanged on the held-out test set. NOTE what it does NOT do: OpenCV expands
   the weights back to 32-bit when it loads the model, so it saves disk space and download
   time, not RAM or inference speed.
2. A smaller input size (default 256 instead of the 320 the model was trained at): the network
   is fully convolutional, so it can be exported at another size without retraining. Compute
   falls with the square of the size (256 is ~36% less work than 320), which is what actually
   makes it faster on a slow CPU. Measured accuracy at 256 was no worse than at 320, but the
   test set is only 92 images, so re-check on your own footage: very small, distant potholes
   are the first thing a lower resolution can lose.

The output file name carries the size (hazard_yolov8n_<size>[_fp16].onnx) because
vision/pi/src/detector.py reads the input size from it.

Usage (needs the training environment: torch + ultralytics + onnx + onnxconverter-common):
    python training/compress_model.py --weights training/runs/hazard/weights/best.pt
    python training/compress_model.py --weights best.pt --imgsz 320 --no-fp16
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = REPO_ROOT / "vision" / "pi" / "models"


def model_filename(imgsz: int, fp16: bool) -> str:
    return f"hazard_yolov8n_{imgsz}{'_fp16' if fp16 else ''}.onnx"


def export_compressed(weights: Path, out_dir: Path, imgsz: int = 256, fp16: bool = True) -> Path:
    """Export `weights` (a trained .pt) to ONNX at `imgsz`, optionally with FP16 weights, into
    `out_dir`. Returns the written path."""
    from ultralytics import YOLO

    model = YOLO(str(weights))
    exported = Path(model.export(format="onnx", imgsz=imgsz, opset=12, simplify=True, dynamic=False, device="cpu"))
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / model_filename(imgsz, fp16)

    if not fp16:
        shutil.copy2(exported, target)
        return target

    import onnx
    from onnxconverter_common import float16

    # keep_io_types: the network still takes and returns float32, only the stored weights shrink,
    # so the detector code needs no change.
    half = float16.convert_float_to_float16(onnx.load(str(exported)), keep_io_types=True)
    onnx.save(half, str(target))
    return target


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--weights", required=True, help="trained PyTorch checkpoint (best.pt)")
    ap.add_argument("--imgsz", type=int, default=256)
    ap.add_argument("--no-fp16", action="store_true", help="keep full-precision weights")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = ap.parse_args()

    target = export_compressed(Path(args.weights), Path(args.out_dir), args.imgsz, not args.no_fp16)
    print(f"wrote {target} ({target.stat().st_size / 1e6:.2f} MB)")
    print("Now score it on the held-out set:  python training/evaluate_onnx.py --data-dir <merged> --split test "
          f"--model {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
