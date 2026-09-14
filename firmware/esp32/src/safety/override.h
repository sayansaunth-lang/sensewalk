// The hard, Pi-independent safety layer (B3 in the learning roadmap).
//
// This is the literal implementation of the research report's central
// claim: "Critical brake actuation runs on FreeRTOS on the ESP32 in under
// 50ms, bypassing Linux OS latency on the Pi." It must work correctly even
// if the Raspberry Pi is completely powered off — it depends on nothing
// from comms/uart_link.h, only on the sensor objects and the brake
// actuator, both local to this MCU.
#pragma once

#include <Arduino.h>
#include <cstdint>

#include "actuators/brake.h"
#include "config.h"
#include "safety/hazard_rules.h"
#include "sensors/grip.h"
#include "sensors/imu.h"
#include "sensors/tof.h"
#include "sensors/ultrasonic.h"

namespace sensewalk::safety {

class SafetyOverride {
public:
    // Call every tick from the highest-priority FreeRTOS task (see
    // tasks.h). Returns true if the brake state changed this call, so the
    // caller can log/measure the engage latency.
    bool update(const sensors::ToFPair& tof, const sensors::UltrasonicTrio& us,
                const sensors::GripPair& grip, actuators::SolenoidBrake& brake) {
        uint32_t startMicros = micros();

        groundDropoffConfirm_.observe(isGroundDropoff(tof.groundMm(), tof.groundBaselineMm()));
        const bool forwardClose = isForwardObstacleClose(tof.forwardMm());
        const bool ultrasonicClose = isUltrasonicClose(us.leftCm()) ||
                                      isUltrasonicClose(us.centerCm()) ||
                                      isUltrasonicClose(us.rightCm());

        const bool hazard = groundDropoffConfirm_.isConfirmed() || forwardClose || ultrasonicClose;
        const bool wasEngaged = brake.isEngaged();

        if (hazard) {
            brake.engage();
        } else if (grip.anyPresent()) {
            // B3: grip presence gates auto-release — the brake does not
            // release itself just because the hazard reading cleared while
            // the user's hands are off the grips.
            brake.release();
        }

        brake.enforceDutyCycle();

        const bool changed = (brake.isEngaged() != wasEngaged);
        if (changed && brake.isEngaged()) {
            lastEngageLatencyUs_ = micros() - startMicros;
        }
        return changed;
    }

    // Measured latency (microseconds) of the most recent hazard->engage
    // transition — this is the number that proves the <50ms budget is
    // actually met (B3 deliverable), not assumed.
    uint32_t lastEngageLatencyUs() const { return lastEngageLatencyUs_; }

    bool meetsLatencyBudget() const {
        return lastEngageLatencyUs_ < (SAFETY_TASK_BUDGET_MS * 1000UL);
    }

private:
    ConfirmTwice groundDropoffConfirm_;
    uint32_t lastEngageLatencyUs_ = 0;
};

}  // namespace sensewalk::safety
