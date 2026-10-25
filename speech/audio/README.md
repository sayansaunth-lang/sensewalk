# Voice clips

Pre-recorded alert voices, played by `speech/tts.py` instead of the synthesised voice. They were
supplied by the project team as MP3 files and converted to small mono 22.05 kHz WAV files (WAV plays
with no extra software on Windows and with `aplay` on the Raspberry Pi).

| File | What it says (transcribed with an offline speech model) | Played for phrase key(s) | Triggered by |
|---|---|---|---|
| `pothole_detected.wav` | "Alert. Pothole detected ahead. Reduce speed." | `pothole_ahead`, `ground_hazard_seen` | ToF drop-off (ESP32 braking) and the camera's pothole detector |
| `obstacle_warning.wav` | "Warning, obstacle detected ahead. Slow down." | `obstacle_close` | ultrasonic obstacle inside the brake distance |
| `road_clear.wav` | "Road ahead is clear." | `brake_released` | brake released after the hazard cleared and a hand is on the grip |
| `vehicle_ahead.wav` | "Caution. Vehicle detected ahead. Maintain safe distance." | `vehicle_ahead` | a car, bus, truck or motorcycle looks close in the camera |
| `person_ahead.wav` | "Caution. Person ahead." (**stand-in** made with the Windows "Microsoft David" voice; replace it with your own recording of the same name) | `person_close` | a person looks close in the camera |
| `traffic_ahead.wav` | "Traffic ahead. Drive carefully." | `traffic_ahead` | two or more vehicles in view |

Phrases without a clip (the fall-alert phrases, sign reading) still use the
text-to-speech voice. To give one of them a clip, add a WAV here and a line to `CLIP_FOR_PHRASE` in
`speech/clips.py`. If a clip file is missing or fails to play, the text-to-speech voice is used, so an
alert is never silent.

The recordings are the team's own material; check you are allowed to publish them before making this
repository public or reusing it elsewhere.
