// ESP32-S3 camera board bring-up test (no Wi-Fi needed).
//
// Different S3 camera boards wire the camera to different pins, and some cheap sensors have no
// JPEG engine, so this tries the common pin layouts and both picture formats until one works,
// and reports which. When the camera is up it waits for the character 'c' on the serial port
// and answers with one JPEG photo (compressed on the chip if the sensor can't do it):
//
//     <<JPEG 12345>>\n  <12345 raw JPEG bytes>  \n<<END>>\n
//
// Use test/cam_grab.py on the laptop to request photos and save them as files.
// Serial speed is 921600 baud (works through the CH343/CH340-style USB-serial chips).
//
// Board settings: ESP32S3 Dev Module, PSRAM = "OPI PSRAM" for N16R8 boards (try "QSPI PSRAM"
// if the board resets with a PSRAM error), Flash size 16MB.

#include <Arduino.h>

#include "esp_camera.h"
#include "img_converters.h"

struct PinMap {
    const char* name;
    int xclk, siod, sioc;
    int y9, y8, y7, y6, y5, y4, y3, y2;
    int vsync, href, pclk;
};

static const PinMap MAPS[] = {
    {"ESP32-S3-EYE / Freenove-style", 15, 4, 5, 16, 17, 18, 12, 10, 8, 9, 11, 6, 7, 13},
    {"ESP32-S3 CAM LCD-style", 40, 17, 18, 39, 41, 42, 12, 3, 14, 47, 13, 21, 38, 11},
    {"XIAO ESP32S3 Sense", 10, 40, 39, 48, 11, 12, 14, 16, 18, 17, 15, 38, 47, 13},
};

static const char* sensorNameFor(int pid) {
    switch (pid) {
        case 0x26: return "OV2640";
        case 0x36: return "OV3660";
        case 0x56: return "OV5640";
        case 0x76: return "OV7670";
        case 0x77: return "OV7725";
        case 0x9B: return "GC0308";
        default: return "unknown";
    }
}

static bool tryMap(const PinMap& m, pixformat_t format) {
    camera_config_t c = {};
    c.ledc_channel = LEDC_CHANNEL_0;
    c.ledc_timer = LEDC_TIMER_0;
    c.pin_d0 = m.y2;
    c.pin_d1 = m.y3;
    c.pin_d2 = m.y4;
    c.pin_d3 = m.y5;
    c.pin_d4 = m.y6;
    c.pin_d5 = m.y7;
    c.pin_d6 = m.y8;
    c.pin_d7 = m.y9;
    c.pin_xclk = m.xclk;
    c.pin_pclk = m.pclk;
    c.pin_vsync = m.vsync;
    c.pin_href = m.href;
    c.pin_sccb_sda = m.siod;
    c.pin_sccb_scl = m.sioc;
    c.pin_pwdn = -1;
    c.pin_reset = -1;
    c.xclk_freq_hz = 20000000;
    c.pixel_format = format;       // JPEG if the sensor has a JPEG engine, else raw RGB565
    c.frame_size = FRAMESIZE_QVGA;  // 320x240: small, fast, and what the vision code resizes to anyway
    c.jpeg_quality = 12;
    c.fb_count = 2;
    c.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
    c.grab_mode = CAMERA_GRAB_LATEST;
    if (!psramFound()) c.fb_count = 1;
    esp_err_t err = esp_camera_init(&c);
    if (err != ESP_OK) {
        Serial.printf("  init failed with 0x%x\n", err);
        esp_camera_deinit();
        return false;
    }
    return true;
}

static bool cameraUp = false;

void setup() {
    Serial.begin(921600);
    delay(1500);
    Serial.println("\n[SENSEWALK cam test]");
    Serial.printf("PSRAM found: %s (%u bytes)\n", psramFound() ? "yes" : "NO", (unsigned)ESP.getPsramSize());
    const pixformat_t formats[] = {PIXFORMAT_JPEG, PIXFORMAT_RGB565};
    for (const PinMap& m : MAPS) {
        for (pixformat_t fmt : formats) {
            Serial.printf("trying pin map: %s, %s\n", m.name, fmt == PIXFORMAT_JPEG ? "JPEG" : "RGB565");
            if (tryMap(m, fmt)) {
                sensor_t* s = esp_camera_sensor_get();
                Serial.printf("CAMERA OK  map=\"%s\"  format=%s  sensor=%s (PID 0x%02X)\n", m.name,
                              fmt == PIXFORMAT_JPEG ? "JPEG" : "RGB565", sensorNameFor(s->id.PID), s->id.PID);
                cameraUp = true;
                for (int i = 0; i < 5; i++) {  // let auto-exposure settle
                    camera_fb_t* fb = esp_camera_fb_get();
                    if (fb) esp_camera_fb_return(fb);
                }
                break;
            }
        }
        if (cameraUp) break;
    }
    if (!cameraUp) Serial.println("CAMERA FAILED on every known pin map: send me the board's listing / pinout.");
    else Serial.println("Ready. Send 'c' to get one JPEG photo.");
}

void loop() {
    if (Serial.available() > 0) {
        char ch = Serial.read();
        if (ch == 'c' && cameraUp) {
            for (int i = 0; i < 2; i++) {  // drop stale buffered frames
                camera_fb_t* old = esp_camera_fb_get();
                if (old) esp_camera_fb_return(old);
            }
            camera_fb_t* fb = esp_camera_fb_get();
            if (!fb) {
                Serial.println("<<NOFRAME>>");
                return;
            }
            uint8_t* jpg = fb->buf;
            size_t jpgLen = fb->len;
            uint8_t* converted = nullptr;
            if (fb->format != PIXFORMAT_JPEG) {  // sensor has no JPEG engine: compress on the chip
                if (!frame2jpg(fb, 80, &converted, &jpgLen)) {
                    esp_camera_fb_return(fb);
                    Serial.println("<<NOFRAME>>");
                    return;
                }
                jpg = converted;
            }
            Serial.printf("\n<<JPEG %u>>\n", (unsigned)jpgLen);
            Serial.write(jpg, jpgLen);
            Serial.print("\n<<END>>\n");
            if (converted) free(converted);
            esp_camera_fb_return(fb);
        } else if (ch == 'c') {
            Serial.println("<<NOCAMERA>>");
        }
    }
    delay(5);
}
