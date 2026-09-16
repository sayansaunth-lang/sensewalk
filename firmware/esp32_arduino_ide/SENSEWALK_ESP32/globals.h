// Shared hardware objects, instantiated once in globals.cpp and used by
// both the .ino (setup-time begin() calls) and tasks.cpp (the FreeRTOS
// task bodies). Kept in one place so it's obvious what state exists and
// who's allowed to touch it, rather than scattering globals across files.
#pragma once

#include "actuators_brake.h"
#include "actuators_haptics.h"
#include "safety_override.h"
#include "sensors_grip.h"
#include "sensors_imu.h"
#include "sensors_tof.h"
#include "sensors_ultrasonic.h"
#include "uart_link.h"

namespace sensewalk::globals {

extern sensors::ToFPair tof;
extern sensors::UltrasonicTrio ultrasonic;
extern sensors::GripPair grip;
extern sensors::Imu imu;
extern actuators::SolenoidBrake brake;
extern actuators::Haptics haptics;
extern comms::UartLink uartLink;
extern safety::SafetyOverride safetyOverride;

// Calls begin() on every hardware object in a safe order (I2C bus first).
// Returns false if any critical sensor fails to initialize — the .ino
// should refuse to start the safety task in that case rather than run with
// a silently-dead sensor.
bool beginAll();

}  // namespace sensewalk::globals
