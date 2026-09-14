#include "globals.h"

#include <Arduino.h>
#include <Wire.h>

#include "config.h"

namespace sensewalk::globals {

sensors::ToFPair tof;
sensors::UltrasonicTrio ultrasonic;
sensors::GripPair grip;
sensors::Imu imu;
actuators::SolenoidBrake brake;
actuators::Haptics haptics;
comms::UartLink uartLink;
safety::SafetyOverride safetyOverride;

bool beginAll() {
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
    Wire.setClock(400000);  // 400kHz I2C — VL53L1X and MPU-6050 both support Fast Mode

    bool ok = true;

    if (!tof.begin()) {
        Serial.println("[globals] FATAL: VL53L1X ToF pair failed to initialize");
        ok = false;
    }
    ultrasonic.begin();  // no I2C, cannot "fail" to init at this level
    grip.begin();

    if (!imu.begin()) {
        Serial.println("[globals] WARNING: MPU-6050 failed to initialize — fall detection disabled");
        // Non-fatal: the ground/obstacle safety path does not depend on the
        // IMU, so the walker can still operate safely without fall alerts.
    }

    brake.begin();
    haptics.begin();
    uartLink.begin();

    return ok;
}

}  // namespace sensewalk::globals
