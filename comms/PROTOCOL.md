# ESP32 <-> Raspberry Pi UART Protocol

_Owned by C3. Design this BEFORE either side writes protocol code — get C1 and C2 sign-off first (D1 in the learning roadmap)._

## Status: DRAFT — not yet agreed

## Physical layer

- Baud rate: **TBD** (both ends must match exactly — e.g. 115200)
- Wiring: ESP32 TX -> Pi RX, ESP32 RX -> Pi TX, common ground

## Message format

Pick one and delete the other once decided:

**Option A — comma-separated:**
```
<tag>,<value>,<timestamp>,<checksum>\n
```

**Option B — JSON-lines:**
```json
{"tag": "tof_fwd", "value": 42, "ts": 1234567, "chk": "a1b2"}
```

## Message tags (fill in as sensors come online)

| Tag | Direction | Meaning | Units |
|---|---|---|---|
| `tof_fwd` | ESP32 -> Pi | Forward ToF distance | mm |
| `tof_gnd` | ESP32 -> Pi | Ground/downward ToF distance | mm |
| `us_l` / `us_r` / `us_c` | ESP32 -> Pi | Ultrasonic left/right/center | cm |
| `imu` | ESP32 -> Pi | Orientation / accel summary | - |
| `brake_state` | ESP32 -> Pi | Brake engaged/disengaged | bool |
| `heartbeat` | ESP32 -> Pi | Liveness ping | - |

## Error handling rules

- The ESP32's hard safety override (brake engage on hazard threshold) **never** waits for a Pi acknowledgment — it must work even if the Pi is off or has rebooted.
- Define behavior for: dropped byte, partial message, Pi reboot mid-stream.

## Validation

Before any real sensor data flows through this link: ESP32 sends a fake value every 200ms, Pi logs it. Target: 1000 consecutive messages, near-zero drop/corruption rate. Log the result in `test/`.
