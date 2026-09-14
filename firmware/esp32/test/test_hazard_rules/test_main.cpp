// Host-native unit tests for src/safety/hazard_rules.h — no ESP32 or
// sensor hardware required. Run with: pio test -e native
#include <unity.h>

#include "../../src/safety/hazard_rules.h"

using namespace sensewalk::safety;

void setUp() {}
void tearDown() {}

static void test_no_target_reading_is_never_a_dropoff() {
    TEST_ASSERT_FALSE(isGroundDropoff(TOF_NO_TARGET, 300));
    TEST_ASSERT_FALSE(isGroundDropoff(500, TOF_NO_TARGET));
}

static void test_dropoff_requires_exceeding_threshold() {
    // baseline 300mm, threshold 150mm -> needs > 450mm to trigger
    TEST_ASSERT_FALSE(isGroundDropoff(440, 300));
    TEST_ASSERT_TRUE(isGroundDropoff(460, 300));
}

static void test_dropoff_false_when_current_below_baseline() {
    // A closer-than-baseline reading is not a drop-off (could be an object
    // in the beam path) — must not be misclassified as one.
    TEST_ASSERT_FALSE(isGroundDropoff(100, 300));
}

static void test_forward_obstacle_close() {
    TEST_ASSERT_TRUE(isForwardObstacleClose(TOF_FWD_HAZARD_MM - 1));
    TEST_ASSERT_FALSE(isForwardObstacleClose(TOF_FWD_HAZARD_MM));
    TEST_ASSERT_FALSE(isForwardObstacleClose(TOF_NO_TARGET));
}

static void test_ultrasonic_zero_is_no_echo_not_hazard() {
    TEST_ASSERT_FALSE(isUltrasonicClose(0));
}

static void test_ultrasonic_close_threshold() {
    TEST_ASSERT_TRUE(isUltrasonicClose(US_HAZARD_CM - 1));
    TEST_ASSERT_FALSE(isUltrasonicClose(US_HAZARD_CM));
}

static void test_grip_present_threshold() {
    TEST_ASSERT_TRUE(isGripPresent(GRIP_PRESENT_ADC_THRESHOLD));
    TEST_ASSERT_FALSE(isGripPresent(GRIP_PRESENT_ADC_THRESHOLD - 1));
}

static void test_confirm_twice_requires_consecutive_hits() {
    ConfirmTwice confirm(2);
    TEST_ASSERT_FALSE(confirm.isConfirmed());
    confirm.observe(true);
    TEST_ASSERT_FALSE(confirm.isConfirmed());  // only 1 so far
    confirm.observe(true);
    TEST_ASSERT_TRUE(confirm.isConfirmed());   // 2 consecutive
}

static void test_confirm_twice_resets_on_a_miss() {
    ConfirmTwice confirm(2);
    confirm.observe(true);
    confirm.observe(false);  // noise — resets the streak
    confirm.observe(true);
    TEST_ASSERT_FALSE(confirm.isConfirmed());  // only 1 consecutive since the reset
}

static void test_fall_requires_all_three_features() {
    FallFeatures dipOnly{100, 100, 0};
    FallFeatures full{100, 3000, 4000};
    TEST_ASSERT_FALSE(isFallDetected(dipOnly));
    TEST_ASSERT_TRUE(isFallDetected(full));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_no_target_reading_is_never_a_dropoff);
    RUN_TEST(test_dropoff_requires_exceeding_threshold);
    RUN_TEST(test_dropoff_false_when_current_below_baseline);
    RUN_TEST(test_forward_obstacle_close);
    RUN_TEST(test_ultrasonic_zero_is_no_echo_not_hazard);
    RUN_TEST(test_ultrasonic_close_threshold);
    RUN_TEST(test_grip_present_threshold);
    RUN_TEST(test_confirm_twice_requires_consecutive_hits);
    RUN_TEST(test_confirm_twice_resets_on_a_miss);
    RUN_TEST(test_fall_requires_all_three_features);
    return UNITY_END();
}
