# SENSEWALK Firmware — Arduino IDE Version

This is the same firmware as [`firmware/esp32/`](../esp32/), restructured to work in the Arduino IDE. **The PlatformIO project at `firmware/esp32/` is the canonical, CI-tested source** — this folder is a manually-kept-in-sync flat mirror for whoever on the team prefers the Arduino IDE. If you change the logic in one, mirror the change in the other.

Why two copies exist: Arduino IDE requires every `.h`/`.cpp` file to sit directly in the sketch folder — it does not compile files inside subdirectories the way PlatformIO does. So `firmware/esp32/src/sensors/tof.h` became `sensors_tof.h` here, `firmware/esp32/src/safety/override.h` became `safety_override.h`, etc. The logic inside every file is identical.

## Step 1 — Install Arduino IDE and the ESP32 board package

1. Install [Arduino IDE 2.x](https://www.arduino.cc/en/software) if you don't have it.
2. Open **File → Preferences**, and in "Additional boards manager URLs" add:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
3. Open **Tools → Board → Boards Manager**, search "esp32", install **"esp32 by Espressif Systems"** (latest version — this firmware supports both the v2.x and v3.x LEDC API via a compatibility check in `actuators_haptics.h`, so either major version should build).

## Step 2 — Install the required libraries

Open **Tools → Manage Libraries...** and install:

| Library | Author | Why |
|---|---|---|
| `VL53L1X` | Pololu | Time-of-flight distance sensors |
| `Adafruit MPU6050` | Adafruit | 6-axis IMU (fall detection) |

Installing "Adafruit MPU6050" will prompt to also install its dependencies — accept installing **"Adafruit Unified Sensor"** and **"Adafruit BusIO"** too.

## Step 3 — Board settings

1. Plug in your ESP32-S3 board via USB.
2. **Tools → Board →** select your exact board (commonly **"ESP32S3 Dev Module"** — check your board's silkscreen/listing if you have a specific one like "ESP32-S3-DevKitC-1").
3. **Tools → USB CDC On Boot →** set to **Enabled** (most ESP32-S3 boards need this to show Serial output over the native USB port — if you don't see output later and your board has a separate USB-to-UART chip instead, try Disabled).
4. **Tools → Port →** select the COM port that appeared when you plugged in the board.
5. Leave other settings (Flash Size, Partition Scheme, Upload Speed) at their defaults unless your specific board's documentation says otherwise.

## Step 4 — Verify the toolchain first (before wiring any sensors)

Open `SENSEWALK_blink_test/SENSEWALK_blink_test.ino` in Arduino IDE, click **Upload**, then open **Tools → Serial Monitor** at **115200 baud**. You should see it print and an LED blink every half-second. **Do this before the full firmware** — it isolates "is my IDE/board/port set up right" from "does the actual sensor code work", which matters a lot once you're debugging real wiring issues.

## Step 5 — Wire your sensors, then flash the full firmware

1. Wire everything per [`docs/WIRING.md`](../../docs/WIRING.md) and the pin assignments in `SENSEWALK_ESP32/config.h`. If your actual wiring uses different GPIO pins, **edit `config.h`** to match — don't rewire to match the code, the code is easier to change.
2. Open `SENSEWALK_ESP32/SENSEWALK_ESP32.ino` in Arduino IDE (this opens the whole sketch folder as tabs).
3. Click **Upload**.
4. Open the Serial Monitor at 115200 baud. On success you'll see:
   ```
   [SENSEWALK] ESP32-S3 firmware starting...
   [SENSEWALK] All tasks started. Safety loop is live.
   ```
   If instead you see `[globals] FATAL: VL53L1X ToF pair failed to initialize` followed by a halt, the two VL53L1X sensors aren't being detected on I2C — check wiring, the XSHUT pin connections, and I2C pull-up resistors (4.7kΩ SDA/SCL to 3.3V if your breakout boards don't already have them) before anything else.

## What this does NOT test

This firmware alone doesn't validate hazard-detection accuracy — it just brings the sensors online and wires the safety logic together. Once it's running:

- Check `docs/DATASHEET_GOTCHAS.md` and `docs/WIRING.md` for per-component wiring warnings before assuming a "no reading" is a code bug rather than a wiring one.
- Every threshold in `config.h` marked `TODO(calibrate)` is a placeholder — use `test/bench_logger.py` (from the Pi or a laptop connected to the ESP32's USB serial) to log real sensor readings and replace those numbers with measured ones, per the learning roadmap's B2/D2 modules.
- The Raspberry Pi side (`vision/`, `fusion/`, `speech/`, `comms/python/`) is a separate piece — this Arduino sketch only covers the ESP32 half of the system. See the main [README.md](../../README.md) for the whole picture.
