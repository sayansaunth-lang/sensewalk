// FreeRTOS task creation and priority assignment (B1 in the learning
// roadmap: "running sensor polling and brake actuation as separate
// prioritised tasks avoids one slow sensor blocking the brake response").
//
// Priority scheme (higher number = higher priority, matches FreeRTOS
// convention as used by the Arduino-ESP32 core):
//
//   5  Safety     — ToF + grip polling (fast, non-blocking) + hard brake
//                   override. Must never be starved.
//   3  Ultrasonic — pulseIn() blocks up to ~25ms; isolated so it can never
//                   delay the safety task.
//   2  Imu        — MPU-6050 polling + fall-window feature tracking.
//   1  Comms      — UART telemetry/commands to the Pi; lowest priority
//                   because it is explicitly non-critical (see
//                   comms/PROTOCOL.md).
#pragma once

namespace sensewalk::tasks {

constexpr int kPrioritySafety = 5;
constexpr int kPriorityUltrasonic = 3;
constexpr int kPriorityImu = 2;
constexpr int kPriorityComms = 1;

constexpr int kStackSizeWords = 4096;

// Creates and starts every task. Call once from setup(), after all
// sensor/actuator/link begin() calls have already succeeded.
void startAll();

}  // namespace sensewalk::tasks
