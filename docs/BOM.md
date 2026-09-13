# Bill of Materials & Budget

Source: SENSEWALK Research Report, Aug 2026. Prices are Indian retail estimates (Robu.in, Quartz Components, Amazon.in) at time of writing — re-check before ordering.

## Core BOM

| Category | Component / Module | Qty | Unit Price (₹) | Total (₹) |
|---|---|---|---|---|
| Core Compute | Raspberry Pi 4 Model B (2GB) | 1 | 4,200 | 4,200 |
| Real-time MCU | ESP32-S3 Microcontroller Board | 1 | 450 | 450 |
| Visual Perception | Raspberry Pi Camera Module v3 (Wide) | 1 | 2,400 | 2,400 |
| Laser Ranging | VL53L1X Time-of-Flight Sensors | 2 | 450 | 900 |
| Sonar Proximity | HC-SR04 Ultrasonic Sensors | 3 | 70 | 210 |
| User Interface | Piezoelectric Thin-Film Load Sensors | 2 | 80 | 160 |
| Haptic Feedback | 1027 Coin Vibration Motors (L/R) | 2 | 40 | 80 |
| Fall Detection | MPU-6050 6-Axis Gyro & Accelerometer | 1 | 95 | 95 |
| Active Braking | 12V Solenoid Push-Pull Actuator Set | 2 | 650 | 1,300 |
| Location & Cellular | NEO-6M GPS + SIM800L GSM Module | 1 | 650 | 650 |
| Visual Safety | WS2812B Addressable RGB LED Strip (1m) | 1 | 220 | 220 |
| Power Unit | 12V 6000mAh Battery Pack + LM2596 Buck | 1 | 1,600 | 1,600 |
| Mechanical Frame | Aluminium/PVC Chassis + Wheels & Grips | 1 | 1,800 | 1,800 |
| | **Subtotal hardware** | | | **14,065** |
| | Miscellaneous (connectors, wires, 3D prints, fasteners) | | | 1,200 |
| | Contingency / buffer (~8%) | | | 1,200 |
| | **Original total estimate** | | | **16,465** |

## Additional components (easy to miss, required for a working prototype)

| Component | Why | Qty | Est. Cost (₹) |
|---|---|---|---|
| MicroSD Card (32GB, Class 10/A1) | Pi OS + OpenCV/OCR + logged data boot storage | 1 | 450 |
| Pi 4 Heatsink + Fan Kit | Prevents thermal throttling under sustained CV load | 1 | 350 |
| IRF520 MOSFET Driver Module | ESP32 GPIO can't switch 12V solenoids directly | 2 | 100 |
| 2N2222 NPN Transistor + Resistor | Drives coin vibration motors from GPIO | 2 | 10 |
| TP4056 Li-ion Charging/Protection Module | Safe recharge + over/under-voltage & short-circuit protection | 1 | 40 |
| GSM Antenna (SMA, spring type) | SIM800L needs one to acquire signal at all | 1 | 100 |
| GPS Active Antenna (SMA) | NEO-6M needs one to get a satellite fix | 1 | 200 |
| Micro SIM Card (SMS/data) | Consumable for SIM800L | 1 | 50 |
| Mini Speaker + PAM8403 Amplifier | Physical audio output for TTS | 1 | 150 |
| Rocker/Toggle Power Switch | Manual master on/off | 1 | 30 |
| In-line Fuse Holder + 3A Fuse | Overcurrent/short-circuit protection | 1 | 40 |
| Piezo Buzzer | Audible fallback if TTS fails/lags | 1 | 20 |
| Perfboard / Prototyping PCB | Vibration-resistant soldered wiring vs. breadboard | 2 | 80 |
| JST/Dupont Connector Kit + Heat-shrink | Serviceable wiring harness | 1 set | 150 |
| | **Additional subtotal** | | **1,770** |

## Revised total

Original estimate (₹16,465) + additional components (₹1,770) ≈ **₹18,235 all-in** — roughly ₹1,200–3,200 over the ₹15,000–17,000 target.

**To close the gap:** use a lower-capacity/cheaper microSD, a passive (fan-less) heatsink, and source the GSM/GPS antennas + SIM card locally rather than online.

## Procurement notes

- Order everything in Phase 1 (Days 1–10) — it's the critical-path blocker for every other phase.
- Read the actual datasheet for every part before ordering a substitute — pin/voltage mismatches are the #1 cause of "why did it just die."
