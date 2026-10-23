// Host-native check of the ESP32-S3 pin map in include/config.h.
//
// The first draft of the map used classic-ESP32 pin numbers. On the ESP32-S3 several of
// those are wired to the flash/PSRAM chips (26-37), do not exist (22-25), or are the native
// USB pins (19, 20); driving them crashed the board in a reboot loop on real hardware.
// This test keeps that from coming back. Run with: pio test -e native
#include <unity.h>

#include "../../include/config.h"

void setUp() {}
void tearDown() {}

static const int kPins[] = {
    PIN_I2C_SDA, PIN_I2C_SCL, PIN_TOF_FWD_XSHUT, PIN_TOF_GND_XSHUT,
    PIN_US_L_TRIG, PIN_US_L_ECHO, PIN_US_C_TRIG, PIN_US_C_ECHO, PIN_US_R_TRIG, PIN_US_R_ECHO,
    PIN_GRIP_LEFT_ADC, PIN_GRIP_RIGHT_ADC, PIN_BRAKE_LEFT, PIN_BRAKE_RIGHT,
    PIN_HAPTIC_LEFT, PIN_HAPTIC_RIGHT, PIN_UART_RX2, PIN_UART_TX2,
};
static const int kCount = sizeof(kPins) / sizeof(kPins[0]);

static bool isForbidden(int p) {
    return p == 0 || p == 3 || p == 45 || p == 46 ||   // strapping pins
           p == 19 || p == 20 ||                        // native USB D-/D+
           (p >= 22 && p <= 37) ||                      // absent / flash / octal PSRAM
           p == 43 || p == 44;                          // UART0 (USB-serial debug)
}

static void test_no_pin_is_forbidden_on_esp32_s3() {
    for (int i = 0; i < kCount; i++) {
        TEST_ASSERT_FALSE_MESSAGE(isForbidden(kPins[i]), "a pin in config.h is unusable on the ESP32-S3");
        TEST_ASSERT_TRUE(kPins[i] >= 1 && kPins[i] <= 48);
    }
}

static void test_no_two_signals_share_a_pin() {
    for (int i = 0; i < kCount; i++)
        for (int j = i + 1; j < kCount; j++) TEST_ASSERT_NOT_EQUAL(kPins[i], kPins[j]);
}

static void test_grip_pins_are_adc1() {
    // ADC1 = GPIO1..10 on the S3.
    TEST_ASSERT_TRUE(PIN_GRIP_LEFT_ADC >= 1 && PIN_GRIP_LEFT_ADC <= 10);
    TEST_ASSERT_TRUE(PIN_GRIP_RIGHT_ADC >= 1 && PIN_GRIP_RIGHT_ADC <= 10);
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_no_pin_is_forbidden_on_esp32_s3);
    RUN_TEST(test_no_two_signals_share_a_pin);
    RUN_TEST(test_grip_pins_are_adc1);
    return UNITY_END();
}
