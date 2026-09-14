// VL53L1X Time-of-Flight sensor pair: one forward-facing (obstacle), one
// downward-facing (ground/drop-off). Both share the I2C bus; since neither
// breakout exposes an alternate address pin, XSHUT is used at boot to bring
// them up one at a time and reassign the forward sensor to a non-default
// address (B2 in the learning roadmap).
#pragma once

#include <VL53L1X.h>
#include <cstdint>

#include "config.h"
#include "safety/hazard_rules.h"

namespace sensewalk::sensors {

class ToFPair {
public:
    // Call once from setup(), after Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL).
    bool begin() {
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

}  // namespace sensewalk::sensors
