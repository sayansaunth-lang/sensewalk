// SENSEWALK camera board: on-device "is a person in view?" detector (no laptop, no Pi).
//
// Runs Google's 96x96 Visual-Wake-Words person model (Apache-2.0, ~300 KB, from the
// TensorFlow Lite Micro examples) on the ESP32-S3 camera board with TensorFlow Lite Micro
// (Arduino library "Chirale_TensorFLowLite").
//
// What it can and cannot do (be honest about this in the demo):
//   * It answers ONE question per frame: person in view, yes/no. It does NOT say where the
//     person is or how far away, so it can only drive a soft warning, never the brake.
//   * Accuracy is limited by a 96x96 grayscale input. Test it on your own camera before trusting it.
//
// Serial (921600 baud) prints one line per frame:
//     t=12345ms infer=180ms person=87 notperson=-87 -> PERSON
// and understands two single-character commands:
//     'c' -> one JPEG photo (same format as SENSEWALK_cam_test, for test/cam_grab.py)
//     'g' -> the exact 96x96 grayscale image fed to the model, as <<GRAY 96x96>> + 9216 bytes
//            (to check the preprocessing: test/cam_gray.py saves it as a PNG)
//
// Camera pin map: ESP32-S3-EYE style, verified on the user's board (GC2145 sensor) with
// SENSEWALK_cam_test. Board settings: ESP32S3 Dev Module, PSRAM = OPI PSRAM.

#include <Arduino.h>
#include <Chirale_TensorFlowLite.h>

#include <esp_heap_caps.h>
#include <esp_timer.h>

#include "esp_camera.h"
#include "img_converters.h"
#include "person_detect_model_data.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

namespace {

constexpr int kModelCols = 96;
constexpr int kModelRows = 96;
constexpr int kPersonIndex = 1;
constexpr int kNotPersonIndex = 0;
// Decision rule: "person" when the person score beats the not-person score by this margin
// (int8 units, 0..255 apart). 0 = plain "which is larger". TODO(calibrate) on real footage.
constexpr int kPersonMargin = 0;
// Debounce, same idea as the Pi's RollingConfirm: warn only if 2 of the last 3 frames agree.
constexpr int kConfirmWindow = 3;
constexpr int kConfirmNeeded = 2;

constexpr int kTensorArenaSize = 130 * 1024;
uint8_t* tensorArena = nullptr;

const tflite::Model* model = nullptr;
tflite::MicroInterpreter* interpreter = nullptr;
TfLiteTensor* input = nullptr;

uint8_t gray96[kModelCols * kModelRows];
bool cameraUp = false;
bool modelUp = false;

bool history[kConfirmWindow] = {false, false, false};
int historyPos = 0;

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

// RGB565 (as delivered by esp32-camera: high byte first) -> 8-bit luma.
inline uint8_t lumaAt(const uint8_t* buf, int width, int x, int y) {
    const uint8_t* p = buf + 2 * (y * width + x);
    const uint16_t px = (static_cast<uint16_t>(p[0]) << 8) | p[1];
    const int r = ((px >> 11) & 0x1F) << 3;
    const int g = ((px >> 5) & 0x3F) << 2;
    const int b = (px & 0x1F) << 3;
    return static_cast<uint8_t>((77 * r + 150 * g + 29 * b) >> 8);
}

// Centre-crop the 320x240 frame to 240x240 and average it down to 96x96 grayscale.
void toGray96(const camera_fb_t* fb) {
    const int cropSize = fb->height;                 // 240
    const int x0 = (fb->width - cropSize) / 2;       // 40
    const float scale = static_cast<float>(cropSize) / kModelCols;  // 2.5
    for (int oy = 0; oy < kModelRows; oy++) {
        for (int ox = 0; ox < kModelCols; ox++) {
            const int sx = x0 + static_cast<int>(ox * scale);
            const int sy = static_cast<int>(oy * scale);
            // 2x2 average around the source point to soften aliasing
            const int sum = lumaAt(fb->buf, fb->width, sx, sy) + lumaAt(fb->buf, fb->width, sx + 1, sy) +
                            lumaAt(fb->buf, fb->width, sx, sy + 1) + lumaAt(fb->buf, fb->width, sx + 1, sy + 1);
            gray96[oy * kModelCols + ox] = static_cast<uint8_t>(sum >> 2);
        }
    }
}

bool initModel() {
    model = tflite::GetModel(g_person_detect_model_data);
    if (model->version() != TFLITE_SCHEMA_VERSION) {
        Serial.printf("model schema %d != supported %d\n", (int)model->version(), TFLITE_SCHEMA_VERSION);
        return false;
    }
    tensorArena = static_cast<uint8_t*>(heap_caps_malloc(kTensorArenaSize, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    if (tensorArena == nullptr) {
        Serial.println("could not allocate the tensor arena");
        return false;
    }
    static tflite::MicroMutableOpResolver<5> resolver;
    resolver.AddAveragePool2D();
    resolver.AddConv2D();
    resolver.AddDepthwiseConv2D();
    resolver.AddReshape();
    resolver.AddSoftmax();
    static tflite::MicroInterpreter staticInterpreter(model, resolver, tensorArena, kTensorArenaSize);
    interpreter = &staticInterpreter;
    if (interpreter->AllocateTensors() != kTfLiteOk) {
        Serial.println("AllocateTensors() failed (arena too small?)");
        return false;
    }
    input = interpreter->input(0);
    Serial.printf("model ok: input %dx%dx%d type=%d, arena used %u bytes\n", input->dims->data[1], input->dims->data[2],
                  input->dims->data[3], (int)input->type, (unsigned)interpreter->arena_used_bytes());
    return true;
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

}  // namespace

void setup() {
    Serial.begin(921600);
    delay(1500);
    Serial.println("\n[SENSEWALK cam person detector]");
    Serial.printf("PSRAM: %s\n", psramFound() ? "yes" : "NO (camera + model need it)");
    cameraUp = initCamera();
    if (cameraUp) {
        sensor_t* s = esp_camera_sensor_get();
        Serial.printf("camera ok (sensor PID 0x%02X)\n", s->id.PID);
        for (int i = 0; i < 5; i++) {
            camera_fb_t* fb = esp_camera_fb_get();
            if (fb) esp_camera_fb_return(fb);
        }
    }
    modelUp = initModel();
    if (cameraUp && modelUp) Serial.println("Ready.");
    else Serial.println("NOT READY: fix the line above.");
}

void loop() {
    if (!cameraUp || !modelUp) {
        delay(1000);
        return;
    }

    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("frame grab failed");
        return;
    }

    // Commands from the laptop (optional).
    char cmd = 0;
    if (Serial.available() > 0) cmd = Serial.read();
    if (cmd == 'c') {
        sendJpeg(fb);
    }

    toGray96(fb);
    esp_camera_fb_return(fb);

    if (cmd == 'g') {
        Serial.printf("\n<<GRAY %dx%d>>\n", kModelCols, kModelRows);
        Serial.write(gray96, sizeof(gray96));
        Serial.print("\n<<END>>\n");
    }

    // The model wants int8 input: pixel - 128.
    for (int i = 0; i < kModelCols * kModelRows; i++) {
        input->data.int8[i] = static_cast<int8_t>(static_cast<int>(gray96[i]) - 128);
    }
    const int64_t t0 = esp_timer_get_time();
    if (interpreter->Invoke() != kTfLiteOk) {
        Serial.println("Invoke() failed");
        return;
    }
    const int inferMs = static_cast<int>((esp_timer_get_time() - t0) / 1000);

    const TfLiteTensor* output = interpreter->output(0);
    const int personScore = output->data.int8[kPersonIndex];
    const int notPersonScore = output->data.int8[kNotPersonIndex];
    const bool personNow = (personScore - notPersonScore) > kPersonMargin;

    history[historyPos] = personNow;
    historyPos = (historyPos + 1) % kConfirmWindow;
    int votes = 0;
    for (bool h : history) votes += h ? 1 : 0;
    const bool confirmed = votes >= kConfirmNeeded;

    Serial.printf("t=%lums infer=%dms person=%d notperson=%d -> %s%s\n", (unsigned long)millis(), inferMs, personScore,
                  notPersonScore, personNow ? "PERSON" : "none", confirmed ? "  [CONFIRMED]" : "");
}
