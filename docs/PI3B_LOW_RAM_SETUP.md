# Running the Vision Pipeline on a Raspberry Pi 3B (1GB)

The team is building with a **Raspberry Pi 3B (1GB RAM)** instead of the Pi 4 (2GB) the research report specced, because that's the hardware actually in hand — see [`docs/BOM.md`](BOM.md). This is workable, but three real constraints need active handling, not just hope:

1. **Weaker CPU** — quad-core Cortex-A53 @ 1.2GHz vs. the Pi 4's Cortex-A72 @ 1.5GHz. Expect noticeably lower FPS on the same detection model.
2. **Half the RAM, and no swap headroom to spare** — 1GB total has to cover the OS, Python, OpenCV, the loaded model, and Tesseract simultaneously.
3. **Older ISP** — the camera pipeline (libcamera) still works with Pi Camera Module 3, but confirm firmware is current (see Step 1).

None of this affects the ESP32-S3 side at all — the hard, sub-50ms braking safety layer runs entirely on the ESP32 and has zero dependency on Pi performance (`docs/ARCHITECTURE.md` design rule #1). A slow or even crashed Pi degrades the "sees a person" / "reads a sign" features, never the core hazard-braking claim. Keep that in mind if FPS numbers below feel underwhelming — the walker is still safe.

## Step 1 — OS setup

- Flash **Raspberry Pi OS Lite (64-bit)**, not the Desktop image — the Desktop environment alone can eat 150-250MB of your 1GB before you've run a single line of your own code. Work headless over SSH.
- In `raspi-config`: enable the camera interface, enable I2C/SPI if used, expand filesystem, and **update everything** (`sudo apt update && sudo apt full-upgrade`) — Camera Module 3 needs a reasonably current libcamera stack; on a 3B this matters more than on a 4, since older stock images are more likely to have stale camera firmware.
- Confirm the camera works before installing anything else:
  ```bash
  libcamera-hello --list-cameras
  libcamera-still -o test.jpg
  ```
  If this fails, fix it before touching Python — every "OpenCV can't open the camera" bug report is usually actually this.

## Step 2 — Give yourself swap room for installation (temporary)

Installing packages (even prebuilt wheels) can briefly spike memory during dependency resolution. Temporarily bump swap so `pip install` doesn't get OOM-killed partway through:

```bash
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

You can lower this back down after setup is done — running the actual pipeline shouldn't need to swap at all if you follow Step 4's resolution/frame-skip guidance; swapping during real-time inference will make things *much* slower, not save you.

## Step 3 — Install dependencies (use piwheels, don't compile from source)

Raspberry Pi OS's `pip` is preconfigured to pull from [piwheels.org](https://www.piwheels.org/), which hosts prebuilt ARM wheels for OpenCV and friends — a plain `pip install` should take a couple of minutes, not the hours a from-source build would take on a 3B:

```bash
sudo apt install python3-picamera2 --no-install-recommends
python3 -m venv --system-site-packages venv   # --system-site-packages is REQUIRED: picamera2 comes from apt
source venv/bin/activate
pip install -r vision/pi/requirements.txt
```

(`picamera2` is installed via `apt`, not `pip`, so it is linked against the system libcamera. A plain `python3 -m venv` cannot see apt-installed packages, so the venv must be created with `--system-site-packages` or `import picamera2` fails inside it.)

The default detector backend is TFLite (verified end-to-end against real weights), so also run:

```bash
pip install tflite-runtime   # piwheels has a prebuilt wheel for this on Pi OS
bash vision/pi/models/download_tflite_model.sh
```

If that `pip install` fails to find a wheel for your exact OS/Python combination, try `pip install ai-edge-litert` (Google's current packaging of the same runtime). The alternative `--detector-backend opencv-dnn` is **not** a ready fallback: it needs Caffe weights you must source yourself (see `vision/pi/models/download_models.sh`).

## Step 4 — The two flags that actually matter for performance

`vision/pi/src/main.py` has two flags built specifically for this situation:

```bash
python3 vision/pi/src/main.py \
  --camera picamera2 \
  --detector-backend tflite \
  --process-every-n-frames 3 \
  --width 320 --height 240 \
  --serial-port /dev/serial0
```

- **`--detector-backend tflite`** (already the default): a quantized (8-bit integer) MobileNet-SSD run through the TFLite runtime — meaningfully lighter on CPU and RAM than the same architecture in float form, which is what C3v in the learning roadmap means by "quantization explains your FPS target". On a laptop CPU it runs a 300x300 frame in roughly 25-35 ms; expect roughly an order of magnitude slower on a Pi 3B — measure it (Step 5) rather than trusting that estimate.
- **`--process-every-n-frames N`**: only runs the (expensive) detection model on every Nth frame — the camera keeps streaming and the fusion state machine still updates every frame using the most recent detection result, so the system stays responsive even though inference itself runs less often. Start at `3` and tune from there based on measured FPS (the on-screen FPS counter with `--preview`, or log it).
- Smaller `--width`/`--height` also directly reduces per-frame OpenCV overhead (resize, color conversion) independent of the detector backend.

## Step 5 — Measure, don't assume

The whole project's culture (see the learning roadmap's closing notes) is "report real numbers, not assumptions." Before trusting any of this for your final report:

```bash
python3 vision/pi/src/main.py --camera picamera2 --preview
```

Watch the on-screen FPS counter for at least a minute under realistic conditions, try the tflite backend and different `--process-every-n-frames` values, and log what you actually measured — including if it's disappointingly low. A working system at 3-4 FPS with an honest writeup beats an unverified claim of 12-15 FPS copied from the Pi 4-oriented research report.

## What NOT to bother with on a 3B

- Don't try to run Tesseract OCR on every frame regardless of backend choice — `vision/pi/src/ocr.py`'s `should_attempt_ocr()` trigger-condition gate already limits this to frames with a sign-like region, which matters even more here than on a Pi 4.
- Don't run the Desktop image "just to see the preview window" — SSH in and use `--preview` with X11 forwarding only for short debugging sessions, or better, run headless and log/photograph results instead.
- Don't install full `tensorflow` unless you've confirmed `tflite-runtime` genuinely isn't available for your setup — full TensorFlow is hundreds of MB and its own import overhead alone can be a meaningful chunk of your 1GB budget before you've processed a single frame.

## Adding the pothole detector (optional, costs extra CPU)

COCO-trained detectors know people and chairs but not potholes, stairs or curbs. The project trains its own ground-hazard model (see [`training/README.md`](../training/README.md)); once `vision/pi/models/hazard_yolov8n_320.onnx` exists, add it with:

```bash
python3 vision/pi/src/main.py --camera picamera2 --hazard-model --process-every-n-frames 4 --width 320 --height 240
```

It runs a second network on every processed frame, so on a Pi 3B raise `--process-every-n-frames` (potholes are static; at walking pace a result every ~1 s is still useful). It only ever produces a *warning* — a camera cannot measure distance, so braking stays the job of the ESP32's ToF/ultrasonic sensors.
