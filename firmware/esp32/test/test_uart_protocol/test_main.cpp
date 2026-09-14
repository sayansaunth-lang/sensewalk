// Host-native unit tests for src/comms/uart_protocol.h. These must stay in
// lockstep with comms/python/tests/test_protocol.py — same wire format,
// same checksum algorithm, tested independently on each side.
// Run with: pio test -e native
#include <unity.h>

#include "../../src/comms/uart_protocol.h"

using namespace sensewalk::comms;

void setUp() {}
void tearDown() {}

static void test_encode_matches_documented_example() {
    char out[MAX_LINE_LEN];
    size_t len = encodeLine(out, sizeof(out), "tof_gnd", "812", 104);
    TEST_ASSERT_GREATER_THAN(0, len);
    TEST_ASSERT_EQUAL_STRING("tof_gnd,812,104,41\n", out);
}

static void test_decode_roundtrip() {
    char out[MAX_LINE_LEN];
    encodeLine(out, sizeof(out), "us_l", "37", 9);
    // strip trailing newline before decoding, matching how uart_link.h's
    // line assembler hands lines to decodeLine()
    out[strcspn(out, "\n")] = '\0';

    DecodedMessage msg = decodeLine(out);
    TEST_ASSERT_TRUE(msg.valid);
    TEST_ASSERT_EQUAL_STRING("us_l", msg.tag);
    TEST_ASSERT_EQUAL_STRING("37", msg.value);
    TEST_ASSERT_EQUAL_UINT16(9, msg.seq);
}

static void test_decode_rejects_bad_checksum() {
    DecodedMessage msg = decodeLine("tof_gnd,812,104,00");
    TEST_ASSERT_FALSE(msg.valid);
}

static void test_decode_rejects_wrong_field_count() {
    DecodedMessage msg = decodeLine("tof_gnd,812");
    TEST_ASSERT_FALSE(msg.valid);
}

static void test_decode_rejects_empty_tag() {
    DecodedMessage msg = decodeLine(",812,104,41");
    TEST_ASSERT_FALSE(msg.valid);
}

static void test_decode_rejects_non_numeric_seq() {
    DecodedMessage msg = decodeLine("tof_gnd,812,abc,41");
    TEST_ASSERT_FALSE(msg.valid);
}

static void test_multi_field_value_preserved_for_caller_to_split() {
    char out[MAX_LINE_LEN];
    encodeLine(out, sizeof(out), "imu", "120|-45|1023", 7);
    out[strcspn(out, "\n")] = '\0';

    DecodedMessage msg = decodeLine(out);
    TEST_ASSERT_TRUE(msg.valid);
    TEST_ASSERT_EQUAL_STRING("120|-45|1023", msg.value);
}

static void test_encode_rejects_oversized_line() {
    char out[MAX_LINE_LEN];
    char hugeValue[MAX_VALUE_LEN + 20];
    memset(hugeValue, 'x', sizeof(hugeValue) - 1);
    hugeValue[sizeof(hugeValue) - 1] = '\0';

    size_t len = encodeLine(out, sizeof(out), "tag", hugeValue, 1);
    TEST_ASSERT_EQUAL(0, len);
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_encode_matches_documented_example);
    RUN_TEST(test_decode_roundtrip);
    RUN_TEST(test_decode_rejects_bad_checksum);
    RUN_TEST(test_decode_rejects_wrong_field_count);
    RUN_TEST(test_decode_rejects_empty_tag);
    RUN_TEST(test_decode_rejects_non_numeric_seq);
    RUN_TEST(test_multi_field_value_preserved_for_caller_to_split);
    RUN_TEST(test_encode_rejects_oversized_line);
    return UNITY_END();
}
