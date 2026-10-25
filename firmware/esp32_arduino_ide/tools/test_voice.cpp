// Host test: the board's mu-law decode matches the reference values from the Python encoder/decoder.
//   g++ -O2 -std=c++17 -I firmware/esp32_arduino_ide/SENSEWALK_cam_main firmware/esp32_arduino_ide/tools/test_voice.cpp -o /tmp/test_voice && /tmp/test_voice
#include <cstdio>

#include "voice.h"

int main() {
    using namespace sensewalk::voice;
    // Reference values produced by make_voice_header.ulaw2lin (standard G.711).
    const uint8_t in[] = {0x00, 0x10, 0x55, 0x7F, 0x80, 0xA5, 0xFF, 0xC3};
    const int16_t want[] = {-32124, -15996, -716, 0, 32124, 6652, 0, 1692};
    int bad = 0;
    for (unsigned i = 0; i < sizeof(in); i++) {
        if (ulawToLinear(in[i]) != want[i]) {
            std::printf("FAIL: 0x%02X -> %d, want %d\n", in[i], ulawToLinear(in[i]), want[i]);
            bad++;
        }
    }
    if (kClipCount != 4 || kClipLen[kClipPothole] < 1000 || kClipLen[kClipPerson] < 1000) {
        std::printf("FAIL: clip table looks wrong\n");
        bad++;
    }
    if (priorityOf(kClipObstacle) <= priorityOf(kClipPothole) || priorityOf(kClipPothole) <= priorityOf(kClipPerson) ||
        priorityOf(kClipPerson) <= priorityOf(kClipRoadClear)) {
        std::printf("FAIL: priority order\n");
        bad++;
    }
    std::printf(bad ? "FAIL\n" : "voice: mu-law decode and clip table OK\nPASS\n");
    return bad ? 1 : 0;
}
