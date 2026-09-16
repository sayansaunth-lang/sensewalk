// Bring-up sanity check — has nothing to do with SENSEWALK's sensors.
// Flash this FIRST, before the full SENSEWALK_ESP32 sketch, to confirm:
//   1. Arduino IDE is talking to your ESP32-S3 (board + port selected right)
//   2. The board package / drivers are installed correctly
//   3. Serial monitor shows output at 115200 baud
//
// If this doesn't upload or you see no serial output, fix that first —
// the full firmware will be much harder to debug if the basic toolchain
// isn't working yet. This mirrors the learning roadmap's own B1 advice:
// "a single ESP32-S3 sketch running two FreeRTOS tasks... blink an LED at
// one rate while polling a button at another."
//
// Most ESP32-S3 dev boards have an onboard LED on GPIO2 or GPIO48 (varies
// by board) — change LED_PIN below if yours is elsewhere, or just watch
// the Serial Monitor output instead.

constexpr int LED_PIN = 2;

void setup() {
    Serial.begin(115200);
    delay(500);
    pinMode(LED_PIN, OUTPUT);
    Serial.println("\n[SENSEWALK blink test] ESP32-S3 is alive. If you can read this, your");
    Serial.println("Arduino IDE -> ESP32-S3 toolchain is working. Proceed to the full");
    Serial.println("SENSEWALK_ESP32 sketch once your sensors are wired per docs/WIRING.md.");
}

void loop() {
    digitalWrite(LED_PIN, HIGH);
    Serial.println("LED on");
    delay(500);
    digitalWrite(LED_PIN, LOW);
    Serial.println("LED off");
    delay(500);
}
