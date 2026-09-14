# Phase 5 Field Test Plan

Owned by C4 (E2 in the learning roadmap). Written now, before field trials begin — not designed on the day, and not written retroactively from memory afterward.

## 1. Braking distance

**Question:** how far does the walker travel between hazard detection and full stop, at a normal walking pace?

- Fixed walking speed: mark a 3m approach lane, have the tester walk at a consistent, comfortable pace (practice runs until pace is consistent before recording).
- Trigger: a known obstacle or drop-off placed at a marked point.
- Measure: distance from the marked hazard point to where the front wheel actually stops, using a tape measure.
- **10+ trials minimum.** Record every trial individually — do not average in your head and discard the raw numbers.
- Report: mean, min, max, and standard deviation, not just the mean.

CSV schema: `trial_id,walking_speed_estimate_ms,braking_distance_cm,notes`

## 2. False-positive alert rate

**Question:** over normal, hazard-free walking, how often does the system falsely alert or brake?

- Route: a fixed, genuinely flat/obstacle-free indoor corridor of known length (e.g., 20m), walked at normal pace.
- **10+ full-length trials minimum**, ideally across different times of day / lighting conditions (vision false positives are lighting-sensitive).
- Count every alert (haptic, TTS, or brake engage) that fires with no real hazard present.
- Report: false positives per 100m walked, broken down by which sensor/subsystem triggered it (ToF / ultrasonic / vision) — this tells you which subsystem's threshold needs the most tuning.

CSV schema: `trial_id,route_length_m,false_alerts_count,false_alerts_by_source,lighting_condition`

## 3. Battery life

**Question:** how long does one charge last under realistic continuous use?

- Fully charge the battery pack, then run the system continuously (vision pipeline + firmware sensing active, walking or bench-simulated walking) until the low-voltage cutoff (TP4056 protection) trips.
- **At least 2 full-discharge trials** — one is not enough to catch pack-to-pack or ambient-temperature variance.
- Report: total runtime, and note whether the Pi or ESP32 side was the practical bottleneck (e.g., did the Pi thermal-throttle before the battery ran low?).

CSV schema: `trial_id,start_charge_pct,runtime_minutes,ambient_temp_c,notes`

## 4. Ground/obstacle detection accuracy

Already specified in detail in B2 of the learning roadmap and [`test/README.md`](README.md) — 50+ walks over a known hazard, 50+ over flat ground, analyzed with [`analyze_detection_log.py`](analyze_detection_log.py).

## 5. Fall detection accuracy

Already specified in D2 of the learning roadmap — 15+ controlled, padded, safe test drops, hit rate calculated by hand from the logged CSV (schema in `test/README.md`).

## 6. Demo rehearsal & defensive plan

A live demo has more failure points than any other part of the project. Before the final presentation:

- [ ] Full dry-run rehearsal, timed, at least once the day before.
- [ ] A backup pre-recorded video of a successful run, in case live hardware fails on the day.
- [ ] A second, pre-charged battery pack brought to the demo.
- [ ] A known-good demo route walked and confirmed the same day (lighting/surface conditions can shift overnight).
- [ ] Whoever is presenting has personally triggered every alert type (hazard brake, person-nearby, sign read, fall alert) at least once during rehearsal — not just watched someone else do it.

## Reporting rule

Every section above produces a CSV in `test/logs/` and a short written summary in the final report. Report the real numbers, including when they're worse than hoped — see the honesty note in `test/README.md`.
