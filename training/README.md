# Training the Ground-Hazard Detector (potholes)

This folder produces `vision/pi/models/hazard_yolov8n_320.onnx` — the one AI model in SENSEWALK that is *ours* rather than downloaded. COCO-trained detectors (the people/objects model in `vision/pi/`) know persons and chairs but have never seen a pothole, and potholes are the headline hazard in the research report.

Pipeline: `prepare_dataset.py` → `train_hazard_model.py` → `evaluate_onnx.py`

## What was trained, and the honest numbers

| | |
|---|---|
| Model | YOLOv8n fine-tuned from COCO-pretrained weights, 320×320 input |
| Classes | `pothole` (one) |
| Data | 913 unique images after cleaning (730 train / 91 val / 92 test), 1,959 boxes |
| Training | CPU, ~66 s/epoch. The run was interrupted at epoch 24 of 60; the best checkpoint (by validation score, around epoch 17) was used |
| Export | ONNX opset 12, fixed 320×320, 11.6 MB, runs through OpenCV's DNN module (no extra runtime on the Pi) |

**Held-out test set (92 images, 187 boxes — never used for training or checkpoint selection):**

| Evaluator | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| ultralytics, PyTorch weights | 0.65 | 0.53 | 0.546 | 0.263 |
| **Deployed path** (ONNX + OpenCV DNN + our decode/NMS), `evaluate_onnx.py` | 0.64 | 0.49 | AP50 0.511 | — |

The deployed-path numbers are the ones to quote. They are identical under OpenCV 4.8.1, 4.10.0 and 5.0.0, so the model behaves the same across the OpenCV versions a Pi might ship. At the 0.35 operating threshold on the test set: 91 true detections, 51 false alarms, 96 missed potholes. Speed: ~32–36 ms/frame on a laptop CPU (i5-13420H, OpenCV 4.x); a Pi 3B will be roughly an order of magnitude slower — **an estimate, measure it** (see `docs/PI3B_LOW_RAM_SETUP.md`).

### What this means in plain terms

It finds roughly half of the potholes it is shown and roughly one detection in three is wrong. That is a useful *"something odd on the ground ahead"* nudge, **not** a safety system — which is why the architecture only lets it produce a spoken/haptic **warning** and never the brake. Braking stays with the ESP32's ToF/ultrasonic sensors, which measure real distance.

## Known limitations (read before trusting it)

- **Small, web-sourced data.** ~900 photos, mostly taken from car or standing height in daylight. A walker's camera is lower and sees sidewalks, floors and ramps. Expect worse results on your own footage until you add it.
- **No "clean road" negatives.** Every training image contains a pothole, so the model has not been taught what cracks, shadows, manhole covers or patched tar are *not*. False alarms on those are likely.
- **One class.** Stairs, curbs and open drains are in `GROUND_HAZARD_CLASSES` ready to be used, but nothing here detects them yet.
- **Small test set.** 92 images means the true accuracy could plausibly differ by ±10 points either way. Don't over-read the second decimal.
- **Interrupted training.** Stopping at epoch 24 of 60 was not by design. The validation curve had plateaued around 0.5 mAP50 but a full run might gain a little.

## Reproducing it

```bash
# 1. Training venv (laptop/desktop, NOT the Pi). Use a SHORT path on Windows —
#    PyTorch's file paths exceed the 260-character limit inside deep folders.
python -m venv C:\swtrain\env
C:\swtrain\env\Scripts\pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # or /cu124 for an NVIDIA GPU
C:\swtrain\env\Scripts\pip install -r training/requirements-train.txt

# 2. Merge + clean sources into one leak-free dataset
python training/prepare_dataset.py --source a=/path/to/datasetA --source b=/path/to/datasetB --out /path/merged --classes pothole

# 3. Train + evaluate + export (writes the .onnx and hazard_classes.txt into vision/pi/models/)
python training/train_hazard_model.py --data /path/merged/data.yaml --weights yolov8n.pt --epochs 60 --batch 16 --device cpu
#    …or finish an interrupted run from its best checkpoint:
python training/train_hazard_model.py --data /path/merged/data.yaml --evaluate-only runs/hazard/weights/best.pt

# 4. Score the code that actually runs on the Pi
python training/evaluate_onnx.py --data-dir /path/merged --split test
```

Why `prepare_dataset.py` exists rather than pointing the trainer at the raw downloads: (a) public datasets contain junk — one source had a stray personal cover letter inside a labels file, 14 non-label lines, which are dropped and never copied into this repo; (b) Roboflow exports contain augmented copies of the same photo, so images are clustered by perceptual hash and each cluster stays whole inside one split — otherwise an augmented copy in training inflates the validation score; (c) 101 exact duplicates existed across the two sources.

## Improving it (what will actually move the numbers)

1. **Film your own data** with the real Pi Camera Module 3 mounted on the walker at its real height — sidewalks, corridors, ramps, potholes, stairs, curbs. This beats any tuning of the model.
2. **Label it** (Roboflow, CVAT or Label Studio export YOLO format) and add it as another `--source`.
3. **Add negatives** — hundreds of obstacle-free road/floor frames with empty label files — to cut false alarms.
4. **Add classes** (`stairs`, `curb`, `open_drain`) and extend `--classes`.
5. Retrain, re-run `evaluate_onnx.py`, and report the new real numbers.

## Data sources and licences

| Source | Licence per its listing |
|---|---|
| `rupesh002/pothole-detection-dataset` (Hugging Face) | MIT (listing). It is a Roboflow export; the original uploader's terms were not verifiable — check before redistributing the *dataset* |
| `Ryukijano/Pothole-detection-Yolov8` → Roboflow `potholes-detection-d4rma` v1 (workspace `project-ssayl`) | CC BY 4.0 — attribution above |

The raw datasets are **not** in this repository. Pretrained starting weights: Ultralytics YOLOv8n (COCO).

**Licence note:** Ultralytics YOLOv8 is licensed AGPL-3.0, and the exported model is a derivative of it. That is fine for a university project, but if SENSEWALK is ever distributed or commercialised, the AGPL-3.0 obligations (or an Ultralytics enterprise licence) apply — decide that before then.
