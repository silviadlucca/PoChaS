#include <Arduino.h>
#include <SPI.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include "DW3000.h"

#ifndef BEACON_UWB_ID
#define BEACON_UWB_ID 250
#endif

#ifndef ORIGIN_ANCHOR_ID
#define ORIGIN_ANCHOR_ID 0
#endif

static const char *AP_SSID = "Beacon-Calibrador";
static const char *AP_PASSWORD = "anclas1234";

static const unsigned long SERIAL_BAUD_RATE = 921600;
static const uint8_t MAX_ANCHORS = 10;
static const uint8_t MAX_SAMPLES = 15;
static const uint8_t DEFAULT_SAMPLES = 7;
static const uint8_t MAX_ATTEMPTS_PER_SAMPLE = 3;
static const unsigned long RESPONSE_TIMEOUT_MS = 14;
static const unsigned long TRANSACTION_TIMEOUT_MS = 55;
static const float MAX_REASONABLE_RANGE_M = 80.0f;

WebServer server(80);
Preferences prefs;

struct AnchorPoint {
  uint8_t id = 0;
  float x = 0.0f;
  float y = 0.0f;
  bool valid = false;
};

struct DistanceReading {
  uint8_t id = 0;
  float distance = 0.0f;
  float rssi = -120.0f;
  float powerDiff = 0.0f;
  bool ok = false;
};

struct LastResult {
  bool hasResult = false;
  bool ok = false;
  uint8_t targetId = 0;
  float x = 0.0f;
  float y = 0.0f;
  float rms = 0.0f;
  uint8_t usedAnchors = 0;
  String message;
  DistanceReading readings[MAX_ANCHORS];
  uint8_t readingCount = 0;
};

AnchorPoint anchors[MAX_ANCHORS];
uint8_t anchorCount = 0;
LastResult lastResult;

void initializeDW3000();
void loadAnchors();
void saveAnchors();
void resetCalibration();
int findAnchorIndex(uint8_t id);
bool addOrUpdateAnchor(uint8_t id, float x, float y);
bool performRanging(uint8_t anchorId, DistanceReading &reading);
bool measureAnchorMedian(uint8_t anchorId, uint8_t samples, DistanceReading &reading);
bool registerAnchorAtBeaconPosition(uint8_t targetId, uint8_t samples, int sideSign);
bool solvePosition(const DistanceReading *readings, uint8_t readingCount, int sideSign, float &x, float &y, float &rms, String &message);
String stateJson();
String htmlPage();
void handleRoot();
void handleState();
void handleRegister();
void handleReset();
void sendJson(int code, const String &json);
String jsonEscape(const String &text);

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  delay(300);

  loadAnchors();
  if (findAnchorIndex(ORIGIN_ANCHOR_ID) < 0) {
    resetCalibration();
  }

  initializeDW3000();

  WiFi.mode(WIFI_AP);
  WiFi.setSleep(false);
  WiFi.softAP(AP_SSID, AP_PASSWORD);

  server.on("/", HTTP_GET, handleRoot);
  server.on("/api/state", HTTP_GET, handleState);
  server.on("/api/register", HTTP_POST, handleRegister);
  server.on("/api/reset", HTTP_POST, handleReset);
  server.begin();

  Serial.println();
  Serial.println("=== BEACON CALIBRATOR READY ===");
  Serial.printf("WiFi SSID: %s\n", AP_SSID);
  Serial.printf("WiFi password: %s\n", AP_PASSWORD);
  Serial.printf("Open: http://%s/\n", WiFi.softAPIP().toString().c_str());
  Serial.printf("Beacon UWB ID: %d\n", BEACON_UWB_ID);
  Serial.printf("Origin anchor ID: %d\n", ORIGIN_ANCHOR_ID);
}

void loop() {
  server.handleClient();
}

void initializeDW3000() {
  SPI.begin();
  DW3000.begin();
  SPI.setFrequency(8000000);

  DW3000.hardReset();
  delay(200);
  DW3000.softReset();
  delay(200);

  int retries = 0;
  while (!DW3000.checkForIDLE() && retries < 5) {
    Serial.printf("[UWB] Waiting for IDLE, retry %d/5\n", retries + 1);
    delay(50);
    retries++;
  }

  if (retries >= 5) {
    Serial.println("[UWB] DW3000 did not reach IDLE. Restarting.");
    delay(100);
    ESP.restart();
  }

  DW3000.setChannel(CHANNEL_5);
  DW3000.setPreambleCode(9);
  DW3000.setSenderID(BEACON_UWB_ID);
  DW3000.init();
  SPI.setFrequency(20000000);
  DW3000.setupGPIO();
  DW3000.configureAsTX();
  DW3000.clearSystemStatus();

  Serial.println("[UWB] DW3000 initialized on channel 5, preamble code 9.");
}

void loadAnchors() {
  prefs.begin("uwbcal", true);
  anchorCount = prefs.getUChar("count", 0);
  if (anchorCount > MAX_ANCHORS) {
    anchorCount = 0;
  }

  for (uint8_t i = 0; i < MAX_ANCHORS; i++) {
    char key[8];
    snprintf(key, sizeof(key), "id%u", i);
    anchors[i].id = prefs.getUChar(key, 0);
    snprintf(key, sizeof(key), "x%u", i);
    anchors[i].x = prefs.getFloat(key, 0.0f);
    snprintf(key, sizeof(key), "y%u", i);
    anchors[i].y = prefs.getFloat(key, 0.0f);
    anchors[i].valid = i < anchorCount;
  }
  prefs.end();
}

void saveAnchors() {
  prefs.begin("uwbcal", false);
  prefs.clear();
  prefs.putUChar("count", anchorCount);

  for (uint8_t i = 0; i < anchorCount; i++) {
    char key[8];
    snprintf(key, sizeof(key), "id%u", i);
    prefs.putUChar(key, anchors[i].id);
    snprintf(key, sizeof(key), "x%u", i);
    prefs.putFloat(key, anchors[i].x);
    snprintf(key, sizeof(key), "y%u", i);
    prefs.putFloat(key, anchors[i].y);
  }
  prefs.end();
}

void resetCalibration() {
  anchorCount = 1;
  for (uint8_t i = 0; i < MAX_ANCHORS; i++) {
    anchors[i] = AnchorPoint();
  }
  anchors[0].id = ORIGIN_ANCHOR_ID;
  anchors[0].x = 0.0f;
  anchors[0].y = 0.0f;
  anchors[0].valid = true;
  saveAnchors();

  lastResult = LastResult();
  lastResult.hasResult = true;
  lastResult.ok = true;
  lastResult.targetId = ORIGIN_ANCHOR_ID;
  lastResult.message = "Calibracion reiniciada. A0 queda fijada en (0,0).";
}

int findAnchorIndex(uint8_t id) {
  for (uint8_t i = 0; i < anchorCount; i++) {
    if (anchors[i].valid && anchors[i].id == id) {
      return i;
    }
  }
  return -1;
}

bool addOrUpdateAnchor(uint8_t id, float x, float y) {
  int existing = findAnchorIndex(id);
  if (existing >= 0) {
    anchors[existing].x = x;
    anchors[existing].y = y;
    anchors[existing].valid = true;
    saveAnchors();
    return true;
  }

  if (anchorCount >= MAX_ANCHORS) {
    return false;
  }

  anchors[anchorCount].id = id;
  anchors[anchorCount].x = x;
  anchors[anchorCount].y = y;
  anchors[anchorCount].valid = true;
  anchorCount++;
  saveAnchors();
  return true;
}

bool performRanging(uint8_t anchorId, DistanceReading &reading) {
  reading = DistanceReading();
  reading.id = anchorId;

  int currStage = 0;
  int tRoundA = 0;
  int tReplyA = 0;
  long long rx = 0;
  long long tx = 0;
  int clockOffset = 0;
  unsigned long startedAt = millis();
  unsigned long timeoutStart = millis();
  bool waitingForResponse = false;

  DW3000.clearSystemStatus();
  DW3000.configureAsTX();
  DW3000.setSenderID(BEACON_UWB_ID);
  DW3000.setDestinationID(anchorId);

  while (millis() - startedAt < TRANSACTION_TIMEOUT_MS) {
    if (waitingForResponse && millis() - timeoutStart >= RESPONSE_TIMEOUT_MS) {
      DW3000.clearSystemStatus();
      DW3000.configureAsTX();
      return false;
    }

    switch (currStage) {
      case 0:
        DW3000.setDestinationID(anchorId);
        DW3000.ds_sendFrame(1);
        tx = DW3000.readTXTimestamp();
        currStage = 1;
        timeoutStart = millis();
        waitingForResponse = true;
        break;

      case 1: {
        int rxStatus = DW3000.receivedFrameSucc();
        if (rxStatus == 0) {
          delay(1);
          break;
        }

        DW3000.clearSystemStatus();
        if (rxStatus == 1 && !DW3000.ds_isErrorFrame() && DW3000.ds_getStage() == 2 && DW3000.getDestinationID() == anchorId) {
          rx = DW3000.readRXTimestamp();
          currStage = 2;
          waitingForResponse = false;
        } else {
          DW3000.configureAsTX();
          return false;
        }
        break;
      }

      case 2:
        DW3000.setDestinationID(anchorId);
        DW3000.ds_sendFrame(3);
        tRoundA = rx - tx;
        tx = DW3000.readTXTimestamp();
        tReplyA = tx - rx;
        currStage = 3;
        timeoutStart = millis();
        waitingForResponse = true;
        break;

      case 3: {
        int rxStatus = DW3000.receivedFrameSucc();
        if (rxStatus == 0) {
          delay(1);
          break;
        }

        DW3000.clearSystemStatus();
        if (rxStatus == 1 && !DW3000.ds_isErrorFrame() && DW3000.ds_getStage() == 4) {
          clockOffset = DW3000.getRawClockOffset();
          int tRoundB = DW3000.read(0x12, 0x04);
          int tReplyB = DW3000.read(0x12, 0x08);
          int rangingTime = DW3000.ds_processRTInfo(tRoundA, tReplyA, tRoundB, tReplyB, clockOffset);
          float distance = DW3000.convertToCM(rangingTime) / 100.0f;
          float rssi = DW3000.getSignalStrength();
          float powerDiff = DW3000.getPowerDifference();

          DW3000.configureAsTX();
          if (!isfinite(distance) || distance <= 0.0f || distance > MAX_REASONABLE_RANGE_M) {
            return false;
          }

          reading.distance = distance;
          reading.rssi = rssi;
          reading.powerDiff = powerDiff;
          reading.ok = true;
          return true;
        }

        DW3000.configureAsTX();
        return false;
      }
    }
  }

  DW3000.clearSystemStatus();
  DW3000.configureAsTX();
  return false;
}

bool measureAnchorMedian(uint8_t anchorId, uint8_t samples, DistanceReading &reading) {
  samples = constrain(samples, (uint8_t)3, MAX_SAMPLES);
  float distances[MAX_SAMPLES];
  float rssiSum = 0.0f;
  float pdSum = 0.0f;
  uint8_t okCount = 0;

  for (uint8_t sample = 0; sample < samples; sample++) {
    DistanceReading attemptReading;
    bool ok = false;

    for (uint8_t attempt = 0; attempt < MAX_ATTEMPTS_PER_SAMPLE && !ok; attempt++) {
      ok = performRanging(anchorId, attemptReading);
      if (!ok) {
        delay(20);
      }
    }

    if (ok) {
      distances[okCount] = attemptReading.distance;
      rssiSum += attemptReading.rssi;
      pdSum += attemptReading.powerDiff;
      okCount++;
    }

    delay(35);
  }

  if (okCount == 0) {
    reading = DistanceReading();
    reading.id = anchorId;
    return false;
  }

  for (uint8_t i = 0; i + 1 < okCount; i++) {
    for (uint8_t j = 0; j + 1 < okCount - i; j++) {
      if (distances[j] > distances[j + 1]) {
        float tmp = distances[j];
        distances[j] = distances[j + 1];
        distances[j + 1] = tmp;
      }
    }
  }

  reading.id = anchorId;
  reading.distance = distances[okCount / 2];
  reading.rssi = rssiSum / okCount;
  reading.powerDiff = pdSum / okCount;
  reading.ok = true;
  return true;
}

bool registerAnchorAtBeaconPosition(uint8_t targetId, uint8_t samples, int sideSign) {
  lastResult = LastResult();
  lastResult.hasResult = true;
  lastResult.targetId = targetId;

  if (targetId == ORIGIN_ANCHOR_ID) {
    lastResult.ok = false;
    lastResult.message = "El ID de origen ya esta reservado para A0.";
    return false;
  }

  DistanceReading readings[MAX_ANCHORS];
  uint8_t readingCount = 0;

  Serial.printf("[CAL] Registering anchor %u with %u samples per known anchor\n", targetId, samples);

  for (uint8_t i = 0; i < anchorCount; i++) {
    if (!anchors[i].valid || anchors[i].id == targetId) {
      continue;
    }

    DistanceReading reading;
    Serial.printf("[CAL] Measuring distance to anchor %u...\n", anchors[i].id);
    if (measureAnchorMedian(anchors[i].id, samples, reading)) {
      readings[readingCount++] = reading;
      Serial.printf("[CAL] Anchor %u: %.3f m, RSSI %.1f dBm\n", reading.id, reading.distance, reading.rssi);
    } else {
      Serial.printf("[CAL] Anchor %u did not respond.\n", anchors[i].id);
    }
  }

  for (uint8_t i = 0; i < readingCount; i++) {
    lastResult.readings[i] = readings[i];
  }
  lastResult.readingCount = readingCount;
  lastResult.usedAnchors = readingCount;

  float x = 0.0f;
  float y = 0.0f;
  float rms = 0.0f;
  String message;

  if (!solvePosition(readings, readingCount, sideSign, x, y, rms, message)) {
    lastResult.ok = false;
    lastResult.message = message;
    return false;
  }

  if (!addOrUpdateAnchor(targetId, x, y)) {
    lastResult.ok = false;
    lastResult.message = "No queda espacio para guardar mas anclas.";
    return false;
  }

  lastResult.ok = true;
  lastResult.x = x;
  lastResult.y = y;
  lastResult.rms = rms;
  lastResult.message = message;

  Serial.printf("[CAL] Anchor %u stored at (%.3f, %.3f), RMS %.3f m\n", targetId, x, y, rms);
  return true;
}

bool solvePosition(const DistanceReading *readings, uint8_t readingCount, int sideSign, float &x, float &y, float &rms, String &message) {
  if (readingCount == 0) {
    message = "No se recibio ninguna distancia valida. Comprueba que las anclas previas estan encendidas.";
    return false;
  }

  if (readingCount == 1) {
    int idx = findAnchorIndex(readings[0].id);
    if (idx < 0) {
      message = "La distancia recibida no corresponde a un ancla registrada.";
      return false;
    }

    x = anchors[idx].x + readings[0].distance;
    y = anchors[idx].y;
    rms = 0.0f;
    message = "Solo habia una ancla conocida: se coloca la nueva ancla sobre el eje X positivo.";
    return true;
  }

  if (readingCount == 2) {
    int idx0 = findAnchorIndex(readings[0].id);
    int idx1 = findAnchorIndex(readings[1].id);
    if (idx0 < 0 || idx1 < 0) {
      message = "Alguna distancia no corresponde a un ancla registrada.";
      return false;
    }

    const AnchorPoint &a0 = anchors[idx0];
    const AnchorPoint &a1 = anchors[idx1];
    float dx = a1.x - a0.x;
    float dy = a1.y - a0.y;
    float baseline = sqrtf(dx * dx + dy * dy);
    if (baseline < 0.05f) {
      message = "Las dos anclas conocidas estan demasiado juntas para resolver la posicion.";
      return false;
    }

    float r0 = readings[0].distance;
    float r1 = readings[1].distance;
    float along = (r0 * r0 - r1 * r1 + baseline * baseline) / (2.0f * baseline);
    float heightSq = r0 * r0 - along * along;
    if (heightSq < -0.35f) {
      message = "Las dos circunferencias no se cruzan. Repite la medicion o separa mejor las anclas.";
      return false;
    }
    if (heightSq < 0.0f) {
      heightSq = 0.0f;
    }

    float ex = dx / baseline;
    float ey = dy / baseline;
    float px = a0.x + along * ex;
    float py = a0.y + along * ey;
    float height = sqrtf(heightSq);
    int sign = sideSign >= 0 ? 1 : -1;

    x = px + sign * height * (-ey);
    y = py + sign * height * ex;

    float e0 = hypotf(x - a0.x, y - a0.y) - r0;
    float e1 = hypotf(x - a1.x, y - a1.y) - r1;
    rms = sqrtf((e0 * e0 + e1 * e1) / 2.0f);
    message = "Posicion calculada con interseccion de dos distancias. Si sale reflejada, repite con el lado Y contrario.";
    return true;
  }

  int refIdx = findAnchorIndex(readings[0].id);
  if (refIdx < 0) {
    message = "La ancla de referencia no esta registrada.";
    return false;
  }

  const AnchorPoint &ref = anchors[refIdx];
  float r0 = readings[0].distance;
  float saa = 0.0f;
  float sab = 0.0f;
  float sbb = 0.0f;
  float sac = 0.0f;
  float sbc = 0.0f;

  for (uint8_t i = 1; i < readingCount; i++) {
    int idx = findAnchorIndex(readings[i].id);
    if (idx < 0) {
      continue;
    }

    const AnchorPoint &a = anchors[idx];
    float ai = 2.0f * (a.x - ref.x);
    float bi = 2.0f * (a.y - ref.y);
    float ci = r0 * r0 - readings[i].distance * readings[i].distance
             + a.x * a.x - ref.x * ref.x
             + a.y * a.y - ref.y * ref.y;

    saa += ai * ai;
    sab += ai * bi;
    sbb += bi * bi;
    sac += ai * ci;
    sbc += bi * ci;
  }

  float det = saa * sbb - sab * sab;
  if (fabsf(det) < 0.0001f) {
    message = "La geometria de las anclas es casi colineal; no se puede triangular bien.";
    return false;
  }

  x = (sac * sbb - sab * sbc) / det;
  y = (saa * sbc - sab * sac) / det;

  float errSq = 0.0f;
  uint8_t used = 0;
  for (uint8_t i = 0; i < readingCount; i++) {
    int idx = findAnchorIndex(readings[i].id);
    if (idx < 0) {
      continue;
    }
    float predicted = hypotf(x - anchors[idx].x, y - anchors[idx].y);
    float error = predicted - readings[i].distance;
    errSq += error * error;
    used++;
  }

  rms = used > 0 ? sqrtf(errSq / used) : 0.0f;
  message = "Posicion calculada por trilateracion 2D con minimos cuadrados.";
  return true;
}

String jsonEscape(const String &text) {
  String escaped;
  escaped.reserve(text.length() + 8);
  for (size_t i = 0; i < text.length(); i++) {
    char c = text[i];
    if (c == '"' || c == '\\') {
      escaped += '\\';
      escaped += c;
    } else if (c == '\n') {
      escaped += "\\n";
    } else if (c == '\r') {
      escaped += "\\r";
    } else {
      escaped += c;
    }
  }
  return escaped;
}

String stateJson() {
  String json;
  json.reserve(4096);
  json += "{";
  json += "\"ap_ssid\":\"";
  json += AP_SSID;
  json += "\",\"ap_ip\":\"";
  json += WiFi.softAPIP().toString();
  json += "\",\"origin_anchor_id\":";
  json += (int)ORIGIN_ANCHOR_ID;
  json += ",\"beacon_uwb_id\":";
  json += (int)BEACON_UWB_ID;
  json += ",\"anchor_count\":";
  json += (int)anchorCount;
  json += ",\"anchors\":[";

  for (uint8_t i = 0; i < anchorCount; i++) {
    if (i > 0) {
      json += ",";
    }
    json += "{\"id\":";
    json += (int)anchors[i].id;
    json += ",\"x\":";
    json += String(anchors[i].x, 3);
    json += ",\"y\":";
    json += String(anchors[i].y, 3);
    json += "}";
  }
  json += "]";

  json += ",\"last_result\":";
  if (!lastResult.hasResult) {
    json += "null";
  } else {
    json += "{\"ok\":";
    json += lastResult.ok ? "true" : "false";
    json += ",\"target_id\":";
    json += (int)lastResult.targetId;
    json += ",\"x\":";
    json += String(lastResult.x, 3);
    json += ",\"y\":";
    json += String(lastResult.y, 3);
    json += ",\"rms\":";
    json += String(lastResult.rms, 3);
    json += ",\"used_anchors\":";
    json += (int)lastResult.usedAnchors;
    json += ",\"message\":\"";
    json += jsonEscape(lastResult.message);
    json += "\",\"readings\":[";
    for (uint8_t i = 0; i < lastResult.readingCount; i++) {
      if (i > 0) {
        json += ",";
      }
      json += "{\"id\":";
      json += (int)lastResult.readings[i].id;
      json += ",\"distance\":";
      json += String(lastResult.readings[i].distance, 3);
      json += ",\"rssi\":";
      json += String(lastResult.readings[i].rssi, 1);
      json += ",\"power_diff\":";
      json += String(lastResult.readings[i].powerDiff, 2);
      json += "}";
    }
    json += "]}";
  }

  json += "}";
  return json;
}

String htmlPage() {
  return R"rawliteral(
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Beacon Calibrador UWB</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f5f7fb; color: #172033; }
    main { max-width: 860px; margin: 0 auto; padding: 22px; }
    header { margin-bottom: 22px; }
    h1 { font-size: 1.55rem; margin: 0 0 6px; }
    h2 { font-size: 1.05rem; margin: 0 0 12px; }
    p { margin: 0; color: #566176; line-height: 1.45; }
    section { background: #fff; border: 1px solid #dde4ef; border-radius: 8px; padding: 16px; margin-bottom: 14px; box-shadow: 0 1px 2px rgba(20, 30, 50, .04); }
    label { display: block; font-size: .82rem; font-weight: 700; margin-bottom: 6px; color: #33415f; }
    input, select, button { font: inherit; }
    input, select { width: 100%; box-sizing: border-box; border: 1px solid #c8d1e1; border-radius: 7px; padding: 10px; background: #fff; color: #172033; }
    button { border: 0; border-radius: 7px; padding: 11px 14px; background: #1769e0; color: white; font-weight: 700; cursor: pointer; }
    button.secondary { background: #e7ecf5; color: #26344d; }
    button.danger { background: #b42318; }
    button:disabled { opacity: .55; cursor: wait; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; }
    .status { padding: 12px; border-radius: 7px; background: #eef5ff; color: #183b67; }
    .status.error { background: #fff0ed; color: #8c1d18; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; border-bottom: 1px solid #edf1f7; padding: 9px 6px; font-size: .92rem; }
    th { color: #5a6578; font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }
    .muted { color: #6a7487; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    @media (max-width: 680px) {
      main { padding: 16px; }
      .grid { grid-template-columns: 1fr; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
<main>
  <header>
    <h1>Beacon Calibrador UWB</h1>
    <p>Conecta el movil a esta red WiFi, coloca el beacon delante del tripode de la nueva ancla y registra su posicion.</p>
  </header>

  <section>
    <h2>Nueva ancla</h2>
    <div class="grid">
      <div>
        <label for="target">ID de la nueva ancla</label>
        <input id="target" type="number" min="1" max="255" value="1">
      </div>
      <div>
        <label for="side">Lado para 2 anclas conocidas</label>
        <select id="side">
          <option value="1">Y positivo</option>
          <option value="-1">Y negativo</option>
        </select>
      </div>
      <div>
        <label for="samples">Muestras por ancla</label>
        <input id="samples" type="number" min="3" max="15" value="7">
      </div>
    </div>
    <div class="actions">
      <button id="measure" onclick="registerAnchor()">Medir y registrar</button>
      <button class="secondary" onclick="refresh()">Actualizar</button>
      <button class="danger" onclick="resetAll()">Reiniciar calibracion</button>
    </div>
  </section>

  <section>
    <h2>Estado</h2>
    <div id="status" class="status">Cargando...</div>
  </section>

  <section>
    <h2>Anclas registradas</h2>
    <table>
      <thead><tr><th>ID</th><th>X (m)</th><th>Y (m)</th></tr></thead>
      <tbody id="anchors"></tbody>
    </table>
  </section>

  <section>
    <h2>Ultimas distancias</h2>
    <table>
      <thead><tr><th>Ancla</th><th>Distancia</th><th>RSSI</th><th>PD</th></tr></thead>
      <tbody id="readings"></tbody>
    </table>
  </section>
</main>

<script>
let busy = false;

function fmt(value, decimals = 3) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(decimals);
}

async function refresh() {
  const res = await fetch("/api/state");
  const state = await res.json();
  render(state);
}

function render(state) {
  const anchors = document.getElementById("anchors");
  anchors.innerHTML = state.anchors.map(a => `<tr><td class="mono">${a.id}</td><td>${fmt(a.x)}</td><td>${fmt(a.y)}</td></tr>`).join("");

  const nextId = Math.max(...state.anchors.map(a => a.id), 0) + 1;
  if (!busy) document.getElementById("target").value = nextId;

  const status = document.getElementById("status");
  if (!state.last_result) {
    status.className = "status";
    status.textContent = `AP ${state.ap_ssid} en ${state.ap_ip}. Ancla origen: ${state.origin_anchor_id}.`;
  } else {
    status.className = state.last_result.ok ? "status" : "status error";
    const r = state.last_result;
    status.textContent = r.ok
      ? `A${r.target_id} guardada en (${fmt(r.x)}, ${fmt(r.y)}) m. RMS ${fmt(r.rms)} m. ${r.message}`
      : r.message;
  }

  const readings = state.last_result && state.last_result.readings ? state.last_result.readings : [];
  document.getElementById("readings").innerHTML = readings.length
    ? readings.map(r => `<tr><td class="mono">${r.id}</td><td>${fmt(r.distance)} m</td><td>${fmt(r.rssi, 1)} dBm</td><td>${fmt(r.power_diff, 2)}</td></tr>`).join("")
    : `<tr><td colspan="4" class="muted">Todavia no hay mediciones.</td></tr>`;
}

async function registerAnchor() {
  busy = true;
  const button = document.getElementById("measure");
  const status = document.getElementById("status");
  button.disabled = true;
  status.className = "status";
  status.textContent = "Midiendo UWB... manten el beacon quieto unos segundos.";

  const params = new URLSearchParams({
    target: document.getElementById("target").value,
    side: document.getElementById("side").value,
    samples: document.getElementById("samples").value
  });

  try {
    const res = await fetch(`/api/register?${params.toString()}`, { method: "POST" });
    const state = await res.json();
    render(state);
  } catch (err) {
    status.className = "status error";
    status.textContent = `Error de comunicacion: ${err.message}`;
  } finally {
    button.disabled = false;
    busy = false;
  }
}

async function resetAll() {
  if (!confirm("Borrar todas las anclas registradas y volver a A0=(0,0)?")) return;
  await fetch("/api/reset", { method: "POST" });
  await refresh();
}

refresh();
setInterval(() => { if (!busy) refresh(); }, 5000);
</script>
</body>
</html>
)rawliteral";
}

void handleRoot() {
  server.send(200, "text/html; charset=utf-8", htmlPage());
}

void handleState() {
  sendJson(200, stateJson());
}

void handleRegister() {
  if (!server.hasArg("target")) {
    lastResult = LastResult();
    lastResult.hasResult = true;
    lastResult.ok = false;
    lastResult.message = "Falta el parametro target.";
    sendJson(400, stateJson());
    return;
  }

  int target = server.arg("target").toInt();
  int samples = server.hasArg("samples") ? server.arg("samples").toInt() : DEFAULT_SAMPLES;
  int side = server.hasArg("side") ? server.arg("side").toInt() : 1;

  if (target < 0 || target > 255) {
    lastResult = LastResult();
    lastResult.hasResult = true;
    lastResult.ok = false;
    lastResult.message = "El ID de ancla debe estar entre 0 y 255.";
    sendJson(400, stateJson());
    return;
  }

  samples = constrain(samples, 3, (int)MAX_SAMPLES);
  registerAnchorAtBeaconPosition((uint8_t)target, (uint8_t)samples, side >= 0 ? 1 : -1);
  sendJson(200, stateJson());
}

void handleReset() {
  resetCalibration();
  sendJson(200, stateJson());
}

void sendJson(int code, const String &json) {
  server.sendHeader("Cache-Control", "no-store");
  server.send(code, "application/json; charset=utf-8", json);
}
