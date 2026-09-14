// HC-SR04 ultrasonic trio (left/center/right). B2 in the learning roadmap
// is explicit: "multiple ultrasonic sensors firing at once cause
// cross-talk — you must trigger them sequentially, not simultaneously."
// This class enforces that by constrution: poll() triggers and reads one
// sensor per call, round-robin, rather than exposing a single "read all"
// method that would tempt firing them together.
#pragma once

#include <Arduino.h>
#include <atomic>
#include <cstdint>

#include "config.h"

namespace sensewalk::sensors {

// Runs in its own FreeRTOS task (see tasks.cpp) because pulseIn() blocks
// for up to ~25ms on a timeout — too long to share a task with the
// time-critical safety loop. Readings are exposed via std::atomic so the
// safety task can read them lock-free from a different task/core.
class UltrasonicTrio {
public:
    void begin() {
        for (auto& ch : channels_) {
            pinMode(ch.trigPin, OUTPUT);
            pinMode(ch.echoPin, INPUT);
            digitalWrite(ch.trigPin, LOW);
        }
    }

    // Call once per SENSOR_POLL_INTERVAL_MS tick; internally advances to
    // the next sensor each call so all three get serviced across three
    // consecutive ticks without ever overlapping pulses.
    void poll() {
        Channel& ch = channels_[nextIndex_];
        ch.lastCm.store(readOnce(ch.trigPin, ch.echoPin), std::memory_order_relaxed);
        nextIndex_ = (nextIndex_ + 1) % 3;
    }

    uint16_t leftCm() const { return channels_[0].lastCm.load(std::memory_order_relaxed); }
    uint16_t centerCm() const { return channels_[1].lastCm.load(std::memory_order_relaxed); }
    uint16_t rightCm() const { return channels_[2].lastCm.load(std::memory_order_relaxed); }

private:
    struct Channel {
        int trigPin;
        int echoPin;
        std::atomic<uint16_t> lastCm{0};  // 0 = no echo yet / timeout, per hazard_rules.h convention
    };

    // 0 = no echo (timeout) — matches sensewalk::safety::isUltrasonicClose's
    // convention that a 0 reading is never treated as a hazard.
    static uint16_t readOnce(int trigPin, int echoPin) {
        digitalWrite(trigPin, LOW);
        delayMicroseconds(2);
        digitalWrite(trigPin, HIGH);
        delayMicroseconds(10);
        digitalWrite(trigPin, LOW);

        // 25ms timeout ~ 4.3m round trip, comfortably above the sensor's
        // rated range — bounds worst-case blocking time per sensor.
        unsigned long durationUs = pulseIn(echoPin, HIGH, 25000UL);
        if (durationUs == 0) return 0;  // timeout, no echo received

        // Speed of sound ~343 m/s at room temp -> 0.0343 cm/us, round trip
        // so divide by 2.
        return static_cast<uint16_t>((durationUs * 0.0343f) / 2.0f);
    }

    Channel channels_[3] = {
        {PIN_US_L_TRIG, PIN_US_L_ECHO},
        {PIN_US_C_TRIG, PIN_US_C_ECHO},
        {PIN_US_R_TRIG, PIN_US_R_ECHO},
    };
    uint8_t nextIndex_ = 0;
};

}  // namespace sensewalk::sensors
