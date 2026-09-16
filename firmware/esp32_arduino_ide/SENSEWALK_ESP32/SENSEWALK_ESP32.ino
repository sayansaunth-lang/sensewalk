// SENSEWALK ESP32-S3 firmware — Arduino IDE build.
//
// This is a flattened mirror of the PlatformIO project at firmware/esp32/
// (Arduino IDE requires every .h/.cpp to sit directly in the sketch folder
// — no subdirectories — so file names here use underscores instead of the
// PlatformIO project's folders: sensors_tof.h == firmware/esp32/src/sensors/tof.h,
// etc.) See ../README.md in this folder for setup instructions (board
// package, libraries, board settings) and firmware/esp32/README.md for the
// full design writeup.
//
// setup() brings up every sensor/actuator/link, then hands off entirely to
// FreeRTOS tasks (tasks.cpp) — loop() intentionally does almost nothing,
// since Arduino's default loop() runs at the lowest priority anyway and
// all real work belongs in the prioritised tasks described in
// docs/ARCHITECTURE.md.
#include <Arduino.h>

#include "config.h"
#include "globals.h"
#include "tasks.h"

void setup() {
    Serial.begin(115200);
    delay(200);  // let USB-serial enumerate before the first log line
    Serial.println("\n[SENSEWALK] ESP32-S3 firmware starting...");

    bool criticalSensorsOk = sensewalk::globals::beginAll();
    if (!criticalSensorsOk) {
        Serial.println("[SENSEWALK] FATAL: a critical sensor failed init. Halting rather than "
                        "running with a silently-dead ground/obstacle sensor.");
        while (true) {
            delay(1000);
        }
    }

    sensewalk::tasks::startAll();
    Serial.println("[SENSEWALK] All tasks started. Safety loop is live.");
}

void loop() {
    // Intentionally empty — see file header. vTaskDelay yields to the
    // scheduler instead of busy-spinning this lowest-priority default task.
    vTaskDelay(pdMS_TO_TICKS(1000));
}
