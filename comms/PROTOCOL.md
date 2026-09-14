# ESP32 <-> Raspberry Pi UART Protocol

_Owned by C3. Implementations: [`comms/python/protocol.py`](python/protocol.py) (Pi side), [`firmware/esp32/src/comms/uart_link.h`](../firmware/esp32/src/comms/uart_link.h) (ESP32 side)._

## Status: AGREED (v1)

## Physical layer

- Baud rate: **115200 8N1**
- Wiring: ESP32 TX2 (GPIO17) -> Pi RX (GPIO15 / pin 10), ESP32 RX2 (GPIO16) -> Pi TX (GPIO14 / pin 8), common ground.
- Use the ESP32's second hardware UART (`Serial2`) — leave `Serial` (UART0) free for USB debug logging during bring-up.
- Pi side: disable the Linux serial console on `/dev/serial0` (`raspi-config` -> Interface Options -> Serial Port -> login shell **No**, hardware enabled **Yes**) or the OS will fight over the port.

## Message format — comma-separated (Option A)

Chosen over JSON-lines: no JSON library dependency needed on the ESP32 side, trivially fast to parse in both C++ and Python, and the message set is small and flat enough that JSON's self-description isn't worth the extra bytes-per-message on a 115200 baud link.

```
<tag>,<value>,<seq>,<checksum>\n
```

- `tag` — short ASCII identifier, see table below.
- `value` — integer or `|`-joined integers for multi-field tags (e.g. IMU). Always integers on the wire — floats are pre-scaled (e.g. accel in milli-g, distance in mm) so parsing never depends on locale/precision.
- `seq` — sender's monotonically increasing message counter (uint16, wraps at 65535). Used by the receiver to detect drops/reordering, *not* used for anything safety-critical.
- `checksum` — 8-bit XOR of every byte in `tag,value,seq` (before the trailing comma), rendered as 2 uppercase hex digits. Receiver recomputes and drops the line on mismatch.

Example line: `tof_gnd,812,104,41\n`

Max line length: 96 bytes including the newline. Anything longer is truncated by the receiver's line buffer and discarded (treated as a corrupt frame).

## Message tags

| Tag | Direction | Meaning | Value encoding |
|---|---|---|---|
| `tof_fwd` | ESP32 -> Pi | Forward ToF distance | mm, uint16 (65535 = out of range / no target) |
| `tof_gnd` | ESP32 -> Pi | Ground/downward ToF distance | mm, uint16 |
| `us_l` | ESP32 -> Pi | Ultrasonic left | cm, uint16 |
| `us_c` | ESP32 -> Pi | Ultrasonic center | cm, uint16 |
| `us_r` | ESP32 -> Pi | Ultrasonic right | cm, uint16 |
| `imu` | ESP32 -> Pi | Orientation summary | `pitch\|roll\|accel_mag` — pitch/roll in centidegrees (int16), accel_mag in milli-g (uint16) |
| `grip` | ESP32 -> Pi | Grip presence (both handles) | bitmask: bit0=left, bit1=right |
| `brake_state` | ESP32 -> Pi | Brake engaged/disengaged | 0=released, 1=engaged |
| `fall` | ESP32 -> Pi | Fall pre-check tripped on the MCU side | 0/1 — the Pi still runs D2's full fusion rule; this is a cheap early flag |
| `heartbeat` | ESP32 -> Pi | Liveness ping, fires every 200ms regardless of other traffic | free-running uptime counter, ms |
| `haptic` | Pi -> ESP32 | Command: drive left/right vibration motors | `left_intensity\|right_intensity`, 0-255 each |
| `say_done` | Pi -> ESP32 | Informational: Pi finished speaking an alert (lets ESP32 stop any redundant buzzer pattern tied to that alert) | alert_id, uint8 |

## Error handling rules

- **The ESP32's hard safety override never waits on this link.** Brake-engage on hazard threshold is decided and executed entirely in firmware (see `firmware/esp32/src/safety/override.*`); UART traffic is telemetry/commands layered on top, not a dependency.
- **Dropped/garbled byte:** receiver resyncs on the next `\n`; a line that fails checksum is discarded and counted, never partially applied.
- **Partial message (line split across reads):** both sides buffer until `\n` or the 96-byte cap, whichever comes first.
- **Pi reboot mid-stream:** ESP32 keeps running its own sensing/braking loop unconditionally; it simply queues/drops outbound messages (no blocking on a full buffer — see `uart_link.h` ring buffer). When the Pi comes back it resyncs on the next valid line, no handshake required.
- **ESP32 reset mid-stream:** Pi's `SerialLink` treats a >2s silence on `heartbeat` as "MCU link down", surfaces it to the fusion state machine, and keeps degraded vision-only operation running rather than crashing.

## Validation

Before any real sensor data flows through this link: ESP32 sends a fake `heartbeat` value every 200ms, Pi logs it. Target: 1000 consecutive messages, near-zero drop/corruption rate.

Run it with:

```bash
python3 comms/python/heartbeat_test.py --port /dev/serial0 --count 1000
```

which writes `test/logs/heartbeat_<timestamp>.csv` with per-message sequence/gap/checksum results and prints a pass/fail summary (see [`test/README.md`](../test/README.md)).
