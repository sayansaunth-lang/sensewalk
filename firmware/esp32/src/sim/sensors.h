// Simulated-sensor scenario for bench demos with NO sensors attached.
//
// Enabled by defining SENSEWALK_SIM_SENSORS (uncomment the line in config.h, or
// build the *_SIM firmware that CI publishes). Only the sensor *readings* are
// faked: the real hazard rules, the safety override, the brake driver and the
// UART link all run exactly as on a walker. NOT for use on a real walker: it
// reports a clear path no matter what is in front of it.
//
// The scenario loops every 40 s so a demo can start at any moment.
#pragma once

#ifdef SENSEWALK_SIM_SENSORS

#include <Arduino.h>
#include <cstdint>

namespace sensewalk::sim {

struct Frame {
    uint16_t fwdMm;
    uint16_t gndMm;
    uint16_t usLeftCm;
    uint16_t usCenterCm;
    uint16_t usRightCm;
    int gripLeftRaw;
    int gripRightRaw;
    bool fall;
    uint8_t phaseId;
    const char* phase;
};

constexpr uint32_t kLoopMs = 40000;
constexpr uint16_t kClearFwdMm = 1500;
constexpr uint16_t kLevelGroundMm = 400;
constexpr uint16_t kClearUsCm = 200;
constexpr int kGripHeldRaw = 2000;  // above GRIP_PRESENT_ADC_THRESHOLD
constexpr int kGripOffRaw = 0;

inline Frame frameAt(uint32_t t) {
    Frame f{kClearFwdMm, kLevelGroundMm, kClearUsCm, kClearUsCm, kClearUsCm, kGripHeldRaw, kGripHeldRaw, false, 0,
            "clear path, hands on grips"};
    if (t < 4000) {
        // clear
    } else if (t < 7000) {
        // obstacle approaches: 1500 mm -> 150 mm over 3 s
        f.fwdMm = static_cast<uint16_t>(1500 - (1350UL * (t - 4000)) / 3000);
        f.phaseId = 1;
        f.phase = "obstacle approaching (forward ToF)";
    } else if (t < 9000) {
        f.fwdMm = 150;
        f.phaseId = 2;
        f.phase = "obstacle blocking, brake must hold";
    } else if (t < 11000) {
        f.phaseId = 3;
        f.phase = "obstacle removed, hands on grips -> brake may release";
    } else if (t < 14000) {
        f.phaseId = 4;
        f.phase = "clear path again";
    } else if (t < 18000) {
        // hands OFF the grips; ground drops away for 1 s, then returns
        f.gripLeftRaw = f.gripRightRaw = kGripOffRaw;
        if (t < 15000) f.gndMm = 700;
        f.phaseId = 5;
        f.phase = "hands off + drop-off ahead (brake must stay on even after ground returns)";
    } else if (t < 21000) {
        f.phaseId = 6;
        f.phase = "hands back on grips -> brake releases";
    } else if (t < 24000) {
        f.usLeftCm = 30;
        f.phaseId = 7;
        f.phase = "obstacle close on the left (ultrasonic)";
    } else if (t < 30000) {
        f.phaseId = 8;
        f.phase = "clear path";
    } else if (t < 30400) {
        f.gripLeftRaw = f.gripRightRaw = kGripOffRaw;
        f.fall = true;
        f.phaseId = 9;
        f.phase = "FALL (free-fall dip + impact + tilt)";
    } else if (t < 32000) {
        f.gripLeftRaw = f.gripRightRaw = kGripOffRaw;
        f.phaseId = 10;
        f.phase = "user on the ground, hands off";
    } else {
        f.phaseId = 11;
        f.phase = "recovered, hands back on grips";
    }
    return f;
}

inline Frame now() { return frameAt(millis() % kLoopMs); }

}  // namespace sensewalk::sim

#endif  // SENSEWALK_SIM_SENSORS
