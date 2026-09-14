#include "tasks.h"

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "config.h"
#include "globals.h"
#include "safety/hazard_rules.h"

namespace sensewalk::tasks {
namespace {

using namespace sensewalk::globals;

void safetyTask(void*) {
    const TickType_t period = pdMS_TO_TICKS(SENSOR_POLL_INTERVAL_MS);
    TickType_t lastWake = xTaskGetTickCount();
    for (;;) {
        tof.poll();
        grip.poll();

        bool changed = safetyOverride.update(tof, ultrasonic, grip, brake);
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
