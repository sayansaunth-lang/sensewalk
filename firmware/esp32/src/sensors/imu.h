// MPU-6050 6-axis IMU: raw accel/gyro streaming, a complementary filter for
// a stable orientation estimate, and a rolling window of features fed into
// safety::isFallDetected() (D2 in the learning roadmap).
//
// A complementary filter is used instead of a full Kalman filter
// deliberately — D2 notes it's "much simpler ... and good enough at this
// project level" for combining noisy accelerometer data with drifting
// gyro data.
#pragma once

#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <atomic>
#include <cmath>
#include <cstdint>

#include "config.h"
#include "safety/hazard_rules.h"

namespace sensewalk::sensors {

// Runs in its own FreeRTOS task (see tasks.cpp). All internal filter state
// is single-writer (only poll(), called from that one task, touches it);
// the public getters read from a set of std::atomic "published" copies
// updated at the end of every poll() so other tasks (comms, for telemetry;
// a fall-alert task) can read a consistent snapshot lock-free.
class Imu {
public:
    bool begin() {
        if (!mpu_.begin()) return false;
        mpu_.setAccelerometerRange(MPU6050_RANGE_8_G);
        mpu_.setGyroRange(MPU6050_RANGE_500_DEG);
        mpu_.setFilterBandwidth(MPU6050_BAND_21_HZ);
        lastUpdateMs_ = millis();
        return true;
    }

    // Call every SENSOR_POLL_INTERVAL_MS tick.
    void poll() {
        sensors_event_t accelEvent, gyroEvent, tempEvent;
        mpu_.getEvent(&accelEvent, &gyroEvent, &tempEvent);

        uint32_t now = millis();
        float dtSeconds = (now - lastUpdateMs_) / 1000.0f;
        lastUpdateMs_ = now;
        if (dtSeconds <= 0.0f || dtSeconds > 1.0f) dtSeconds = SENSOR_POLL_INTERVAL_MS / 1000.0f;

        // Accelerometer-derived pitch/roll (degrees) — noisy but drift-free.
        float accelPitch = std::atan2(accelEvent.acceleration.y,
                                       std::sqrt(accelEvent.acceleration.x * accelEvent.acceleration.x +
                                                 accelEvent.acceleration.z * accelEvent.acceleration.z)) *
                            (180.0f / static_cast<float>(M_PI));
        float accelRoll = std::atan2(-accelEvent.acceleration.x, accelEvent.acceleration.z) *
                           (180.0f / static_cast<float>(M_PI));

        // Gyro integration (deg/s -> deg) — drift-free short-term, drifts
        // over minutes, which is exactly what the accelerometer term below
        // corrects for.
        float gyroPitch = pitchDeg_ + gyroEvent.gyro.y * (180.0f / static_cast<float>(M_PI)) * dtSeconds;
        float gyroRoll = rollDeg_ + gyroEvent.gyro.x * (180.0f / static_cast<float>(M_PI)) * dtSeconds;

        // Complementary filter: mostly trust the (drift-free) gyro
        // short-term, slowly pull toward the (noisy but stable-average)
        // accelerometer estimate.
        constexpr float kAlpha = 0.98f;
        pitchDeg_ = kAlpha * gyroPitch + (1.0f - kAlpha) * accelPitch;
        rollDeg_ = kAlpha * gyroRoll + (1.0f - kAlpha) * accelRoll;

        float accelMagnitude = std::sqrt(
            accelEvent.acceleration.x * accelEvent.acceleration.x +
            accelEvent.acceleration.y * accelEvent.acceleration.y +
            accelEvent.acceleration.z * accelEvent.acceleration.z);
        // m/s^2 -> milli-g (1g = 9.80665 m/s^2)
        lastAccelMilliG_ = static_cast<uint16_t>((accelMagnitude / 9.80665f) * 1000.0f);

        updateFallWindow(now, lastAccelMilliG_);

        // Publish this cycle's results for lock-free cross-task reads.
        publishedPitchCentideg_.store(pitchCentidegInternal(), std::memory_order_relaxed);
        publishedRollCentideg_.store(rollCentidegInternal(), std::memory_order_relaxed);
        publishedAccelMilliG_.store(lastAccelMilliG_, std::memory_order_relaxed);
        publishedFallMin_.store(windowMinAccelMilliG_, std::memory_order_relaxed);
        publishedFallMax_.store(windowMaxAccelMilliG_, std::memory_order_relaxed);
        publishedFallOrientDelta_.store(windowOrientationDeltaCentideg_, std::memory_order_relaxed);
    }

    int16_t pitchCentideg() const { return publishedPitchCentideg_.load(std::memory_order_relaxed); }
    int16_t rollCentideg() const { return publishedRollCentideg_.load(std::memory_order_relaxed); }
    uint16_t accelMilliG() const { return publishedAccelMilliG_.load(std::memory_order_relaxed); }

    safety::FallFeatures fallFeatures() const {
        return {publishedFallMin_.load(std::memory_order_relaxed),
                publishedFallMax_.load(std::memory_order_relaxed),
                publishedFallOrientDelta_.load(std::memory_order_relaxed)};
    }

private:
    int16_t pitchCentidegInternal() const { return static_cast<int16_t>(pitchDeg_ * 100.0f); }
    int16_t rollCentidegInternal() const { return static_cast<int16_t>(rollDeg_ * 100.0f); }

    void updateFallWindow(uint32_t now, uint16_t accelMilliG) {
        if (now - windowStartMs_ > FALL_DETECT_WINDOW_MS) {
            windowStartMs_ = now;
            windowMinAccelMilliG_ = accelMilliG;
            windowMaxAccelMilliG_ = accelMilliG;
            windowStartPitchCentideg_ = pitchCentidegInternal();
            windowStartRollCentideg_ = rollCentidegInternal();
        } else {
            windowMinAccelMilliG_ = std::min(windowMinAccelMilliG_, accelMilliG);
            windowMaxAccelMilliG_ = std::max(windowMaxAccelMilliG_, accelMilliG);
        }
        int32_t pitchDelta = std::abs(pitchCentidegInternal() - windowStartPitchCentideg_);
        int32_t rollDelta = std::abs(rollCentidegInternal() - windowStartRollCentideg_);
        windowOrientationDeltaCentideg_ = static_cast<uint16_t>(pitchDelta + rollDelta);
    }

    Adafruit_MPU6050 mpu_;
    float pitchDeg_ = 0.0f;
    float rollDeg_ = 0.0f;
    uint16_t lastAccelMilliG_ = 1000;  // resting = ~1g
    uint32_t lastUpdateMs_ = 0;

    uint32_t windowStartMs_ = 0;
    uint16_t windowMinAccelMilliG_ = 1000;
    uint16_t windowMaxAccelMilliG_ = 1000;
    int16_t windowStartPitchCentideg_ = 0;
    int16_t windowStartRollCentideg_ = 0;
    uint16_t windowOrientationDeltaCentideg_ = 0;

    std::atomic<int16_t> publishedPitchCentideg_{0};
    std::atomic<int16_t> publishedRollCentideg_{0};
    std::atomic<uint16_t> publishedAccelMilliG_{1000};
    std::atomic<uint16_t> publishedFallMin_{1000};
    std::atomic<uint16_t> publishedFallMax_{1000};
    std::atomic<uint16_t> publishedFallOrientDelta_{0};
};

}  // namespace sensewalk::sensors
