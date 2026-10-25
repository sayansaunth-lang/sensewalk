// Host test: the C++ pothole classifier reproduces PyTorch's outputs on held-out test views.
//
//   g++ -O2 -std=c++17 -I firmware/esp32_arduino_ide/SENSEWALK_cam_main \
//       firmware/esp32_arduino_ide/tools/test_pothole_net.cpp -o /tmp/test_pothole_net && /tmp/test_pothole_net
//
// CI runs exactly this. The same check also runs on the camera board at boot (see the sketch).
#include <cmath>
#include <cstdio>

#include "pothole_golden.h"
#include "pothole_net.h"

int main() {
    using namespace sensewalk::pothole;
    float worst = 0.0f;
    for (int i = 0; i < kGoldenCount; i++) {
        const Logits l = run(kGoldenViews[i]);
        worst = std::fmax(worst, std::fabs(l.no_pothole - kGoldenLogits[2 * i]));
        worst = std::fmax(worst, std::fabs(l.pothole - kGoldenLogits[2 * i + 1]));
    }
    std::printf("pothole net: %d golden views, worst logit difference vs PyTorch = %.2e\n", kGoldenCount, worst);
    if (worst > 1e-3f) {
        std::printf("FAIL: C++ inference does not match PyTorch\n");
        return 1;
    }
    std::printf("PASS\n");
    return 0;
}
