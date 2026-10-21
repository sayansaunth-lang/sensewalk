# Training the Ground-Hazard Detector (potholes)

This folder produces `vision/pi/models/hazard_yolov8n_256_fp16.onnx` — the one AI model in SENSEWALK that is *ours* rather than downloaded. COCO-trained detectors (the people/objects model in `vision/pi/`) know persons and chairs but have never seen a pothole, and potholes are the headline hazard in the research report.

Pipeline: `prepare_dataset.py` → `train_hazard_model.py` → `evaluate_onnx.py`

## What was trained, and the honest numbers

| | |
|---|---|
| Model | YOLOv8n fine-tuned from COCO-pretrained weights at 320×320, **3,011,043 parameters** |
| Classes | `pothole` (one) |
| Data | 913 unique images after cleaning (730 train / 91 val / 92 test), 1,959 boxes |
| Training | CPU, ~66 s/epoch. The run was interrupted at epoch 24 of 60; the best checkpoint (by validation score, around epoch 17) was used |
| Export (shipped) | ONNX opset 12, **256×256 input, FP16 weights, 6.1 MB**, runs through OpenCV's DNN module (no extra runtime on the Pi). Compressed from the 12.1 MB / 320×320 export — see "Compression" below |

**Held-out test set (92 images, 187 boxes — never used for training or checkpoint selection):**

| Evaluator | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| ultralytics, PyTorch weights | 0.65 | 0.53 | 0.546 | 0.263 |
| **Deployed path, shipped model** (256, FP16; ONNX + OpenCV DNN + our decode/NMS), `evaluate_onnx.py` | 0.68 | 0.49 | AP50 0.538 | — |
| Deployed path, original 320 full-precision export (no longer shipped) | 0.64 | 0.49 | AP50 0.511 | — |

The deployed-path numbers are the ones to quote. AP50 is identical under OpenCV 4.8.1, 4.10.0 and 5.0.0 (precision differed by 0.01 on 5.0 from one borderline detection), so the model behaves the same across the OpenCV versions a Pi might ship. At the 0.35 operating threshold on the test set the shipped model gives 92 true detections, 44 false alarms and 95 missed potholes. Speed: ~12–18 ms/frame on a laptop CPU (i5-13420H); a Pi 3B will be much slower — **an estimate, measure it** with `vision/pi/src/benchmark.py`.

### What this means in plain terms

It finds roughly half of the potholes it is shown and roughly one detection in three is wrong. That is a useful *"something odd on the ground ahead"* nudge, **not** a safety system — which is why the architecture only lets it produce a spoken/haptic **warning** and never the brake. Braking stays with the ESP32's ToF/ultrasonic sensors, which measure real distance.

## Compression (why the shipped model is 256 / FP16)

The original export was 12.1 MB at 320×320. `compress_model.py` makes it smaller in two independent ways. Each was scored on the same 92 held-out test images with OpenCV (the code path the Pi runs), after rebuilding the dataset split from scratch and confirming it reproduced the original numbers exactly:

| Variant | File | AP50 | Precision | Recall | Hits / false alarms / misses |
|---|---|---|---|---|---|
| 320, full precision (original) | 12.14 MB | 0.511 | 0.641 | 0.487 | 91 / 51 / 96 |
| 320, FP16 | 6.11 MB | 0.511 | 0.636 | 0.487 | 91 / 52 / 96 |
| 256, full precision | 12.12 MB | 0.538 | 0.682 | 0.492 | 92 / 43 / 95 |
| **256, FP16 (shipped)** | **6.10 MB** | **0.538** | **0.677** | **0.492** | **92 / 44 / 95** |
| 224, FP16 | 6.10 MB | 0.542 | 0.672 | 0.492 | 92 / 45 / 95 |

- **FP16 halves the file** with no measurable accuracy change. It does **not** reduce RAM or speed: OpenCV expands the weights back to 32-bit when it loads the model. It helps disk space and download time only.
- **A smaller input is what makes it faster.** Compute scales with the square of the size, so 256 is about 36% less work than 320 (224 is about 51% less). A fully convolutional network can be exported at a new size without retraining.
- **Why 256 and not 224:** the 224 score was not meaningfully better, and a smaller input loses small or distant potholes first. 256 is the compromise. Re-run `evaluate_onnx.py` on your own walker footage before going lower.
- **Caution on the numbers:** the lower-resolution models scoring slightly *higher* than 320 is within what 92 test images can produce by chance. Read it as "no loss detected", not "256 is better".
- **Not tried:** INT8 quantization. OpenCV's DNN module cannot run the usual ONNX INT8 format, and the alternatives (onnxruntime on a 1 GB Pi, or a TensorFlow Lite conversion) add heavy dependencies; the speed benefit on a Pi 3B is unmeasured. Worth trying only if the benchmark shows the Pi is too slow even at 256.

Reproduce: `python training/compress_model.py --weights training/runs/hazard/weights/best.pt` (add `--imgsz 320 --no-fp16` for the original). `train_hazard_model.py` now exports this compact model by default.

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
