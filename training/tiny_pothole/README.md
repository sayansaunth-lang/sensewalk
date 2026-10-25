# Tiny pothole classifier (ESP32-S3 camera board)

The YOLOv8n pothole detector (`training/`) is far too big for an ESP32-S3. This is a separate, much smaller
model that runs **on the camera board itself**, so a demo needs no laptop and no Pi.

It answers one question per frame: **does this view contain a pothole?** It cannot say *where*, so it can only
drive a warning (buzzer + vibration), never the brake.

| | |
|---|---|
| Input | 64x64 grayscale, the centre square of the camera frame |
| Network | 4 stride-2 3x3 convolutions (16-32-64-64 channels, BatchNorm folded in), global average pool, 2-way dense |
| Size | 60,530 parameters (about 240 KB as float32 in flash) |
| Code | `firmware/esp32_arduino_ide/SENSEWALK_cam_main/pothole_net.h`, plain C++, no library |
| Training data | the same leak-free train/val/test split as the YOLO model (730 / 91 / 92 images) |

## How it was trained
A *view* is a random square crop of a photo. A **positive** view mostly contains a labelled pothole; a **negative**
view contains no pothole box (road, kerb, sky, buildings from the same photos). Training samples 2 positive and 4
negative views per image per epoch with "cheap camera" augmentation (blur, noise, low contrast, exposure drift).
Validation and test use fixed, seeded views of images the model never trained on.

## Measured results (held-out test images, 257 views: 180 pothole, 77 not)

| Threshold | False alarms on non-pothole views | Potholes caught |
|---|---|---|
| 0.73 (**shipped**, `kThreshold`) | about 5% | about 71% |
| 0.62 | about 8% | about 81% |
| 0.46 | about 14% | about 88% |

Threshold-independent quality: AUC 0.94 (test). Full numbers: `training/results/tiny_pothole_w16.json`.
The 5/8/14% figures come from 77 negative views, so each carries roughly +/-5 points of uncertainty.
A smaller 15k-parameter version (width 8) scored worse (AUC 0.89), so width 16 was kept.

The board also requires 2 of the last 3 frames to agree before it raises an alert, which removes isolated false
alarms but not a steady one.

## Proof the board computes the same thing as PyTorch
`firmware/esp32_arduino_ide/tools/test_pothole_net.cpp` runs 12 held-out views through the C++ code and compares
with PyTorch: worst logit difference 6e-07. CI runs it on every push, and the board repeats the check at boot
("pothole selftest ... OK").

## What these numbers do NOT tell you
* The test views are crops of *web photos* of potholes and the roads around them. A walker's camera is lower, in
  different light, and sees pavements and floors. **Real-world accuracy is unmeasured.**
* "Not a pothole" here means road, kerbs, sky and buildings from the same photos. Indoor scenes, faces, shadows,
  manhole covers and cracks were never taught as "not a pothole" and may trigger false alarms.
* The camera board's own sensor (GC2145) is softer and noisier than the training photos. Augmentation helps, but
  it has not been tested on real pothole footage from this camera.
* A view classifier can fire when a pothole is in view anywhere in the centre square, even far away.

Before relying on it, film real ground footage with the camera board, check the false-alarm rate on ordinary
floors and pavements, and retrain (`train_tiny_pothole.py`, then `export_c.py`) with that footage added.

## Reproduce
```
python training/tiny_pothole/train_tiny_pothole.py --data <merged dataset> --out <dir> --width 16 --epochs 70
python training/tiny_pothole/export_c.py --weights <dir>/tiny_pothole_w16.pt --views <dir>/test_views.npy \
       --width 16 --threshold 0.73 --out firmware/esp32_arduino_ide/SENSEWALK_cam_main
```
