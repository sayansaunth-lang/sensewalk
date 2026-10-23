// I2C wiring check — flash this when the full firmware says
// "VL53L1X ToF pair failed to initialize". It lists every device the ESP32-S3
// can hear on the SENSEWALK I2C pins (SDA=GPIO8, SCL=GPIO9, see docs/WIRING.md)
// and, as a hint for miswiring, on a few other common pin pairs.
//
// Expected addresses: 0x29 = VL53L1X (default, before the firmware renames it),
// 0x68 or 0x69 = MPU-6050. Nothing found = the wires or power are the problem,
// not the software.

#include <Wire.h>

constexpr int PIN_TOF_FWD_XSHUT = 4;
constexpr int PIN_TOF_GND_XSHUT = 5;

struct PinPair { int sda; int scl; const char* note; };
const PinPair PAIRS[] = {
    {8, 9, "SENSEWALK wiring (docs/WIRING.md)"},
    {9, 8, "SDA/SCL swapped"},
    {1, 2, "alternative"},
    {17, 18, "alternative"},
    {41, 42, "alternative"},
};

static const char* name_of(uint8_t a) {
    if (a == 0x29) return "VL53L1X (default address)";
    if (a == 0x30 || a == 0x31) return "VL53L1X (renamed by SENSEWALK firmware)";
    if (a == 0x68 || a == 0x69) return "MPU-6050 IMU";
    return "unknown device";
}

static int scan(int sda, int scl) {
    Wire.end();
    Wire.begin(sda, scl);
    Wire.setClock(100000);
    int found = 0;
    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        if (Wire.endTransmission() == 0) {
            Serial.printf("    found 0x%02X  %s\n", addr, name_of(addr));
            found++;
        }
    }
    return found;
}

void setup() {
    Serial.begin(115200);
    delay(1500);
    // Both XSHUT pins high so any connected VL53L1X is awake and answers at 0x29.
    pinMode(PIN_TOF_FWD_XSHUT, OUTPUT);
    pinMode(PIN_TOF_GND_XSHUT, OUTPUT);
    digitalWrite(PIN_TOF_FWD_XSHUT, HIGH);
    digitalWrite(PIN_TOF_GND_XSHUT, HIGH);
    delay(50);
}

void loop() {
    Serial.println("\n[SENSEWALK i2c scan]");
    int total = 0;
    for (const PinPair& p : PAIRS) {
        Serial.printf("  SDA=GPIO%d SCL=GPIO%d (%s)\n", p.sda, p.scl, p.note);
        int n = scan(p.sda, p.scl);
        if (n == 0) Serial.println("    nothing responded");
        total += n;
    }
    if (total == 0) {
        Serial.println("RESULT: no I2C device heard on any pin pair. Check sensor power (3.3V + GND) and that SDA/SCL wires are connected.");
    } else {
        Serial.println("RESULT: devices found. They must be on SDA=8/SCL=9 for the SENSEWALK firmware.");
    }
    delay(4000);
}
