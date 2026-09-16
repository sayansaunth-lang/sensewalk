// Left/right coin vibration motor drivers (via 2N2222 transistor stages),
// independently PWM-controlled (B3 in the learning roadmap). Intensity
// 0-255 matches comms/PROTOCOL.md's `haptic` command encoding.
//
// ESP32 Arduino core v3.x replaced the channel-based LEDC API
// (ledcSetup/ledcAttachPin/ledcWrite(channel,...)) with a pin-based one
// (ledcAttach/ledcWrite(pin,...)) — the #if below supports building against
// either core major version, since Arduino IDE's Boards Manager may offer
// either depending on when you install it.
#pragma once

#include <Arduino.h>
#include <cstdint>

#include "config.h"

namespace sensewalk::actuators {

class Haptics {
public:
    void begin() {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
        ledcAttach(PIN_HAPTIC_LEFT, kPwmFreqHz, kPwmResolutionBits);
        ledcAttach(PIN_HAPTIC_RIGHT, kPwmFreqHz, kPwmResolutionBits);
#else
        ledcSetup(kLeftChannel, kPwmFreqHz, kPwmResolutionBits);
        ledcSetup(kRightChannel, kPwmFreqHz, kPwmResolutionBits);
        ledcAttachPin(PIN_HAPTIC_LEFT, kLeftChannel);
        ledcAttachPin(PIN_HAPTIC_RIGHT, kRightChannel);
#endif
        setIntensity(0, 0);
    }

    void setIntensity(uint8_t leftIntensity, uint8_t rightIntensity) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
        ledcWrite(PIN_HAPTIC_LEFT, leftIntensity);
        ledcWrite(PIN_HAPTIC_RIGHT, rightIntensity);
#else
        ledcWrite(kLeftChannel, leftIntensity);
        ledcWrite(kRightChannel, rightIntensity);
#endif
        leftIntensity_ = leftIntensity;
        rightIntensity_ = rightIntensity;
    }

    void off() { setIntensity(0, 0); }

    uint8_t leftIntensity() const { return leftIntensity_; }
    uint8_t rightIntensity() const { return rightIntensity_; }

private:
    static constexpr int kLeftChannel = 4;    // only used on core v2.x's channel-based API
    static constexpr int kRightChannel = 5;   // only used on core v2.x's channel-based API
    static constexpr int kPwmFreqHz = 5000;
    static constexpr int kPwmResolutionBits = 8;  // matches 0-255 intensity range

    uint8_t leftIntensity_ = 0;
    uint8_t rightIntensity_ = 0;
};

}  // namespace sensewalk::actuators
