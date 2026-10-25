// SENSEWALK ESP32-S3 camera board: on-board vision with no laptop and no Pi.
//
//   * PERSON in view  - Google's 96x96 person model (TensorFlow Lite Micro), ~0.37 s per frame.
//   * POTHOLE in view - our own tiny CNN (pothole_net.h, 60k parameters, trained on our dataset).
//   * Both are *warnings only*. They say something is in view, not where or how far, so they never
//     brake. Braking stays with the distance sensors on the safety ESP32.
//
// Outputs when something is confirmed (2 of the last 3 frames agree):
//   * a haptic command to the SAFETY ESP32 over a 3-wire UART (same protocol the Pi uses:
//     "haptic,<left>|<right>"), so the safety board vibrates the motors; it is re-sent 5x/second
//     and drops to 0|0 when the scene clears,
//   * a buzzer pattern on a piezo (2 short beeps = person, 3 long beeps = pothole),
//   * a status line on USB serial (921600 baud).
//
// Wiring to the safety ESP32 (3 wires, 3.3 V logic both sides):
//     camera board kLinkTxPin  ->  safety board GPIO16 (UART2 RX)
//     camera board kLinkRxPin  <-  safety board GPIO17 (UART2 TX)
//     GND to GND
//   Piezo buzzer: kBuzzerPin to the buzzer's + lead, buzzer - to GND (a passive piezo, or an active
//   buzzer through a 100 ohm resistor).
//   CONFIRM THESE PINS AGAINST YOUR BOARD'S SILKSCREEN: they must be free (not used by the camera,
//   flash/PSRAM or the USB serial chip). Change the three constants below if not.
//
// USB commands: 'c' -> one JPEG photo, 'g' -> the 96x96 grayscale person-model input,
//               'k' -> the 64x64 grayscale pothole-model input.
//
// Board settings: ESP32S3 Dev Module, PSRAM = "OPI PSRAM". Library: Chirale_TensorFLowLite.

#include <Arduino.h>
#include <Chirale_TensorFlowLite.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>

#include "esp_camera.h"
#include "img_converters.h"
#include "person_detect_model_data.h"
#define SENSEWALK_POTHOLE_PSRAM  // pothole workspace in PSRAM (see pothole_net.h)
#include "pothole_golden.h"
#include "pothole_net.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "uart_protocol.h"

namespace {

// ---- pins (see the header comment: confirm against your board) ----
constexpr int kLinkTxPin = 1;     // -> safety board GPIO16
constexpr int kLinkRxPin = 2;     // <- safety board GPIO17
constexpr int kBuzzerPin = 14;    // piezo buzzer
constexpr uint32_t kLinkBaud = 115200;

// ---- detection settings ----
constexpr int kPersonModelSize = 96;
constexpr int kPotholeModelSize = sensewalk::pothole::kInputSize;  // 64
constexpr int kPersonMargin = 0;  // person score must beat not-person by this (int8 units). TODO(calibrate)
constexpr int kConfirmWindow = 3;
constexpr int kConfirmNeeded = 2;
constexpr uint32_t kBeepCooldownMs = 4000;

// haptic strength (0-255) sent to the safety board
constexpr int kHapticPerson = 150;
constexpr int kHapticPothole = 255;

constexpr int kTensorArenaSize = 96 * 1024;  // the person model needs ~82 KB
uint8_t* tensorArena = nullptr;
const tflite::Model* personModel = nullptr;
tflite::MicroInterpreter* personInterpreter = nullptr;
TfLiteTensor* personInput = nullptr;

uint8_t gray96[kPersonModelSize * kPersonModelSize];
uint8_t gray64[kPotholeModelSize * kPotholeModelSize];
bool cameraUp = false;
bool personUp = false;

// Shared with the link/beeper tasks. 0 = clear, 1 = person, 2 = pothole.
volatile uint8_t gAlert = 0;
QueueHandle_t beepQueue = nullptr;

struct Confirm {
    bool h[kConfirmWindow] = {false, false, false};
    int pos = 0;
    bool observe(bool v) {
        h[pos] = v;
        pos = (pos + 1) % kConfirmWindow;
        int n = 0;
        for (bool x : h) n += x ? 1 : 0;
        return n >= kConfirmNeeded;
    }
};
Confirm personConfirm, potholeConfirm;

bool initCamera() {
    camera_config_t c = {};
    c.ledc_channel = LEDC_CHANNEL_0;
    c.ledc_timer = LEDC_TIMER_0;
    c.pin_d0 = 11;
    c.pin_d1 = 9;
    c.pin_d2 = 8;
    c.pin_d3 = 10;
    c.pin_d4 = 12;
    c.pin_d5 = 18;
    c.pin_d6 = 17;
    c.pin_d7 = 16;
    c.pin_xclk = 15;
    c.pin_pclk = 13;
    c.pin_vsync = 6;
    c.pin_href = 7;
    c.pin_sccb_sda = 4;
    c.pin_sccb_scl = 5;
    c.pin_pwdn = -1;
    c.pin_reset = -1;
    c.xclk_freq_hz = 20000000;
    c.pixel_format = PIXFORMAT_RGB565;  // the GC2145 has no JPEG engine
    c.frame_size = FRAMESIZE_QVGA;      // 320x240
    c.jpeg_quality = 12;
    c.fb_count = 2;
    c.fb_location = CAMERA_FB_IN_PSRAM;
    c.grab_mode = CAMERA_GRAB_LATEST;
    esp_err_t err = esp_camera_init(&c);
    if (err != ESP_OK) {
        Serial.printf("camera init failed 0x%x\n", err);
        return false;
    }
    return true;
}

inline uint8_t lumaAt(const uint8_t* buf, int width, int x, int y) {
    const uint8_t* p = buf + 2 * (y * width + x);  // RGB565, high byte first
    const uint16_t px = (static_cast<uint16_t>(p[0]) << 8) | p[1];
    const int r = ((px >> 11) & 0x1F) << 3;
    const int g = ((px >> 5) & 0x3F) << 2;
    const int b = (px & 0x1F) << 3;
    return static_cast<uint8_t>((77 * r + 150 * g + 29 * b) >> 8);
}

// Centre-crop the frame to a square and area-average it down to out x out grayscale.
void toGray(const camera_fb_t* fb, int outSize, uint8_t* out) {
    const int crop = fb->height;                  // 240
    const int x0 = (fb->width - crop) / 2;        // 40
    const float scale = static_cast<float>(crop) / outSize;
    const int block = static_cast<int>(scale);    // 2 for 96, 3 for 64
    for (int oy = 0; oy < outSize; oy++) {
        for (int ox = 0; ox < outSize; ox++) {
            const int sx = x0 + static_cast<int>(ox * scale);
            const int sy = static_cast<int>(oy * scale);
            int sum = 0;
            for (int dy = 0; dy < block; dy++)
                for (int dx = 0; dx < block; dx++) sum += lumaAt(fb->buf, fb->width, sx + dx, sy + dy);
            out[oy * outSize + ox] = static_cast<uint8_t>(sum / (block * block));
        }
    }
}

bool initPersonModel() {
    personModel = tflite::GetModel(g_person_detect_model_data);
    if (personModel->version() != TFLITE_SCHEMA_VERSION) {
        Serial.printf("person model schema %d != supported %d\n", (int)personModel->version(), TFLITE_SCHEMA_VERSION);
        return false;
    }
    tensorArena = static_cast<uint8_t*>(heap_caps_malloc(kTensorArenaSize, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    if (tensorArena == nullptr) {
        Serial.println("could not allocate the person model's tensor arena");
        return false;
    }
    static tflite::MicroMutableOpResolver<5> resolver;
    resolver.AddAveragePool2D();
    resolver.AddConv2D();
    resolver.AddDepthwiseConv2D();
    resolver.AddReshape();
    resolver.AddSoftmax();
    static tflite::MicroInterpreter interpreter(personModel, resolver, tensorArena, kTensorArenaSize);
    personInterpreter = &interpreter;
    if (personInterpreter->AllocateTensors() != kTfLiteOk) {
        Serial.println("person model AllocateTensors() failed");
        return false;
    }
    personInput = personInterpreter->input(0);
    return true;
}

// Prove the on-board pothole network matches PyTorch before trusting it.
bool potholeSelfTest() {
    using namespace sensewalk::pothole;
    float worst = 0.0f;
    for (int i = 0; i < kGoldenCount; i++) {
        const Logits l = run(kGoldenViews[i]);
        worst = fmaxf(worst, fabsf(l.no_pothole - kGoldenLogits[2 * i]));
        worst = fmaxf(worst, fabsf(l.pothole - kGoldenLogits[2 * i + 1]));
    }
    Serial.printf("pothole selftest: worst logit diff vs PyTorch %.2e -> %s\n", worst, worst < 1e-3f ? "OK" : "MISMATCH");
    return worst < 1e-3f;
}

void sendJpeg(camera_fb_t* fb) {
    uint8_t* converted = nullptr;
    size_t len = 0;
    if (!frame2jpg(fb, 80, &converted, &len)) {
        Serial.println("<<NOFRAME>>");
        return;
    }
    Serial.printf("\n<<JPEG %u>>\n", (unsigned)len);
    Serial.write(converted, len);
    Serial.print("\n<<END>>\n");
    free(converted);
}

void sendGray(const char* tag, const uint8_t* data, int size) {
    Serial.printf("\n<<%s %dx%d>>\n", tag, size, size);
    Serial.write(data, size * size);
    Serial.print("\n<<END>>\n");
}

// ---- tasks: haptic link to the safety board, and the buzzer ----
void linkTask(void*) {
    uint16_t seq = 0;
    uint32_t lastPrintMs = 0;
    int lastPrinted = -1;
    for (;;) {
        const uint8_t alert = gAlert;
        const int level = alert == 2 ? kHapticPothole : (alert == 1 ? kHapticPerson : 0);
        char value[16];
        snprintf(value, sizeof(value), "%d|%d", level, level);
        char line[sensewalk::comms::MAX_LINE_LEN];
        const size_t n = sensewalk::comms::encodeLine(line, sizeof(line), "haptic", value, seq++);
        if (n > 0) {
            Serial1.write(reinterpret_cast<const uint8_t*>(line), n);
            // Echo the exact frame to USB when it changes (and once a second) so a laptop can verify it.
            if (level != lastPrinted || millis() - lastPrintMs > 1000) {
                lastPrinted = level;
                lastPrintMs = millis();
                Serial.printf("[uart] %s", line);
            }
        }
        vTaskDelay(pdMS_TO_TICKS(200));
    }
}

void beep(int freqHz, int onMs, int offMs, int count) {
    for (int i = 0; i < count; i++) {
        tone(kBuzzerPin, freqHz);
        vTaskDelay(pdMS_TO_TICKS(onMs));
        noTone(kBuzzerPin);
        vTaskDelay(pdMS_TO_TICKS(offMs));
    }
}

void beepTask(void*) {
    uint8_t kind;
    for (;;) {
        if (xQueueReceive(beepQueue, &kind, portMAX_DELAY) == pdTRUE) {
            if (kind == 2) beep(1000, 300, 150, 3);   // pothole: 3 long beeps
            else if (kind == 1) beep(2200, 120, 100, 2);  // person: 2 short beeps
        }
    }
}

}  // namespace

void setup() {
    Serial.begin(921600);
    delay(1500);
    Serial.println("\n[SENSEWALK cam main: person + pothole]");
    Serial.printf("PSRAM: %s\n", psramFound() ? "yes" : "NO (camera + model need it)");

    Serial1.begin(kLinkBaud, SERIAL_8N1, kLinkRxPin, kLinkTxPin);
    pinMode(kBuzzerPin, OUTPUT);
    beepQueue = xQueueCreate(4, sizeof(uint8_t));

    cameraUp = initCamera();
    if (cameraUp) {
        sensor_t* s = esp_camera_sensor_get();
        Serial.printf("camera ok (sensor PID 0x%02X)\n", s->id.PID);
        for (int i = 0; i < 5; i++) {
            camera_fb_t* fb = esp_camera_fb_get();
            if (fb) esp_camera_fb_return(fb);
        }
    }
    personUp = initPersonModel();
    if (personUp) {
        Serial.printf("person model ok: arena used %u bytes\n", (unsigned)personInterpreter->arena_used_bytes());
    }
    const bool potholeOk = potholeSelfTest();

    xTaskCreate(linkTask, "link", 4096, nullptr, 2, nullptr);
    xTaskCreate(beepTask, "beep", 3072, nullptr, 2, nullptr);

    if (cameraUp && personUp && potholeOk) Serial.println("Ready.");
    else Serial.println("NOT READY: fix the line above.");
}

void loop() {
    if (!cameraUp || !personUp) {
        delay(1000);
        return;
    }

    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("frame grab failed");
        return;
    }
    char cmd = 0;
    if (Serial.available() > 0) cmd = Serial.read();
    if (cmd == 'c') sendJpeg(fb);

    toGray(fb, kPersonModelSize, gray96);
    toGray(fb, kPotholeModelSize, gray64);
    esp_camera_fb_return(fb);
    if (cmd == 'g') sendGray("GRAY", gray96, kPersonModelSize);
    if (cmd == 'k') sendGray("POTH", gray64, kPotholeModelSize);

    // --- person ---
    for (int i = 0; i < kPersonModelSize * kPersonModelSize; i++) {
        personInput->data.int8[i] = static_cast<int8_t>(static_cast<int>(gray96[i]) - 128);
    }
    const int64_t t0 = esp_timer_get_time();
    if (personInterpreter->Invoke() != kTfLiteOk) {
        Serial.println("person Invoke() failed");
        return;
    }
    const int personMs = static_cast<int>((esp_timer_get_time() - t0) / 1000);
    const TfLiteTensor* out = personInterpreter->output(0);
    const int personScore = out->data.int8[1];
    const int notPersonScore = out->data.int8[0];
    const bool personNow = (personScore - notPersonScore) > kPersonMargin;
    const bool personConfirmed = personConfirm.observe(personNow);

    // --- pothole ---
    const int64_t t1 = esp_timer_get_time();
    const float pProb = sensewalk::pothole::probability(gray64);
    const int potholeMs = static_cast<int>((esp_timer_get_time() - t1) / 1000);
    const bool potholeNow = pProb >= sensewalk::pothole::kThreshold;
    const bool potholeConfirmed = potholeConfirm.observe(potholeNow);

    // --- alert (pothole outranks person) ---
    const uint8_t alert = potholeConfirmed ? 2 : (personConfirmed ? 1 : 0);
    static uint8_t lastAlert = 0;
    static uint32_t lastBeepMs = 0;
    if (alert != 0 && (alert > lastAlert || millis() - lastBeepMs > kBeepCooldownMs)) {
        lastBeepMs = millis();
        xQueueSend(beepQueue, &alert, 0);
    }
    lastAlert = alert;
    gAlert = alert;

    // Keep the "-> PERSON [CONFIRMED]" shape: test/cam_person_check.py and cam_view.py parse it.
    Serial.printf("t=%lums infer=%dms person=%d notperson=%d -> %s%s | pothole p=%.2f (%dms) -> %s%s\n",
                  (unsigned long)millis(), personMs, personScore, notPersonScore, personNow ? "PERSON" : "none",
                  personConfirmed ? "  [CONFIRMED]" : "", pProb, potholeMs, potholeNow ? "POTHOLE" : "clear",
                  potholeConfirmed ? " [CONFIRMED]" : "");
}
