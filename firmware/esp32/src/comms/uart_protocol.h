// Wire-format codec for the ESP32<->Pi UART link. Mirrors
// comms/python/protocol.py exactly — see comms/PROTOCOL.md for the spec.
// Kept free of Arduino.h / HardwareSerial so it's host-testable via
// `pio test -e native`; uart_link.h wraps this with the actual Serial2
// I/O and FreeRTOS queueing.
#pragma once

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace sensewalk::comms {

constexpr size_t MAX_LINE_LEN = 96;
constexpr size_t MAX_TAG_LEN = 16;
constexpr size_t MAX_VALUE_LEN = 48;

// 8-bit XOR of every byte in "tag,value,seq" — must match
// comms/python/protocol.py's compute_checksum() bit for bit.
inline uint8_t computeChecksum(const char* tag, const char* value, uint16_t seq) {
    char payload[MAX_TAG_LEN + MAX_VALUE_LEN + 8];
    int len = std::snprintf(payload, sizeof(payload), "%s,%s,%u", tag, value, seq);
    uint8_t csum = 0;
    for (int i = 0; i < len; ++i) {
        csum ^= static_cast<uint8_t>(payload[i]);
    }
    return csum;
}

// Renders "<tag>,<value>,<seq>,<XX>\n" into `out` (caller-owned buffer of at
// least MAX_LINE_LEN bytes). Returns the number of bytes written (excluding
// the null terminator), or 0 if the encoded line would exceed MAX_LINE_LEN.
inline size_t encodeLine(char* out, size_t outCapacity, const char* tag, const char* value, uint16_t seq) {
    uint8_t checksum = computeChecksum(tag, value, seq);
    int len = std::snprintf(out, outCapacity, "%s,%s,%u,%02X\n", tag, value, seq, checksum);
    if (len < 0 || static_cast<size_t>(len) >= outCapacity || static_cast<size_t>(len) > MAX_LINE_LEN) {
        if (outCapacity > 0) out[0] = '\0';
        return 0;
    }
    return static_cast<size_t>(len);
}

struct DecodedMessage {
    char tag[MAX_TAG_LEN] = {0};
    char value[MAX_VALUE_LEN] = {0};
    uint16_t seq = 0;
    bool valid = false;
};

// Parses one line (WITHOUT the trailing '\n' — strip it before calling, see
// LineAssembler in uart_link.h). Sets result.valid = false on any
// malformed-field or checksum-mismatch condition, matching
// comms/python/protocol.py's MalformedLineError / ChecksumError split at
// the caller level (both just mean "drop this frame" per PROTOCOL.md).
inline DecodedMessage decodeLine(const char* line) {
    DecodedMessage result;

    char buf[MAX_LINE_LEN + 1];
    std::strncpy(buf, line, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';

    char* fields[4] = {nullptr, nullptr, nullptr, nullptr};
    int fieldCount = 0;
    char* cursor = buf;
    fields[fieldCount++] = cursor;
    while (*cursor != '\0' && fieldCount < 4) {
        if (*cursor == ',') {
            *cursor = '\0';
            fields[fieldCount++] = cursor + 1;
        }
        cursor++;
    }
    // Reject if there's a 5th field (extra comma) or fewer than 4 fields.
    if (fieldCount != 4 || strchr(fields[3], ',') != nullptr) {
        return result;  // valid = false
    }

    const char* tag = fields[0];
    const char* value = fields[1];
    const char* seqStr = fields[2];
    const char* checksumStr = fields[3];

    if (tag[0] == '\0' || value[0] == '\0' || checksumStr[0] == '\0') {
        return result;
    }
    if (std::strlen(tag) >= MAX_TAG_LEN || std::strlen(value) >= MAX_VALUE_LEN) {
        return result;
    }

    char* endptr = nullptr;
    long seqLong = std::strtol(seqStr, &endptr, 10);
    if (endptr == seqStr || *endptr != '\0' || seqLong < 0 || seqLong > 65535) {
        return result;
    }
    uint16_t seq = static_cast<uint16_t>(seqLong);

    uint8_t expected = computeChecksum(tag, value, seq);
    long providedLong = std::strtol(checksumStr, &endptr, 16);
    if (endptr == checksumStr || *endptr != '\0') {
        return result;
    }
    if (static_cast<uint8_t>(providedLong) != expected) {
        return result;
    }

    std::strncpy(result.tag, tag, MAX_TAG_LEN - 1);
    std::strncpy(result.value, value, MAX_VALUE_LEN - 1);
    result.seq = seq;
    result.valid = true;
    return result;
}

}  // namespace sensewalk::comms
