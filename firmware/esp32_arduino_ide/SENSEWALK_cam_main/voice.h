// Voice clips for the camera board: G.711 mu-law decoding and clip priorities.
// Plain C++ (no Arduino dependency) so the decode is host-tested; the I2S playback is in the sketch.
#pragma once

#include <cstdint>

#include "voice_clips.h"

namespace sensewalk::voice {

// Decode one 8-bit mu-law byte to a 16-bit sample (standard G.711).
inline int16_t ulawToLinear(uint8_t byte) {
    const int u = ~byte & 0xFF;
    int sample = (((u & 0x0F) << 3) + 0x84) << ((u & 0x70) >> 4);
    sample -= 0x84;
    return static_cast<int16_t>((u & 0x80) ? -sample : sample);
}

// Higher number = more urgent. A more urgent clip interrupts a less urgent one that is still playing.
inline int priorityOf(int clip) {
    switch (clip) {
        case kClipObstacle: return 4;   // the safety board has braked
        case kClipPothole: return 3;
        case kClipPerson: return 2;
        case kClipRoadClear: return 1;  // informational
        default: return 0;
    }
}

}  // namespace sensewalk::voice
