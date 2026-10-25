// Inference for the tiny pothole classifier (weights in pothole_weights.h, trained by
// training/tiny_pothole/train_tiny_pothole.py). Plain C++ with no library or Arduino dependency, so
// the same code runs on the ESP32-S3 camera board and in the host test that proves it matches PyTorch.
//
//   input : 64x64 8-bit grayscale view (row-major), normalised inside as (pixel - 128) / 128
//   output: probability that the view contains a pothole
//
// This answers "is there a pothole in this view?", not where. See training/tiny_pothole/README.md
// for the measured accuracy and its limits.
#pragma once

#include <cmath>
#include <cstdint>

#include "pothole_weights.h"

namespace sensewalk::pothole {

constexpr int kInputSize = 64;

namespace detail {

// 3x3 convolution, stride 2, zero padding 1, ReLU. Layouts: input/output HWC, weights [out][ky][kx][in].
inline void conv3x3s2(const float* in, int inH, int inW, int inC, const float* w, const float* b, int outC, float* out) {
    const int outH = (inH + 2 - 3) / 2 + 1;
    const int outW = (inW + 2 - 3) / 2 + 1;
    for (int oy = 0; oy < outH; oy++) {
        for (int ox = 0; ox < outW; ox++) {
            float* dst = out + (oy * outW + ox) * outC;
            for (int oc = 0; oc < outC; oc++) {
                float acc = b[oc];
                const float* wk = w + oc * 9 * inC;
                for (int ky = 0; ky < 3; ky++) {
                    const int iy = oy * 2 - 1 + ky;
                    if (iy < 0 || iy >= inH) continue;
                    for (int kx = 0; kx < 3; kx++) {
                        const int ix = ox * 2 - 1 + kx;
                        if (ix < 0 || ix >= inW) continue;
                        const float* src = in + (iy * inW + ix) * inC;
                        const float* wp = wk + (ky * 3 + kx) * inC;
                        for (int ic = 0; ic < inC; ic++) acc += src[ic] * wp[ic];
                    }
                }
                dst[oc] = acc > 0.0f ? acc : 0.0f;
            }
        }
    }
}

}  // namespace detail

// Two logits: [no pothole, pothole].
struct Logits {
    float no_pothole;
    float pothole;
};

inline Logits run(const uint8_t* gray64) {
    // Largest activation is 32x32xC1; static so a 100 KB array never lands on a task stack.
    static float bufA[(kInputSize / 2) * (kInputSize / 2) * kC1];
    static float bufB[(kInputSize / 4) * (kInputSize / 4) * kC2];
    static float input[kInputSize * kInputSize];
    for (int i = 0; i < kInputSize * kInputSize; i++) input[i] = (static_cast<float>(gray64[i]) - 128.0f) / 128.0f;

    detail::conv3x3s2(input, 64, 64, 1, kW1, kB1, kC1, bufA);   // -> 32x32xC1
    detail::conv3x3s2(bufA, 32, 32, kC1, kW2, kB2, kC2, bufB);  // -> 16x16xC2
    detail::conv3x3s2(bufB, 16, 16, kC2, kW3, kB3, kC3, bufA);  // -> 8x8xC3
    detail::conv3x3s2(bufA, 8, 8, kC3, kW4, kB4, kC4, bufB);    // -> 4x4xC4

    float pooled[kC4];
    for (int c = 0; c < kC4; c++) {
        float sum = 0.0f;
        for (int p = 0; p < 16; p++) sum += bufB[p * kC4 + c];
        pooled[c] = sum / 16.0f;
    }
    float logit[2];
    for (int o = 0; o < 2; o++) {
        float acc = kFcB[o];
        for (int c = 0; c < kC4; c++) acc += pooled[c] * kFcW[o * kC4 + c];
        logit[o] = acc;
    }
    return {logit[0], logit[1]};
}

// Probability of "pothole" (softmax of the two logits).
inline float probability(const uint8_t* gray64) {
    const Logits l = run(gray64);
    return 1.0f / (1.0f + std::exp(l.no_pothole - l.pothole));
}

}  // namespace sensewalk::pothole
