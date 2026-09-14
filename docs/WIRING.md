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
| Ultrasonic C trig/echo | GPIO14 / GPIO27 | HC-SR04 (center) | |
| Ultrasonic R trig/echo | GPIO26 / GPIO25 | HC-SR04 (right) | Triggered sequentially, never simultaneously — see B2's cross-talk warning |
| Grip left (analog) | GPIO34 | Piezoelectric thin-film sensor (left handle) | Input-only ADC pin on most ESP32 variants — confirm this is valid on the specific S3 dev board purchased |
| Grip right (analog) | GPIO35 | Piezoelectric thin-film sensor (right handle) | Same caveat |
| Brake left | GPIO32 | IRF520 MOSFET gate (left solenoid channel) | Active-HIGH: HIGH energises the solenoid |
| Brake right | GPIO33 | IRF520 MOSFET gate (right solenoid channel) | |
| Haptic left | GPIO21 | 2N2222 base (left vibration motor) | PWM via `ledcWrite`, 0-255 intensity |
| Haptic right | GPIO19 | 2N2222 base (right vibration motor) | |
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
