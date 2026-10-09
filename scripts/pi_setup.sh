#!/usr/bin/env bash
# One-command setup of the SENSEWALK vision/AI software on a Raspberry Pi.
#
# Run this ON the Pi (over SSH, or with a keyboard and screen):
#
#     curl -fsSL https://raw.githubusercontent.com/sayansaunth-lang/sensewalk/master/scripts/pi_setup.sh | bash
#   or, if you already cloned the repo:
#     bash scripts/pi_setup.sh
#
# What it does, in order. It stops at the first real failure and says which step failed:
#   1. installs system packages (git, camera library, Tesseract OCR, speech engine)
#   2. clones the repo (or updates it)
#   3. creates a Python venv WITH --system-site-packages (needed so picamera2 is importable)
#   4. installs Python packages + the TFLite runtime
#   5. downloads the people/object model (checksum-verified)
#   6. verifies the pothole model arrived intact (SHA-256) and that both models load
#   7. checks the camera is detected
#
# Safe to re-run. It never touches your SD card, Wi-Fi, or system settings beyond apt packages.
set -euo pipefail

REPO_URL="https://github.com/sayansaunth-lang/sensewalk"
DEST="${SENSEWALK_DIR:-$HOME/sensewalk}"
# SHA-256 of vision/pi/models/hazard_yolov8n_320.onnx as committed. Update this if you retrain
# and commit a new model (the script tells you the new value when it differs).
HAZARD_SHA256="e779e4ad08ccaec35e1c5d6ac2db168ecdf53d0c68f5227f4b28abc6e797150c"

STEP=0
step() { STEP=$((STEP + 1)); echo; echo "==> [$STEP/7] $*"; }
fail() { echo; echo "FAILED at step $STEP: $*" >&2; exit 1; }
trap 'echo; echo "Setup stopped at step $STEP. Fix the error above and re-run this script (it is safe to re-run)." >&2' ERR

if [ "$(id -u)" -eq 0 ]; then
  fail "do not run as root/sudo. Run as your normal user; the script calls sudo only where needed."
fi

echo "SENSEWALK Pi setup"
echo "  Pi model : $(tr -d '\0' </proc/device-tree/model 2>/dev/null || echo unknown)"
echo "  OS       : $(. /etc/os-release && echo "$PRETTY_NAME") ($(uname -m))"
echo "  RAM      : $(awk '/MemTotal/ {printf "%.0f MB", $2/1024}' /proc/meminfo)"
echo "  Install  : $DEST"

step "System packages (this needs internet and can take a few minutes)"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  git curl unzip python3-venv python3-pip python3-picamera2 \
  tesseract-ocr espeak-ng

step "Get the code"
if [ -d "$DEST/.git" ]; then
  git -C "$DEST" pull --ff-only
else
  git clone "$REPO_URL" "$DEST"
fi
cd "$DEST"

step "Python environment (venv with --system-site-packages: picamera2 comes from apt)"
python3 -m venv --system-site-packages venv
# shellcheck disable=SC1091
source venv/bin/activate
python -m pip install --upgrade pip

step "Python packages (OpenCV, OCR, serial, speech, TFLite runtime)"
pip install -r vision/pi/requirements.txt
if ! pip install tflite-runtime; then
  echo "tflite-runtime has no wheel for this OS/Python; trying ai-edge-litert instead..."
  pip install ai-edge-litert || fail "could not install a TFLite runtime (tflite-runtime or ai-edge-litert)"
fi

step "People/object model (downloaded, checksum-verified)"
bash vision/pi/models/download_tflite_model.sh

step "Verify the AI models"
actual="$(sha256sum vision/pi/models/hazard_yolov8n_320.onnx | cut -d' ' -f1)"
if [ "$actual" != "$HAZARD_SHA256" ]; then
  echo "Pothole model checksum differs from the one in this script:" >&2
  echo "  expected $HAZARD_SHA256" >&2
  echo "  got      $actual" >&2
  echo "If you retrained and committed a new model on purpose, update HAZARD_SHA256 in this script." >&2
  echo "If not, the file is corrupt: delete it and run 'git checkout vision/pi/models/hazard_yolov8n_320.onnx'." >&2
  fail "pothole model checksum mismatch"
fi
echo "pothole model checksum OK"

python - <<'PY'
import sys
import cv2
major, minor = (int(x) for x in cv2.__version__.split(".")[:2])
print("OpenCV", cv2.__version__)
if (major, minor) < (4, 8):
    sys.exit("OpenCV is older than 4.8 and cannot read the pothole model. Run: pip install -U opencv-python-headless")
from vision.pi.src.detector import TFLiteSSDDetector, YoloOnnxDetector
TFLiteSSDDetector()
YoloOnnxDetector()
print("both AI models load OK")
PY

step "Camera check"
CAM_CMD=""
for c in rpicam-hello libcamera-hello; do
  if command -v "$c" >/dev/null 2>&1; then CAM_CMD="$c"; break; fi
done
if [ -n "$CAM_CMD" ]; then
  if "$CAM_CMD" --list-cameras 2>&1 | grep -qiE "^[0-9]+ *:"; then
    "$CAM_CMD" --list-cameras 2>&1 | head -6
    echo "camera detected"
  else
    echo "WARNING: no camera detected. Power off, reseat the ribbon cable (contacts facing the right way, both ends)," >&2
    echo "         and check 'sudo apt full-upgrade' has been run. The software installed fine; this is a hardware/OS issue." >&2
  fi
else
  echo "WARNING: rpicam-hello/libcamera-hello not found; run 'sudo apt full-upgrade' and re-run." >&2
fi

echo
echo "=============================================================="
echo "Setup finished. Next, measure real speed on THIS Pi (no screen needed):"
echo "    cd $DEST && source venv/bin/activate"
echo "    python3 vision/pi/src/benchmark.py"
echo
echo "Then run the pipeline with simulated sensors (no ESP32 needed yet):"
echo "    python3 vision/pi/src/main.py --camera picamera2 --sim --hazard-model \\"
echo "        --process-every-n-frames 4 --width 320 --height 240"
echo "=============================================================="
