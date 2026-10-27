#include "tasks.h"

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "config.h"
#include "sim/sensors.h"
#include "globals.h"
#include "safety/hazard_rules.h"

namespace sensewalk::tasks {
namespace {

using namespace sensewalk::globals;

void safetyTask(void*) {
    const TickType_t period = pdMS_TO_TICKS(SENSOR_POLL_INTERVAL_MS);
    TickType_t lastWake = xTaskGetTickCount();
#ifdef SENSEWALK_SIM_SENSORS
    int lastPhaseId = -1;
#endif
    for (;;) {
        tof.poll();
        grip.poll();

        bool changed = safetyOverride.update(tof, ultrasonic, grip, brake);
#ifdef SENSEWALK_SIM_SENSORS
        {
            const sim::Frame f = sim::now();
            if (f.phaseId != lastPhaseId) {
                lastPhaseId = f.phaseId;
                Serial.printf("\n[sim] t=%lus  phase %u: %s\n",
                              static_cast<unsigned long>((millis() % sim::kLoopMs) / 1000),
                              static_cast<unsigned>(f.phaseId), f.phase);
            }
            if (changed) {
                Serial.printf("[sim] BRAKE %s  (fwd=%umm gnd=%umm usL=%ucm grips=%u, decision step %lu us)\n",
                              brake.isEngaged() ? "ENGAGED" : "released",
                              static_cast<unsigned>(tof.forwardMm()),
                              static_cast<unsigned>(tof.groundMm()),
                              static_cast<unsigned>(ultrasonic.leftCm()),
                              static_cast<unsigned>(grip.bitmask()),
                              static_cast<unsigned long>(safetyOverride.lastEngageLatencyUs()));
            }
        }
#endif
        if (changed) {
            uartLink.sendInt("brake_state", brake.isEngaged() ? 1 : 0);
            if (brake.isEngaged() && !safetyOverride.meetsLatencyBudget()) {
                // Logged, not acted on — the brake already engaged either
                // way (engage-first, complain-after). This is the honest
                // "report real measured numbers" instinct from the
                // learning roadmap applied to firmware, not just field tests.
                Serial.printf("[safety] WARNING: engage latency %lu us exceeded %lu ms budget\n",
                              static_cast<unsigned long>(safetyOverride.lastEngageLatencyUs()),
                              static_cast<unsigned long>(SAFETY_TASK_BUDGET_MS));
            }
        }
        if (brake.dutyCycleTripped()) {
            Serial.println("[safety] WARNING: solenoid duty-cycle limit hit, force-released");
            brake.clearDutyCycleFlag();
        }

        vTaskDelayUntil(&lastWake, period);
    }
}

void ultrasonicTask(void*) {
    const TickType_t period = pdMS_TO_TICKS(SENSOR_POLL_INTERVAL_MS);
    TickType_t lastWake = xTaskGetTickCount();
    for (;;) {
        ultrasonic.poll();
        vTaskDelayUntil(&lastWake, period);
    }
}

void imuTask(void*) {
    const TickType_t period = pdMS_TO_TICKS(SENSOR_POLL_INTERVAL_MS);
    TickType_t lastWake = xTaskGetTickCount();
    for (;;) {
        imu.poll();
        if (safety::isFallDetected(imu.fallFeatures())) {
            uartLink.sendInt("fall", 1);
#ifdef SENSEWALK_SIM_SENSORS
            {
                static uint32_t lastFallLogMs = 0;
                if (millis() - lastFallLogMs > 2000) {
                    lastFallLogMs = millis();
                    Serial.println("[sim] FALL detected by the real fall rule -> fall=1 sent to the Pi");
                }
            }
#endif
        }
        vTaskDelayUntil(&lastWake, period);
    }
}

void commsTask(void*) {
    const TickType_t period = pdMS_TO_TICKS(10);
    TickType_t lastWake = xTaskGetTickCount();
    uint32_t lastHeartbeatMs = 0;
    uint32_t lastTelemetryMs = 0;

    for (;;) {
        uartLink.poll();
        haptics.setIntensity(uartLink.lastHapticLeft(), uartLink.lastHapticRight());
        {
            // Log haptic commands from the camera board / Pi: on a change, and a count every 5 s.
            static uint32_t lastCount = 0;
            static uint8_t lastL = 0, lastR = 0;
            static uint32_t lastReportMs = 0;
            const uint32_t count = uartLink.hapticMessages();
            if (count != lastCount && (uartLink.lastHapticLeft() != lastL || uartLink.lastHapticRight() != lastR)) {
                Serial.printf("[comms] haptic command received: left=%u right=%u\n", uartLink.lastHapticLeft(),
                              uartLink.lastHapticRight());
            }
            lastCount = count;
            lastL = uartLink.lastHapticLeft();
            lastR = uartLink.lastHapticRight();
            if (millis() - lastReportMs > 5000) {
                lastReportMs = millis();
                Serial.printf("[comms] %lu haptic commands received so far (%lu raw bytes on the UART2 RX pin)\n",
                              static_cast<unsigned long>(count), static_cast<unsigned long>(uartLink.rawBytes()));
            }
        }

        uint32_t now = millis();
        if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
            lastHeartbeatMs = now;
            uartLink.sendInt("heartbeat", static_cast<long>(now));
        }

        // Telemetry at ~10Hz — plenty for the Pi's fusion logic, far below
        // what would risk saturating a 115200 baud link.
        if (now - lastTelemetryMs >= 100) {
            lastTelemetryMs = now;
            uartLink.sendInt("tof_fwd", tof.forwardMm());
            uartLink.sendInt("tof_gnd", tof.groundMm());
            uartLink.sendInt("us_l", ultrasonic.leftCm());
            uartLink.sendInt("us_c", ultrasonic.centerCm());
            uartLink.sendInt("us_r", ultrasonic.rightCm());
            uartLink.sendInt("grip", grip.bitmask());

            char imuValue[48];
            snprintf(imuValue, sizeof(imuValue), "%d|%d|%u", imu.pitchCentideg(), imu.rollCentideg(),
                      imu.accelMilliG());
            uartLink.send("imu", imuValue);
        }

        vTaskDelayUntil(&lastWake, period);
    }
}

}  // namespace

void startAll() {
    xTaskCreatePinnedToCore(safetyTask, "safety", kStackSizeWords, nullptr, kPrioritySafety, nullptr, 1);
    xTaskCreatePinnedToCore(ultrasonicTask, "ultrasonic", kStackSizeWords, nullptr, kPriorityUltrasonic, nullptr, 1);
    xTaskCreatePinnedToCore(imuTask, "imu", kStackSizeWords, nullptr, kPriorityImu, nullptr, 0);
    xTaskCreatePinnedToCore(commsTask, "comms", kStackSizeWords, nullptr, kPriorityComms, nullptr, 0);
}

}  // namespace sensewalk::tasks
