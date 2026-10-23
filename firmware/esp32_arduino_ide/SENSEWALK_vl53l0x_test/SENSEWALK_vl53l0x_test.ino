// Bench test for a VL53L0X time-of-flight sensor (the cheaper sibling of the
// VL53L1X the SENSEWALK firmware is written for; both answer at I2C 0x29).
// SENSEWALK_i2c_scan tells you which one you have. The VL53L0X reaches roughly
// 1.2 m reliably (the VL53L1X reaches about 4 m), so it is fine for bench
// checks but short for a walker's obstacle sensing.
//
// Wiring per docs/WIRING.md: SDA=GPIO8, SCL=GPIO9, 3.3V, GND.
// Requires the "VL53L0X" library by Pololu (Library Manager).

#include <Wire.h>
#include <VL53L0X.h>

constexpr int PIN_I2C_SDA = 8;
constexpr int PIN_I2C_SCL = 9;

VL53L0X sensor;
bool ok = false;

void start() {
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
    sensor.setTimeout(500);
    ok = sensor.init();
    if (!ok) {
        Serial.println("[vl53l0x test] init FAILED - run SENSEWALK_i2c_scan first");
        return;
    }
    sensor.startContinuous(100);
    Serial.println("[vl53l0x test] sensor OK. Printing distance in mm (8190+ = nothing in range).");
}

void setup() {
    Serial.begin(115200);
    delay(1500);
    start();
}

void loop() {
    if (!ok) { delay(2000); start(); return; }
    uint16_t mm = sensor.readRangeContinuousMillimeters();
    if (sensor.timeoutOccurred()) {
        Serial.println("[vl53l0x test] TIMEOUT");
    } else {
        Serial.printf("distance_mm=%u\n", mm);
    }
}
