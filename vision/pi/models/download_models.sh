#!/usr/bin/env bash
# Downloads the pretrained Caffe MobileNet-SSD (VOC 20-class) model files
# used by vision/pi/src/detector.py. Model weights are gitignored
# (*.caffemodel) — run this once after cloning, on the Pi or any dev
# machine that will run detection.
set -euo pipefail
cd "$(dirname "$0")"

PROTOTXT_URL="https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/deploy.prototxt"
CAFFEMODEL_URL="https://github.com/chuanqi305/MobileNet-SSD/raw/master/mobilenet_iter_73000.caffemodel"

echo "Downloading MobileNet-SSD prototxt..."
curl -fL "$PROTOTXT_URL" -o MobileNetSSD_deploy.prototxt

echo "Downloading MobileNet-SSD caffemodel (~23MB)..."
curl -fL "$CAFFEMODEL_URL" -o MobileNetSSD_deploy.caffemodel

echo "Done. Verify with: python3 -c \"import cv2; cv2.dnn.readNetFromCaffe('MobileNetSSD_deploy.prototxt', 'MobileNetSSD_deploy.caffemodel')\""
