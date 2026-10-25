# Wiring Reference

Pin assignments are defined once in [`firmware/esp32/include/config.h`](../firmware/esp32/include/config.h) — this document explains *why* each connection is made that way and cross-references the BOM component it drives. If this doc and `config.h` ever disagree, `config.h` is correct (it's what's actually compiled) — fix this doc, not the other way around.

## ESP32-S3 pin map

| Signal | Pin | Connects to | Notes |
|---|---|---|---|
| I2C SDA | GPIO8 | VL53L1X x2 (shared bus), MPU-6050 | Fast Mode 400kHz (see `globals.cpp`) |
| I2C SCL | GPIO9 | VL53L1X x2 (shared bus), MPU-6050 | |
| ToF forward XSHUT | GPIO4 | VL53L1X (forward-facing) | Held LOW at boot, then HIGH to bring the sensor up and reassign its address — see `sensors/tof.h` |
| ToF ground XSHUT | GPIO5 | VL53L1X (downward-facing) | Same XSHUT dance, brought up first |
| Ultrasonic L trig/echo | GPIO12 / GPIO13 | HC-SR04 (left) | |
| Ultrasonic C trig/echo | GPIO14 / GPIO15 | HC-SR04 (center) | |
| Ultrasonic R trig/echo | GPIO38 / GPIO39 | HC-SR04 (right) | Triggered sequentially, never simultaneously — see B2's cross-talk warning |
| Grip left (analog) | GPIO1 | Piezoelectric thin-film sensor (left handle) | ADC1 channel on the S3 (usable with no Wi-Fi conflict) |
| Grip right (analog) | GPIO2 | Piezoelectric thin-film sensor (right handle) | ADC1 channel |
| Brake left | GPIO40 | IRF520 MOSFET gate (left solenoid channel) | Active-HIGH: HIGH energises the solenoid |
| Brake right | GPIO41 | IRF520 MOSFET gate (right solenoid channel) | |
| Haptic left | GPIO21 | 2N2222 base (left vibration motor) | PWM via `ledcWrite`, 0-255 intensity |
| Haptic right | GPIO42 | 2N2222 base (right vibration motor) | |
| UART2 TX | GPIO17 | Pi GPIO15 (RXD) | |
| UART2 RX | GPIO16 | Pi GPIO14 (TXD) | |
| Common ground | — | Pi GND | **Non-negotiable** — a floating ground between the two boards is the single most common cause of a "flaky" UART link that looks like a software bug |

## Power chain

```
12V 6000mAh battery pack
  -> TP4056 (charge/discharge protection)
  -> in-line 3A fuse
  -> rocker power switch
  -> LM2596 buck converter -> 5V rail -> Raspberry Pi 4 (via USB-C or GPIO 5V, per LM2596 output wiring)
  -> 12V rail (unregulated, post-fuse) -> IRF520 MOSFET drain -> solenoids
  -> ESP32-S3 powered from its own onboard 5V/3.3V regulator, fed from the 5V rail (not directly from 12V)
```

**Before first power-on:** multimeter-check every rail against this diagram (S2 in the learning roadmap). Confirm the LM2596 output is actually trimmed to 5V (it's an adjustable buck converter, not fixed) before connecting the Pi — Pi 4 is not 12V-tolerant on its 5V rail and this is the single easiest way to destroy the board.

## Component-specific gotchas

See [`docs/DATASHEET_GOTCHAS.md`](DATASHEET_GOTCHAS.md) for the per-component "read this before wiring" notes (S3 in the learning roadmap) — SIM800L's current spike requirement in particular is not optional to skip.

## What still needs a real teammate's hands

This document describes the *intended* wiring from the BOM and firmware pin assignments. It has not been validated against physical breakout boards, which sometimes place XSHUT, address-select, or power pins differently than assumed here. M2 (Actuation & Power Systems Lead) should treat this as a first draft to check against the actual purchased breakouts' silkscreens/datasheets, not as verified fact.

## GPS (NEO-6M) and GSM (SIM800L) — connect these to the Pi through USB-serial adapters

The ESP32 link already uses the Pi's one usable hardware UART (`/dev/serial0`, GPIO14/15). A Raspberry Pi 3B has **no spare hardware UART** for the GPS and GSM modules, and bit-banged serial on a Pi is unreliable at the speeds these modules use. The plan that works:

| Module | Connects to | Port it appears as | Baud |
|---|---|---|---|
| ESP32-S3 | Pi GPIO14/15 (see table above) | `/dev/serial0` | 115200 |
| NEO-6M GPS | USB-to-TTL adapter (CP2102 or CH340, ~₹150) in a Pi USB port | `/dev/ttyUSB0` | 9600 |
| SIM800L GSM | a second USB-to-TTL adapter in another Pi USB port | `/dev/ttyUSB1` | 9600 |

Add **two USB-to-TTL adapters (about ₹300 total)** to the BOM — they are not in the original report. USB ports can swap numbering between boots when two identical adapters are plugged in; once both work, pin them with udev rules (or use `/dev/serial/by-id/...` paths) so the GPS never gets opened as the modem.

Wire each module's TX to the adapter's RX and RX to TX (crossed), and share ground.

**SIM800L power (non-negotiable):** its supply must be 3.4–4.4 V and able to deliver ~2 A in short bursts. Do **not** power it from the Pi's 5 V pin, the adapter, or any logic pin — the transmit burst browns it out and it resets mid-SMS. Feed it from the battery/buck rail through its own regulator (a ~1000 µF capacitor close to the module helps) and share ground with everything else. Its logic is 2.8 V tolerant on the RX line, so put a resistor divider or level shifter between the adapter's TX and the module's RX if the adapter outputs 3.3 V or 5 V.

**It is a 2G modem.** It only works where your carrier still operates a 2G (GSM 900/1800) network; some Indian carriers have retired it in many areas. Put your SIM in a phone first, force it to 2G, and confirm you get service where the walker will be used — otherwise `AT+CREG?` will never report registered and no code can fix that.

**GPS needs the sky.** The NEO-6M will not fix indoors and a cold start can take several minutes outdoors. Test it outside, early, not on demo day.

Check everything stage by stage with the bench script (it reports which stage failed):

```bash
python -m emergency.send_test_sms --gsm-port /dev/ttyUSB1 --gps-port /dev/ttyUSB0 --number +91XXXXXXXXXX
```

Then enable alerts in the main pipeline (numbers come from the environment so they never end up in the repository):

```bash
export SENSEWALK_EMERGENCY_NUMBERS="+91XXXXXXXXXX,+91YYYYYYYYYY"
python3 vision/pi/src/main.py --camera picamera2 --serial-port /dev/serial0 \
    --gsm-port /dev/ttyUSB1 --gps-port /dev/ttyUSB0
```

A detected fall starts a 10-second countdown ("Fall detected. Hold the handle to cancel the alert"); gripping the handle cancels it, otherwise the SMS with a map link is sent. Tune the window with `--fall-confirm-s`.


## ESP32-S3 camera board (on-board vision, no Pi or laptop)

The camera board (firmware `SENSEWALK_cam_main`) runs person and pothole detection by itself and tells the safety ESP32 to vibrate. It talks to the safety board over the same UART protocol the Pi uses, so the safety firmware needs no changes.

| Camera board | Safety ESP32-S3 | Notes |
|---|---|---|
| `kLinkTxPin` (default GPIO1) | GPIO16 (UART2 RX) | 3.3 V logic both sides |
| `kLinkRxPin` (default GPIO2) | GPIO17 (UART2 TX) | |
| GND | GND | common ground is required |
| `kI2sBclkPin` (default GPIO47) | MAX98357A **BCLK** | I2S bit clock |
| `kI2sLrcPin` (default GPIO21) | MAX98357A **LRC** | I2S word select |
| `kI2sDinPin` (default GPIO14) | MAX98357A **DIN** | I2S data |
| 5 V (from the power bank / the board's 5V pin) | MAX98357A **VIN** | powered from 5 V, **not** from a GPIO; keep leads short |
| GND | MAX98357A **GND** | |
| MAX98357A speaker terminals | 4-8 ohm speaker (about 3 W) | leave GAIN and SD unconnected (9 dB gain, (L+R)/2 mixing) |
| `kBuzzerPin` (default -1 = off) | optional piezo buzzer + lead (other lead to GND) | passive piezo, or an active buzzer through ~100 ohm |

**Confirm all the camera-board pins against your board's silkscreen before wiring.** They must not be used by the camera (4-13, 15-18), the flash/PSRAM, the USB-serial chip, the SD-card socket or the RGB LED (often GPIO48). The defaults are a guess; change `kLinkTxPin`, `kLinkRxPin`, `kI2sBclkPin`, `kI2sLrcPin`, `kI2sDinPin` and `kBuzzerPin` at the top of `SENSEWALK_cam_main.ino` if your board differs. The camera board is powered by its own USB-C supply (power bank); do not power it from the safety board's 3.3 V pin.

Behaviour: person confirmed -> `haptic,150|150` and the voice "Caution. Person ahead."; pothole confirmed -> `haptic,255|255` and "Alert. Pothole detected ahead. Reduce speed."; clear -> `haptic,0|0`. When the safety board reports `brake_state,1` the speaker says "Warning, obstacle detected ahead. Slow down."; on `brake_state,0` it says "Road ahead is clear." A more urgent clip cuts off a less urgent one. Send `v` over USB to play every clip once as a speaker test. The firmware needs the 16 MB flash layout (Flash Size 16MB, Partition Scheme "16M Flash (3MB APP/9.9MB FATFS)") because the voice clips are embedded (about 0.2 MB). The haptic frame is re-sent every 200 ms. Both are warnings only; braking stays with the safety board's distance sensors.
