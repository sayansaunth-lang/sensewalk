"""Train a tiny "pothole in view?" image classifier small enough to run on the ESP32-S3 camera board.

This is NOT the YOLOv8n detector used on the Pi. The ESP32-S3 cannot run that model, so this is a
~15k-60k parameter CNN that looks at a 64x64 grayscale view and answers one question: does this
view contain a pothole? It cannot say where, and it will be less accurate than the Pi's model.

Data: the same leak-free train/val/test split as the YOLO model (training/prepare_dataset.py), so
the test images are never seen in training. A "view" is a random square crop of an image:
  positive = a crop that mostly contains at least one labelled pothole box;
  negative = a crop with no pothole box at all (road, kerbs, sky, buildings from the same photos).
Augmentation imitates a cheap camera (blur, noise, low contrast) so the model is not fooled by it.

Run (training Python env with torch + opencv):
    python training/tiny_pothole/train_tiny_pothole.py --data <merged dataset dir> --out <out dir> --width 16
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn

VIEW = 64


# --------------------------------------------------------------------------- data
def read_split(root: Path, split: str):
    items = []
    for img_path in sorted((root / "images" / split).glob("*.jpg")):
        img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        h, w = img.shape
        boxes = []
        lab = root / "labels" / split / (img_path.stem + ".txt")
        if lab.exists():
            for line in lab.read_text().splitlines():
                p = line.split()
                if len(p) == 5:
                    cx, cy, bw, bh = (float(v) for v in p[1:])
                    boxes.append(((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h))
        items.append((img, boxes, img_path.name))
    return items


def _overlap(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy


def sample_view(img, boxes, rng, positive: bool, tries: int = 40):
    """Return a square crop (uint8, any size) that is a positive or negative view, or None."""
    h, w = img.shape
    short = min(h, w)
    for _ in range(tries):
        side = rng.uniform(0.45, 1.0) * short if positive else rng.uniform(0.3, 0.8) * short
        x0 = rng.uniform(0, w - side)
        y0 = rng.uniform(0, h - side)
        crop = (x0, y0, x0 + side, y0 + side)
        if positive:
            for b in boxes:
                barea = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))
                inside = _overlap(crop, b)
                if inside / barea >= 0.6 and inside / (side * side) >= 0.04:
                    return img[int(y0):int(y0 + side), int(x0):int(x0 + side)]
        else:
            margin = 0.05 * short
            if all(_overlap(crop, (b[0] - margin, b[1] - margin, b[2] + margin, b[3] + margin)) == 0 for b in boxes):
                return img[int(y0):int(y0 + side), int(x0):int(x0 + side)]
    return None


def to_view(crop: np.ndarray) -> np.ndarray:
    return cv2.resize(crop, (VIEW, VIEW), interpolation=cv2.INTER_AREA)


def augment(v: np.ndarray, rng) -> np.ndarray:
    """Imitate a cheap sensor: softness, noise, flat contrast, exposure drift, hflip."""
    v = v.astype(np.float32)
    if rng.random() < 0.5:
        v = v[:, ::-1]
    alpha = rng.uniform(0.5, 1.4)
    beta = rng.uniform(-40, 40)
    v = (v - 128.0) * alpha + 128.0 + beta
    if rng.random() < 0.5:
        k = rng.uniform(0.3, 1.4)
        v = cv2.GaussianBlur(np.ascontiguousarray(v), (0, 0), k)
    if rng.random() < 0.7:
        v = v + rng.normal(0, rng.uniform(0, 9), v.shape)
    if rng.random() < 0.3:
        small = cv2.resize(np.ascontiguousarray(v), (32, 32), interpolation=cv2.INTER_AREA)
        v = cv2.resize(small, (VIEW, VIEW), interpolation=cv2.INTER_LINEAR)
    return np.clip(v, 0, 255).astype(np.uint8)


def fixed_set(items, seed: int, views_per_class: int = 2):
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for img, boxes, _ in items:
        for positive in (True, False):
            for _ in range(views_per_class):
                crop = sample_view(img, boxes, rng, positive)
                if crop is not None and crop.size > 100:
                    xs.append(to_view(crop))
                    ys.append(1 if positive else 0)
    return np.stack(xs), np.array(ys, dtype=np.int64)


# --------------------------------------------------------------------------- model
class Net(nn.Module):
    def __init__(self, width: int):
        super().__init__()
        c = [1, width, width * 2, width * 4, width * 4]
        layers = []
        for i in range(4):
            layers += [nn.Conv2d(c[i], c[i + 1], 3, stride=2, padding=1, bias=False), nn.BatchNorm2d(c[i + 1]), nn.ReLU()]
        self.features = nn.Sequential(*layers)
        self.fc = nn.Linear(c[4], 2)

    def forward(self, x):
        x = self.features(x)
        return self.fc(x.mean(dim=(2, 3)))


def prep(batch_u8: np.ndarray) -> torch.Tensor:
    # same normalisation the ESP32 code uses: (pixel - 128) / 128
    return torch.from_numpy((batch_u8.astype(np.float32) - 128.0) / 128.0).unsqueeze(1)


def metrics(prob: np.ndarray, y: np.ndarray, thr: float):
    pred = prob >= thr
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    return {"thr": float(thr), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / max(1, tp + fp), "recall": tp / max(1, tp + fn), "accuracy": (tp + tn) / len(y)}


def auc(prob: np.ndarray, y: np.ndarray) -> float:
    pos, neg = prob[y == 1], prob[y == 0]
    return float(np.mean([(p > neg).mean() + 0.5 * (p == neg).mean() for p in pos]))


def predict(model, xs):
    model.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(xs), 512):
            out.append(torch.softmax(model(prep(xs[i:i + 512])), dim=1)[:, 1].numpy())
    return np.concatenate(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--width", type=int, default=16)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(8)
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)

    train, val, test = (read_split(args.data, s) for s in ("train", "val", "test"))
    xv, yv = fixed_set(val, 101)
    xt, yt = fixed_set(test, 202)
    print(f"images train/val/test: {len(train)}/{len(val)}/{len(test)}; fixed views val {len(yv)} (pos {int(yv.sum())}), "
          f"test {len(yt)} (pos {int(yt.sum())})")

    model = Net(args.width)
    n_params = sum(p.numel() for p in model.parameters())
    print("parameters:", n_params)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=6e-3, total_steps=args.epochs * 60)
    lossf = nn.CrossEntropyLoss()

    best = (-1.0, None)
    t0 = time.time()
    for epoch in range(args.epochs):
        xs, ys = [], []
        for img, boxes, _ in train:
            for positive in (True, False):
                for _ in range(2 if positive else 4):  # more negatives: a warning that cries wolf gets ignored
                    crop = sample_view(img, boxes, rng, positive)
                    if crop is not None and crop.size > 100:
                        xs.append(augment(to_view(crop), rng))
                        ys.append(1 if positive else 0)
        xs, ys = np.stack(xs), np.array(ys)
        order = rng.permutation(len(ys))
        model.train()
        batches = np.array_split(order, 60)
        total = 0.0
        for idx in batches:
            opt.zero_grad()
            loss = lossf(model(prep(xs[idx])), torch.from_numpy(ys[idx]))
            loss.backward()
            opt.step()
            sched.step()
            total += float(loss)
        pv = predict(model, xv)
        a = auc(pv, yv)
        if a > best[0]:
            best = (a, {k: v.clone() for k, v in model.state_dict().items()})
        if epoch % 5 == 0 or epoch == args.epochs - 1:
            print(f"epoch {epoch:2d} loss {total / 60:.3f} val AUC {a:.3f} acc@0.5 {metrics(pv, yv, 0.5)['accuracy']:.3f} "
                  f"({time.time() - t0:.0f}s, train views {len(ys)}, pos {int(ys.sum())})")

    model.load_state_dict(best[1])
    pv, pt = predict(model, xv), predict(model, xt)
    # threshold: the lowest one that still gives >= 85% precision on VALIDATION (a warning that cries wolf is ignored)
    chosen = 0.5
    for thr in np.linspace(0.3, 0.95, 66):
        if metrics(pv, yv, thr)["precision"] >= 0.85:
            chosen = float(thr)
            break
    result = {
        "width": args.width, "parameters": n_params, "best_val_auc": best[0],
        "chosen_threshold": chosen,
        "val": metrics(pv, yv, chosen), "test": metrics(pt, yt, chosen), "test_auc": auc(pt, yt),
        "test_at_0.5": metrics(pt, yt, 0.5),
        "note": "views are random square crops of the held-out images; this is a view classifier, not a detector",
    }
    print(json.dumps(result, indent=2))
    (args.out / f"tiny_pothole_w{args.width}.json").write_text(json.dumps(result, indent=2))
    torch.save(best[1], args.out / f"tiny_pothole_w{args.width}.pt")
    np.save(args.out / "test_views.npy", xt[:64])
    np.save(args.out / "test_views_labels.npy", yt[:64])


if __name__ == "__main__":
    main()
