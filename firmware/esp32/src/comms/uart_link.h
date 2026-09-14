// Hardware I/O wrapper around uart_protocol.h: owns Serial2, an incoming
// line assembler, an outgoing send queue (FreeRTOS queue, non-blocking —
// see the class comment below for why), and dispatches decoded `haptic` /
// `say_done` commands from the Pi.
//
// Per comms/PROTOCOL.md: this class is telemetry/commands layered on top
// of the safety loop, never a dependency of it. safety::SafetyOverride
// never calls into this class.
#pragma once

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

#include "comms/uart_protocol.h"
#include "config.h"

namespace sensewalk::comms {

struct OutgoingMessage {
    char tag[MAX_TAG_LEN];
    char value[MAX_VALUE_LEN];
};

class UartLink {
public:
    void begin() {
        Serial2.begin(UART_BAUD, SERIAL_8N1, PIN_UART_RX2, PIN_UART_TX2);
        // Small, fixed-size queue: if the Pi is down/slow and this fills
        // up, send() drops the oldest-style overflow rather than blocking
        // — a full outbound queue must never stall the caller (which may
        // be the safety task). See PROTOCOL.md: "the ESP32 side must never
        // depend on the Pi being alive."
        outgoingQueue_ = xQueueCreate(32, sizeof(OutgoingMessage));
    }

    // Non-blocking: enqueues for the UART task to actually write. Safe to
    // call from any task, including the safety task, without risking a
    // stall on a full/slow serial line.
    void send(const char* tag, const char* value) {
        if (outgoingQueue_ == nullptr) return;
        OutgoingMessage msg{};
        strncpy(msg.tag, tag, MAX_TAG_LEN - 1);
        strncpy(msg.value, value, MAX_VALUE_LEN - 1);
        xQueueSend(outgoingQueue_, &msg, 0);  // 0 timeout: never block
    }

    void sendInt(const char* tag, long value) {
        char buf[MAX_VALUE_LEN];
        snprintf(buf, sizeof(buf), "%ld", value);
        send(tag, buf);
    }

    // Call from the (low-priority) comms task: drains the outgoing queue
    // to the wire, and reads/decodes/dispatches whatever's arrived from the Pi.
    void poll() {
        OutgoingMessage outMsg;
        while (xQueueReceive(outgoingQueue_, &outMsg, 0) == pdTRUE) {
            char line[MAX_LINE_LEN];
            size_t len = encodeLine(line, sizeof(line), outMsg.tag, outMsg.value, seqOut_);
            if (len > 0) {
                Serial2.write(reinterpret_cast<const uint8_t*>(line), len);
                seqOut_ = (seqOut_ + 1) % 65536;
            }
        }

        while (Serial2.available() > 0) {
            char c = static_cast<char>(Serial2.read());
            if (c == '\n') {
                inBuf_[inBufLen_] = '\0';
                DecodedMessage msg = decodeLine(inBuf_);
                if (msg.valid) {
                    dispatch(msg);
                }
                inBufLen_ = 0;
            } else if (inBufLen_ < MAX_LINE_LEN - 1) {
                inBuf_[inBufLen_++] = c;
            } else {
                // Line too long without a newline — corrupt/oversized
                // frame, per PROTOCOL.md drop it and resync.
                inBufLen_ = 0;
            }
        }
    }

    uint8_t lastHapticLeft() const { return hapticLeft_; }
    uint8_t lastHapticRight() const { return hapticRight_; }

private:
    void dispatch(const DecodedMessage& msg) {
        if (strcmp(msg.tag, "haptic") == 0) {
            char valueCopy[MAX_VALUE_LEN];
            strncpy(valueCopy, msg.value, sizeof(valueCopy) - 1);
            valueCopy[sizeof(valueCopy) - 1] = '\0';
            char* sep = strchr(valueCopy, '|');
            if (sep != nullptr) {
                *sep = '\0';
                hapticLeft_ = static_cast<uint8_t>(atoi(valueCopy));
                hapticRight_ = static_cast<uint8_t>(atoi(sep + 1));
            }
        }
        // 'say_done' and any future Pi->ESP32 tags: extend here as needed.
    }

    QueueHandle_t outgoingQueue_ = nullptr;
    uint16_t seqOut_ = 0;

    char inBuf_[MAX_LINE_LEN];
    size_t inBufLen_ = 0;

    uint8_t hapticLeft_ = 0;
    uint8_t hapticRight_ = 0;
};

}  // namespace sensewalk::comms
