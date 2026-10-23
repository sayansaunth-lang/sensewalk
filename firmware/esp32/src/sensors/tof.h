// VL53L1X Time-of-Flight sensor pair: one forward-facing (obstacle), one
// downward-facing (ground/drop-off). Both share the I2C bus; since neither
// breakout exposes an alternate address pin, XSHUT is used at boot to bring
// them up one at a time and reassign the forward sensor to a non-default
// address (B2 in the learning roadmap).
#pragma once

#include "config.h"  // defines (or not) SENSEWALK_TOF_VL53L0X_FORWARD_ONLY
#ifdef SENSEWALK_TOF_VL53L0X_FORWARD_ONLY
#include <VL53L0X.h>
#else
#include <VL53L1X.h>
#endif
#include <cstdint>

#include "config.h"
#include "sim/sensors.h"
#include "safety/hazard_rules.h"

namespace sensewalk::sensors {

#ifndef SENSEWALK_TOF_VL53L0X_FORWARD_ONLY
class ToFPair {
public:
    // Call once from setup(), after Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL).
    bool begin() {
#ifdef SENSEWALK_SIM_SENSORS
        gndBaselineMm_ = sim::kLevelGroundMm;
        return true;  // no hardware: readings come from the simulated scenario
#endif
        pinMode(PIN_TOF_FWD_XSHUT, OUTPUT);
        pinMode(PIN_TOF_GND_XSHUT, OUTPUT);
        digitalWrite(PIN_TOF_FWD_XSHUT, LOW);
        digitalWrite(PIN_TOF_GND_XSHUT, LOW);
        delay(10);

        // Bring up the ground sensor first at its final (non-default) address.
        digitalWrite(PIN_TOF_GND_XSHUT, HIGH);
        delay(10);
        gnd_.setTimeout(500);
        if (!gnd_.init()) return false;
        gnd_.setAddress(TOF_GND_I2C_ADDR);

        // Then the forward sensor.
        digitalWrite(PIN_TOF_FWD_XSHUT, HIGH);
        delay(10);
        fwd_.setTimeout(500);
        if (!fwd_.init()) return false;
        fwd_.setAddress(TOF_FWD_I2C_ADDR);

        // Long-distance mode + a timing budget tuned for a device that must
        // scan both ground and forward obstacles without starving either
        // reading (B2: "ROI and timing budget settings ... matter for a
        // device scanning both ground and forward obstacles").
        for (VL53L1X* sensor : {&fwd_, &gnd_}) {
            sensor->setDistanceMode(VL53L1X::Long);
            sensor->setMeasurementTimingBudget(33000);  // 33ms budget per reading
            sensor->startContinuous(SENSOR_POLL_INTERVAL_MS);
        }

        // Establish an initial ground baseline immediately so the very
        // first hazard check isn't comparing against zero.
        gndBaselineMm_ = gnd_.read();
        return true;
    }

    // Call every SENSOR_POLL_INTERVAL_MS from the sensing task.
    void poll() {
#ifdef SENSEWALK_SIM_SENSORS
        {
            const sim::Frame f = sim::now();
            lastFwdMm_ = f.fwdMm;
            lastGndMm_ = f.gndMm;
            if (safety::isValidToFReading(f.gndMm)) {
                gndBaselineMm_ = static_cast<uint16_t>((gndBaselineMm_ * 15 + f.gndMm) / 16);
            }
            return;
        }
#endif
        if (fwd_.dataReady()) {
            lastFwdMm_ = fwd_.read() ? fwd_.ranging_data.range_mm : safety::TOF_NO_TARGET;
        }
        if (gnd_.dataReady()) {
            uint16_t reading = gnd_.read() ? gnd_.ranging_data.range_mm : safety::TOF_NO_TARGET;
            lastGndMm_ = reading;
            // Slowly track a rolling baseline for "normal" ground distance
            // so a sustained slope (ramp) doesn't get misread as a
            // drop-off — only a *sudden* increase should trigger.
            if (safety::isValidToFReading(reading)) {
                gndBaselineMm_ = static_cast<uint16_t>((gndBaselineMm_ * 15 + reading) / 16);
            }
        }
    }

    uint16_t forwardMm() const { return lastFwdMm_; }
    uint16_t groundMm() const { return lastGndMm_; }
    uint16_t groundBaselineMm() const { return gndBaselineMm_; }

private:
    VL53L1X fwd_;
    VL53L1X gnd_;
    uint16_t lastFwdMm_ = safety::TOF_NO_TARGET;
    uint16_t lastGndMm_ = safety::TOF_NO_TARGET;
    uint16_t gndBaselineMm_ = 0;
};
#else  // SENSEWALK_TOF_VL53L0X_FORWARD_ONLY

// Single VL53L0X, forward-facing only (for builds with just ONE proximity sensor).
// There is NO ground sensor in this configuration, so ground drop-off detection is
// disabled: groundMm() always reports "no target" and isGroundDropoff() can never fire.
// The forward obstacle brake works as normal, but only to ~1.2 m (VL53L0X), which is
// enough for the 300 mm brake threshold and not for early warning. Bench/prototype only.
class ToFPair {
public:
    bool begin() {
        pinMode(PIN_TOF_FWD_XSHUT, OUTPUT);
        pinMode(PIN_TOF_GND_XSHUT, OUTPUT);
        digitalWrite(PIN_TOF_GND_XSHUT, LOW);  // no ground sensor fitted
        digitalWrite(PIN_TOF_FWD_XSHUT, HIGH);
        delay(10);
        fwd_.setTimeout(500);
        if (!fwd_.init()) return false;
        fwd_.setMeasurementTimingBudget(33000);
        fwd_.startContinuous(SENSOR_POLL_INTERVAL_MS);
        Serial.println("[tof] VL53L0X forward-only mode: NO ground drop-off detection");
        return true;
    }

    void poll() {
        // Non-blocking: only read when the sensor has a fresh result, so the safety task never waits.
        if ((fwd_.readReg(VL53L0X::RESULT_INTERRUPT_STATUS) & 0x07) == 0) return;
        const uint16_t mm = fwd_.readRangeContinuousMillimeters();
        lastFwdMm_ = (fwd_.timeoutOccurred() || mm >= 8190) ? safety::TOF_NO_TARGET : mm;
    }

    uint16_t forwardMm() const { return lastFwdMm_; }
    uint16_t groundMm() const { return safety::TOF_NO_TARGET; }
    uint16_t groundBaselineMm() const { return 0; }

private:
    VL53L0X fwd_;
    uint16_t lastFwdMm_ = safety::TOF_NO_TARGET;
};

#endif  // SENSEWALK_TOF_VL53L0X_FORWARD_ONLY

}  // namespace sensewalk::sensors
