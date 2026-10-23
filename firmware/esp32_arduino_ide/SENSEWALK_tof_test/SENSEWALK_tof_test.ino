// Single VL53L1X bench test: prints live distance so you can verify one sensor
// before wiring the pair the full firmware needs. Flash after SENSEWALK_i2c_scan
// shows "found 0x29". Wave your hand / a book in front of the sensor and watch
// the numbers. Wiring per docs/WIRING.md: SDA=GPIO8, SCL=GPIO9, 3.3V, GND.
//
// This is a bring-up tool only. It does not replace the safety firmware.

#include <Wire.h>
#include <VL53L1X.h>

constexpr int PIN_I2C_SDA = 8;
constexpr int PIN_I2C_SCL = 9;
constexpr int PIN_TOF_FWD_XSHUT = 4;
constexpr int PIN_TOF_GND_XSHUT = 5;

VL53L1X sensor;
bool ok = false;

void setup() {
    Serial.begin(115200);
    delay(1500);
    pinMode(PIN_TOF_FWD_XSHUT, OUTPUT);
    pinMode(PIN_TOF_GND_XSHUT, OUTPUT);
    digitalWrite(PIN_TOF_FWD_XSHUT, HIGH);
    digitalWrite(PIN_TOF_GND_XSHUT, HIGH);
    delay(20);
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
    Wire.setClock(400000);
    sensor.setTimeout(500);
    ok = sensor.init();
    if (!ok) {
        Serial.println("[tof test] sensor.init() FAILED - run SENSEWALK_i2c_scan first");
        return;
    }
    sensor.setDistanceMode(VL53L1X::Long);
    sensor.setMeasurementTimingBudget(33000);
    sensor.startContinuous(50);
    Serial.println("[tof test] sensor OK. Printing distance in mm (4000+ or 0 = nothing in range).");
}

void loop() {
    if (!ok) { delay(1000); setup(); return; }
    uint16_t mm = sensor.read();
    if (sensor.timeoutOccurred()) {
        Serial.println("[tof test] TIMEOUT reading sensor");
    } else {
        Serial.printf("distance_mm=%u status=%d\n", mm, (int)sensor.ranging_data.range_status);
    }
    delay(100);
}
