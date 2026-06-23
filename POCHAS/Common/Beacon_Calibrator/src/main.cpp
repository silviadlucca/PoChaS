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
#define ORIGIN_ANCHOR_ID 1
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
const float SOFT_NLOS_PD_DB = 6.0f;
const float HARD_NLOS_PD_DB = 10.0f;


WebServer server(80);
Preferences prefs;

struct AnchorPoint {
  uint8_t id = 0;
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;
  bool valid = false;
};

struct DistanceReading {
  uint8_t id = 0;
  float distance = 0.0f;
  float horizontalDistance = 0.0f;
  float rssi = -120.0f;
  float powerDiff = 0.0f;
  uint8_t losState = 0;
  bool ok = false;
};

struct LastResult {
  bool hasResult = false;
  bool ok = false;
  uint8_t targetId = 0;
  float x = 0.0f;
  float y = 0.0f;
  float z = 0.0f;
  bool hasAlternative = false;
  float alternativeX = 0.0f;
  float alternativeY = 0.0f;
  float alternativeZ = 0.0f;
  float rms = 0.0f;
  uint8_t usedAnchors = 0;
  String message;
  DistanceReading readings[MAX_ANCHORS];
  uint8_t readingCount = 0;
};

AnchorPoint anchors[MAX_ANCHORS];
float pairwiseDistances[MAX_ANCHORS][MAX_ANCHORS] = {{0.0f}};
uint8_t anchorCount = 0;
bool heightsCalibrated = false;
float calibratedFloorOffset = 0.0f;
LastResult lastResult;

void initializeDW3000();
void loadAnchors();
void loadPairwiseDistances();
void saveAnchors();
void resetCalibration();
int findAnchorIndex(uint8_t id);
bool addOrUpdateAnchor(uint8_t id, float x, float y, float z);
void setPairwiseDistance(uint8_t idA, uint8_t idB, float distance);
float getPairwiseDistance(uint8_t idA, uint8_t idB);
bool performRanging(uint8_t anchorId, DistanceReading &reading);
bool measureAnchorMedian(uint8_t anchorId, uint8_t samples, DistanceReading &reading);
bool registerAnchorAtBeaconPosition(uint8_t targetId, uint8_t samples, int sideSign, bool useAlternative);
bool calibrateInitialAnchors(uint8_t samples, float floorOffset);
bool solveProvisionalPosition2D(const DistanceReading *readings, uint8_t readingCount, int sideSign, float &x, float &y, float &rms, String &message);
bool solveThreeSpherePosition(const DistanceReading *readings, bool useAlternative, float &x, float &y, float &z, float &altX, float &altY, float &altZ, float &rms, String &message);
bool solve3DLeastSquares(const DistanceReading *readings, uint8_t readingCount, float &x, float &y, float &z, float &rms, String &message);
bool solveLinear3x3(float matrix[3][3], float vector[3], float solution[3]);
String stateJson();
String anchorsExportJson();
String htmlPage();
void handleRoot();
void handleState();
void handleRegister();
void handleReset();
void handleCalibrateHeights();
void handleExportAnchors();
void sendJson(int code, const String &json);
String jsonEscape(const String &text);
uint8_t classifyLOSState(float pd);

uint8_t classifyLOSState(float pd) {
  if (pd > HARD_NLOS_PD_DB) return 2;
  if (pd >= SOFT_NLOS_PD_DB) return 1;
  return 0;
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  delay(300);

  loadAnchors();
  if (findAnchorIndex(ORIGIN_ANCHOR_ID) < 0) {
    resetCalibration();
  }
  loadPairwiseDistances();

  initializeDW3000();

  WiFi.mode(WIFI_AP);
  WiFi.setSleep(false);
  WiFi.softAP(AP_SSID, AP_PASSWORD);

  server.on("/", HTTP_GET, handleRoot);
  server.on("/api/state", HTTP_GET, handleState);
  server.on("/api/register", HTTP_POST, handleRegister);
  server.on("/api/reset", HTTP_POST, handleReset);
  server.on("/api/calibrate-heights", HTTP_POST, handleCalibrateHeights);
  server.on("/anchors.json", HTTP_GET, handleExportAnchors);
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
  heightsCalibrated = prefs.isKey("heightcal") ? prefs.getBool("heightcal", false) : false;
  calibratedFloorOffset = prefs.isKey("flooroff") ? prefs.getFloat("flooroff", 0.0f) : 0.0f;

  for (uint8_t i = 0; i < MAX_ANCHORS; i++) {
    anchors[i] = AnchorPoint();
    if (i >= anchorCount) {
      continue;
    }

    char key[8];
    snprintf(key, sizeof(key), "id%u", i);
    anchors[i].id = prefs.getUChar(key, 0);
    snprintf(key, sizeof(key), "x%u", i);
    anchors[i].x = prefs.isKey(key) ? prefs.getFloat(key, 0.0f) : 0.0f;
    snprintf(key, sizeof(key), "y%u", i);
    anchors[i].y = prefs.isKey(key) ? prefs.getFloat(key, 0.0f) : 0.0f;
    snprintf(key, sizeof(key), "z%u", i);
    anchors[i].z = prefs.isKey(key) ? prefs.getFloat(key, 0.0f) : 0.0f;
    anchors[i].valid = true;
  }
  prefs.end();
}

void loadPairwiseDistances() {
  for (uint8_t i = 0; i < MAX_ANCHORS; i++) {
    for (uint8_t j = 0; j < MAX_ANCHORS; j++) {
      pairwiseDistances[i][j] = 0.0f;
    }
  }

  prefs.begin("uwbcal", true);
  for (uint8_t i = 0; i < anchorCount; i++) {
    for (uint8_t j = i + 1; j < anchorCount; j++) {
      char key[16];
      uint8_t lowId = min(anchors[i].id, anchors[j].id);
      uint8_t highId = max(anchors[i].id, anchors[j].id);
      snprintf(key, sizeof(key), "d%u_%u", lowId, highId);
      if (prefs.isKey(key)) {
        float distance = prefs.getFloat(key, 0.0f);
        pairwiseDistances[i][j] = distance;
        pairwiseDistances[j][i] = distance;
      }
    }
  }
  prefs.end();
}

void saveAnchors() {
  prefs.begin("uwbcal", false);
  prefs.putUChar("count", anchorCount);
  prefs.putBool("heightcal", heightsCalibrated);
  prefs.putFloat("flooroff", calibratedFloorOffset);

  for (uint8_t i = 0; i < anchorCount; i++) {
    char key[8];
    snprintf(key, sizeof(key), "id%u", i);
    prefs.putUChar(key, anchors[i].id);
    snprintf(key, sizeof(key), "x%u", i);
    prefs.putFloat(key, anchors[i].x);
    snprintf(key, sizeof(key), "y%u", i);
    prefs.putFloat(key, anchors[i].y);
    snprintf(key, sizeof(key), "z%u", i);
    prefs.putFloat(key, anchors[i].z);
  }
  prefs.end();
}

void resetCalibration() {
  prefs.begin("uwbcal", false);
  prefs.clear();
  prefs.end();

  anchorCount = 1;
  heightsCalibrated = false;
  calibratedFloorOffset = 0.0f;
  for (uint8_t i = 0; i < MAX_ANCHORS; i++) {
    anchors[i] = AnchorPoint();
    for (uint8_t j = 0; j < MAX_ANCHORS; j++) {
      pairwiseDistances[i][j] = 0.0f;
    }
  }
  anchors[0].id = ORIGIN_ANCHOR_ID;
  anchors[0].x = 0.0f;
  anchors[0].y = 0.0f;
  anchors[0].z = 0.0f;
  anchors[0].valid = true;
  saveAnchors();

  lastResult = LastResult();
  lastResult.hasResult = true;
  lastResult.ok = true;
  lastResult.targetId = ORIGIN_ANCHOR_ID;
  lastResult.message = "Calibracion reiniciada. Registra A2 y A3 antes de calibrar el suelo.";
}

int findAnchorIndex(uint8_t id) {
  for (uint8_t i = 0; i < anchorCount; i++) {
    if (anchors[i].valid && anchors[i].id == id) {
      return i;
    }
  }
  return -1;
}

bool addOrUpdateAnchor(uint8_t id, float x, float y, float z) {
  int existing = findAnchorIndex(id);
  if (existing >= 0) {
    anchors[existing].x = x;
    anchors[existing].y = y;
    anchors[existing].z = z;
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
  anchors[anchorCount].z = z;
  anchors[anchorCount].valid = true;
  anchorCount++;
  saveAnchors();
  return true;
}

void setPairwiseDistance(uint8_t idA, uint8_t idB, float distance) {
  int indexA = findAnchorIndex(idA);
  int indexB = findAnchorIndex(idB);
  if (indexA < 0 || indexB < 0 || indexA == indexB || distance <= 0.0f) {
    return;
  }

  pairwiseDistances[indexA][indexB] = distance;
  pairwiseDistances[indexB][indexA] = distance;

  uint8_t lowId = min(idA, idB);
  uint8_t highId = max(idA, idB);
  char key[16];
  snprintf(key, sizeof(key), "d%u_%u", lowId, highId);
  prefs.begin("uwbcal", false);
  prefs.putFloat(key, distance);
  prefs.end();
}

float getPairwiseDistance(uint8_t idA, uint8_t idB) {
  int indexA = findAnchorIndex(idA);
  int indexB = findAnchorIndex(idB);
  if (indexA < 0 || indexB < 0) {
    return 0.0f;
  }
  return pairwiseDistances[indexA][indexB];
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
  reading.losState = classifyLOSState(reading.powerDiff);
  reading.ok = true;
  return true;
}

bool registerAnchorAtBeaconPosition(uint8_t targetId, uint8_t samples, int sideSign, bool useAlternative) {
  lastResult = LastResult();
  lastResult.hasResult = true;
  lastResult.targetId = targetId;

  if (targetId <= ORIGIN_ANCHOR_ID) {
    lastResult.ok = false;
    lastResult.message = "El ID de origen ya esta reservado para A1.";
    return false;
  }

  int existingIndex = findAnchorIndex(targetId);
  uint8_t expectedNextId = ORIGIN_ANCHOR_ID + anchorCount;
  if (existingIndex < 0 && targetId != expectedNextId) {
    lastResult.ok = false;
    lastResult.message = "Registra las anclas en orden consecutivo: A2, A3, A4...";
    return false;
  }

  if (!heightsCalibrated && targetId > ORIGIN_ANCHOR_ID + 2) {
    lastResult.ok = false;
    lastResult.message = "Antes de registrar A4 debes calibrar las alturas de A1-A3 desde el suelo.";
    return false;
  }

  if (heightsCalibrated && targetId <= ORIGIN_ANCHOR_ID + 2) {
    lastResult.ok = false;
    lastResult.message = "A1-A3 ya forman la referencia 3D. Reinicia la calibracion para volver a medirlas.";
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
      reading.horizontalDistance = reading.distance;
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
  float z = 0.0f;
  float rms = 0.0f;
  String message;
  float altX = 0.0f;
  float altY = 0.0f;
  float altZ = 0.0f;

  if (!heightsCalibrated) {
    if (readingCount != anchorCount) {
      lastResult.ok = false;
      lastResult.message = "Deben responder todas las anclas anteriores para guardar las distancias de calibracion.";
      return false;
    }
    if (!solveProvisionalPosition2D(readings, readingCount, sideSign, x, y, rms, message)) {
      lastResult.ok = false;
      lastResult.message = message;
      return false;
    }
    message += " Coordenadas provisionales; falta calibrar el suelo.";
  } else {
    if (readingCount < 3) {
      lastResult.ok = false;
      lastResult.message = "Se necesitan al menos tres anclas 3D visibles.";
      return false;
    }
    if (readingCount == 3) {
      if (!solveThreeSpherePosition(readings, useAlternative, x, y, z, altX, altY, altZ, rms, message)) {
        lastResult.ok = false;
        lastResult.message = message;
        return false;
      }
      lastResult.hasAlternative = true;
      lastResult.alternativeX = altX;
      lastResult.alternativeY = altY;
      lastResult.alternativeZ = altZ;
    } else if (!solve3DLeastSquares(readings, readingCount, x, y, z, rms, message)) {
      lastResult.ok = false;
      lastResult.message = message;
      return false;
    }
  }

  if (!addOrUpdateAnchor(targetId, x, y, z)) {
    lastResult.ok = false;
    lastResult.message = "No queda espacio para guardar mas anclas.";
    return false;
  }

  lastResult.ok = true;
  lastResult.x = x;
  lastResult.y = y;
  lastResult.z = z;
  lastResult.rms = rms;
  lastResult.message = message;

  for (uint8_t i = 0; i < readingCount; i++) {
    setPairwiseDistance(targetId, readings[i].id, readings[i].distance);
  }

  Serial.printf("[CAL] Anchor %u stored at (%.3f, %.3f, %.3f), RMS %.3f m\n", targetId, x, y, z, rms);
  return true;
}

bool calibrateInitialAnchors(uint8_t samples, float floorOffset) {
  lastResult = LastResult();
  lastResult.hasResult = true;
  lastResult.targetId = ORIGIN_ANCHOR_ID + 2;

  uint8_t id1 = ORIGIN_ANCHOR_ID;
  uint8_t id2 = ORIGIN_ANCHOR_ID + 1;
  uint8_t id3 = ORIGIN_ANCHOR_ID + 2;
  int index1 = findAnchorIndex(id1);
  int index2 = findAnchorIndex(id2);
  int index3 = findAnchorIndex(id3);
  if (index1 < 0 || index2 < 0 || index3 < 0) {
    lastResult.message = "Primero debes registrar provisionalmente A2 y A3.";
    return false;
  }

  float d12 = getPairwiseDistance(id1, id2);
  float d13 = getPairwiseDistance(id1, id3);
  float d23 = getPairwiseDistance(id2, id3);
  if (d12 <= 0.0f || d13 <= 0.0f || d23 <= 0.0f) {
    lastResult.message = "Faltan distancias entre A1, A2 y A3. Reinicia y registralas de nuevo.";
    return false;
  }

  DistanceReading floorReadings[3];
  uint8_t ids[3] = {id1, id2, id3};
  for (uint8_t i = 0; i < 3; i++) {
    if (!measureAnchorMedian(ids[i], samples, floorReadings[i])) {
      lastResult.message = "No respondieron las tres anclas. Comprueba que A1, A2 y A3 estan encendidas.";
      return false;
    }
    floorReadings[i].horizontalDistance = floorReadings[i].distance;
    lastResult.readings[i] = floorReadings[i];
  }
  lastResult.readingCount = 3;
  lastResult.usedAnchors = 3;

  float r1 = floorReadings[0].distance;
  float r2 = floorReadings[1].distance;
  float r3 = floorReadings[2].distance;
  if (r1 < 0.05f) {
    lastResult.message = "La distancia vertical a A1 es demasiado pequena.";
    return false;
  }

  float h1 = r1;
  float h2 = (r1 * r1 + r2 * r2 - d12 * d12) / (2.0f * r1);
  float x2Sq = r2 * r2 - h2 * h2;
  float h3 = (r1 * r1 + r3 * r3 - d13 * d13) / (2.0f * r1);
  float radial3Sq = r3 * r3 - h3 * h3;
  if (x2Sq <= 0.001f || radial3Sq <= 0.001f) {
    lastResult.message = "Las distancias no forman una geometria 3D valida. Repite la calibracion del suelo.";
    return false;
  }

  float x2 = sqrtf(x2Sq);
  float x3 = (radial3Sq + x2 * x2 + (h3 - h2) * (h3 - h2) - d23 * d23) / (2.0f * x2);
  float y3Sq = radial3Sq - x3 * x3;
  if (y3Sq < -0.05f) {
    lastResult.message = "Las medidas de A1-A3 son incompatibles. Repite con linea de vision y mas muestras.";
    return false;
  }
  y3Sq = max(0.0f, y3Sq);
  float ySign = anchors[index3].y < 0.0f ? -1.0f : 1.0f;

  anchors[index1].x = 0.0f;
  anchors[index1].y = 0.0f;
  anchors[index1].z = floorOffset + h1;
  anchors[index2].x = x2;
  anchors[index2].y = 0.0f;
  anchors[index2].z = floorOffset + h2;
  anchors[index3].x = x3;
  anchors[index3].y = ySign * sqrtf(y3Sq);
  anchors[index3].z = floorOffset + h3;

  if (anchors[index1].z < 0.0f || anchors[index2].z < 0.0f || anchors[index3].z < 0.0f) {
    lastResult.message = "La solucion situa alguna ancla bajo el suelo. Revisa la colocacion del beacon.";
    return false;
  }

  heightsCalibrated = true;
  calibratedFloorOffset = floorOffset;
  saveAnchors();

  lastResult.ok = true;
  lastResult.x = anchors[index3].x;
  lastResult.y = anchors[index3].y;
  lastResult.z = anchors[index3].z;
  lastResult.rms = 0.0f;
  lastResult.message = "Alturas A1-A3 calibradas automaticamente. Ya puedes registrar A4.";
  return true;
}

bool solveProvisionalPosition2D(const DistanceReading *readings, uint8_t readingCount, int sideSign, float &x, float &y, float &rms, String &message) {
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

    x = anchors[idx].x + readings[0].horizontalDistance;
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

    float r0 = readings[0].horizontalDistance;
    float r1 = readings[1].horizontalDistance;
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
  float r0 = readings[0].horizontalDistance;
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
    float ci = r0 * r0 - readings[i].horizontalDistance * readings[i].horizontalDistance
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
    float error = predicted - readings[i].horizontalDistance;
    errSq += error * error;
    used++;
  }

  rms = used > 0 ? sqrtf(errSq / used) : 0.0f;
  message = "Posicion calculada por trilateracion 2D con minimos cuadrados.";
  return true;
}

bool solveThreeSpherePosition(const DistanceReading *readings, bool useAlternative, float &x, float &y, float &z,
                              float &altX, float &altY, float &altZ, float &rms, String &message) {
  float points[3][3];
  float radii[3];
  for (uint8_t n = 0; n < 3; n++) {
    int idx = findAnchorIndex(readings[n].id);
    if (idx < 0) {
      message = "Una medicion no corresponde a un ancla 3D conocida.";
      return false;
    }
    points[n][0] = anchors[idx].x;
    points[n][1] = anchors[idx].y;
    points[n][2] = anchors[idx].z;
    radii[n] = readings[n].distance;
  }

  float p21[3] = {points[1][0] - points[0][0], points[1][1] - points[0][1], points[1][2] - points[0][2]};
  float d = sqrtf(p21[0] * p21[0] + p21[1] * p21[1] + p21[2] * p21[2]);
  if (d < 0.05f) {
    message = "A1 y A2 estan demasiado juntas para trilateracion 3D.";
    return false;
  }

  float ex[3] = {p21[0] / d, p21[1] / d, p21[2] / d};
  float p31[3] = {points[2][0] - points[0][0], points[2][1] - points[0][1], points[2][2] - points[0][2]};
  float projection = ex[0] * p31[0] + ex[1] * p31[1] + ex[2] * p31[2];
  float orthogonal[3] = {
    p31[0] - projection * ex[0],
    p31[1] - projection * ex[1],
    p31[2] - projection * ex[2]
  };
  float j = sqrtf(orthogonal[0] * orthogonal[0] + orthogonal[1] * orthogonal[1] + orthogonal[2] * orthogonal[2]);
  if (j < 0.05f) {
    message = "A1, A2 y A3 son casi colineales; no definen una referencia 3D estable.";
    return false;
  }

  float ey[3] = {orthogonal[0] / j, orthogonal[1] / j, orthogonal[2] / j};
  float ez[3] = {
    ex[1] * ey[2] - ex[2] * ey[1],
    ex[2] * ey[0] - ex[0] * ey[2],
    ex[0] * ey[1] - ex[1] * ey[0]
  };

  float localX = (radii[0] * radii[0] - radii[1] * radii[1] + d * d) / (2.0f * d);
  float localY = (radii[0] * radii[0] - radii[2] * radii[2] + projection * projection + j * j) / (2.0f * j)
               - (projection * localX / j);
  float localZSq = radii[0] * radii[0] - localX * localX - localY * localY;
  if (localZSq < -0.20f) {
    message = "Las tres esferas no se intersectan. Repite las medidas de A4.";
    return false;
  }
  localZSq = max(0.0f, localZSq);
  float localZ = sqrtf(localZSq);

  float base[3] = {
    points[0][0] + localX * ex[0] + localY * ey[0],
    points[0][1] + localX * ex[1] + localY * ey[1],
    points[0][2] + localX * ex[2] + localY * ey[2]
  };
  float candidates[2][3] = {
    {base[0] + localZ * ez[0], base[1] + localZ * ez[1], base[2] + localZ * ez[2]},
    {base[0] - localZ * ez[0], base[1] - localZ * ez[1], base[2] - localZ * ez[2]}
  };

  float meanKnownZ = (points[0][2] + points[1][2] + points[2][2]) / 3.0f;
  int automatic = 0;
  if (candidates[0][2] < 0.0f && candidates[1][2] >= 0.0f) {
    automatic = 1;
  } else if ((candidates[0][2] >= 0.0f) == (candidates[1][2] >= 0.0f)) {
    automatic = fabsf(candidates[1][2] - meanKnownZ) < fabsf(candidates[0][2] - meanKnownZ) ? 1 : 0;
  }

  int selected = useAlternative ? 1 - automatic : automatic;
  int other = 1 - selected;
  if (candidates[selected][2] < 0.0f) {
    message = candidates[other][2] >= 0.0f
      ? "La solucion seleccionada queda bajo el suelo; usa la solucion automatica."
      : "Ambas soluciones de A4 quedan bajo el suelo. Repite las medidas.";
    return false;
  }

  x = candidates[selected][0];
  y = candidates[selected][1];
  z = candidates[selected][2];
  altX = candidates[other][0];
  altY = candidates[other][1];
  altZ = candidates[other][2];

  float errorSq = 0.0f;
  for (uint8_t n = 0; n < 3; n++) {
    float dx = x - points[n][0];
    float dy = y - points[n][1];
    float dz = z - points[n][2];
    float error = sqrtf(dx * dx + dy * dy + dz * dz) - radii[n];
    errorSq += error * error;
  }
  rms = sqrtf(errorSq / 3.0f);
  message = useAlternative
    ? "A4 calculada con la solucion 3D alternativa."
    : "A4 calculada con la solucion 3D automatica; se muestra tambien la alternativa.";
  return true;
}

bool solveLinear3x3(float matrix[3][3], float vector[3], float solution[3]) {
  float augmented[3][4];
  for (uint8_t row = 0; row < 3; row++) {
    for (uint8_t col = 0; col < 3; col++) {
      augmented[row][col] = matrix[row][col];
    }
    augmented[row][3] = vector[row];
  }

  for (uint8_t pivot = 0; pivot < 3; pivot++) {
    uint8_t bestRow = pivot;
    for (uint8_t row = pivot + 1; row < 3; row++) {
      if (fabsf(augmented[row][pivot]) > fabsf(augmented[bestRow][pivot])) {
        bestRow = row;
      }
    }
    if (fabsf(augmented[bestRow][pivot]) < 0.00001f) {
      return false;
    }
    if (bestRow != pivot) {
      for (uint8_t col = pivot; col < 4; col++) {
        float tmp = augmented[pivot][col];
        augmented[pivot][col] = augmented[bestRow][col];
        augmented[bestRow][col] = tmp;
      }
    }

    float divisor = augmented[pivot][pivot];
    for (uint8_t col = pivot; col < 4; col++) {
      augmented[pivot][col] /= divisor;
    }
    for (uint8_t row = 0; row < 3; row++) {
      if (row == pivot) continue;
      float factor = augmented[row][pivot];
      for (uint8_t col = pivot; col < 4; col++) {
        augmented[row][col] -= factor * augmented[pivot][col];
      }
    }
  }

  for (uint8_t row = 0; row < 3; row++) {
    solution[row] = augmented[row][3];
  }
  return true;
}

bool solve3DLeastSquares(const DistanceReading *readings, uint8_t readingCount, float &x, float &y, float &z,
                         float &rms, String &message) {
  if (readingCount < 4) {
    message = "Se necesitan cuatro anclas para minimos cuadrados 3D.";
    return false;
  }

  int refIndex = findAnchorIndex(readings[0].id);
  if (refIndex < 0) return false;
  const AnchorPoint &ref = anchors[refIndex];
  float r0 = readings[0].distance;
  float normal[3][3] = {{0.0f}};
  float rhs[3] = {0.0f, 0.0f, 0.0f};

  for (uint8_t n = 1; n < readingCount; n++) {
    int idx = findAnchorIndex(readings[n].id);
    if (idx < 0) continue;
    const AnchorPoint &anchor = anchors[idx];
    float row[3] = {
      2.0f * (anchor.x - ref.x),
      2.0f * (anchor.y - ref.y),
      2.0f * (anchor.z - ref.z)
    };
    float value = r0 * r0 - readings[n].distance * readings[n].distance
                + anchor.x * anchor.x + anchor.y * anchor.y + anchor.z * anchor.z
                - ref.x * ref.x - ref.y * ref.y - ref.z * ref.z;
    for (uint8_t i = 0; i < 3; i++) {
      rhs[i] += row[i] * value;
      for (uint8_t j = 0; j < 3; j++) {
        normal[i][j] += row[i] * row[j];
      }
    }
  }

  float solution[3];
  if (!solveLinear3x3(normal, rhs, solution)) {
    message = "La geometria 3D es degenerada; separa mejor las alturas y posiciones de las anclas.";
    return false;
  }
  x = solution[0];
  y = solution[1];
  z = solution[2];
  if (z < 0.0f) {
    message = "La solucion 3D queda bajo el suelo. Repite las medidas.";
    return false;
  }

  float errorSq = 0.0f;
  for (uint8_t n = 0; n < readingCount; n++) {
    int idx = findAnchorIndex(readings[n].id);
    if (idx < 0) continue;
    float dx = x - anchors[idx].x;
    float dy = y - anchors[idx].y;
    float dz = z - anchors[idx].z;
    float error = sqrtf(dx * dx + dy * dy + dz * dz) - readings[n].distance;
    errorSq += error * error;
  }
  rms = sqrtf(errorSq / readingCount);
  message = "Posicion calculada por minimos cuadrados 3D.";
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
  json += ",\"heights_calibrated\":";
  json += heightsCalibrated ? "true" : "false";
  json += ",\"floor_offset\":";
  json += String(calibratedFloorOffset, 3);
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
    json += ",\"z\":";
    json += String(anchors[i].z, 3);
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
    json += ",\"z\":";
    json += String(lastResult.z, 3);
    json += ",\"rms\":";
    json += String(lastResult.rms, 3);
    json += ",\"used_anchors\":";
    json += (int)lastResult.usedAnchors;
    json += ",\"alternative\":";
    if (lastResult.hasAlternative) {
      json += "{\"x\":";
      json += String(lastResult.alternativeX, 3);
      json += ",\"y\":";
      json += String(lastResult.alternativeY, 3);
      json += ",\"z\":";
      json += String(lastResult.alternativeZ, 3);
      json += "}";
    } else {
      json += "null";
    }
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
      json += ",\"horizontal_distance\":";
      json += String(lastResult.readings[i].horizontalDistance, 3);
      json += ",\"rssi\":";
      json += String(lastResult.readings[i].rssi, 1);
      json += ",\"power_diff\":";
      json += String(lastResult.readings[i].powerDiff, 2);
      json += ",\"los_state\":";
      json += (int)lastResult.readings[i].losState;
      json += "}";
    }
    json += "]}";
  }

  json += "}";
  return json;
}

String anchorsExportJson() {
  String json;
  json.reserve(1024);
  json += "{\n";
  for (uint8_t i = 0; i < anchorCount; i++) {
    json += "  \"";
    json += (int)anchors[i].id;
    json += "\": [";
    json += String(anchors[i].x, 3);
    json += ", ";
    json += String(anchors[i].y, 3);
    json += ", ";
    json += String(anchors[i].z, 3);
    json += "]";
    if (i + 1 < anchorCount) {
      json += ",";
    }
    json += "\n";
  }
  json += "}\n";
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
    button, .button-link { border: 0; border-radius: 7px; padding: 11px 14px; background: #1769e0; color: white; font-weight: 700; cursor: pointer; text-decoration: none; display: inline-block; box-sizing: border-box; }
    button.secondary, .button-link.secondary { background: #e7ecf5; color: #26344d; }
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
    <h2>Calibracion automatica de alturas</h2>
    <p>Tras registrar A2 y A3, enciende A1-A3 y coloca el beacon en el suelo exactamente debajo de la antena de A1.</p>
    <div class="grid">
      <div>
        <label for="floorOffset">Altura de la antena del beacon sobre el suelo (m)</label>
        <input id="floorOffset" type="number" min="0" max="1" step="0.001" value="0">
      </div>
    </div>
    <div class="actions">
      <button id="calibrate" onclick="calibrateHeights()">Calibrar alturas A1-A3</button>
      <a class="button-link secondary" href="/anchors.json" download="anchors.json">Descargar JSON</a>
    </div>
    <div id="calibrationStatus" class="status" style="margin-top:12px">Calibracion 3D pendiente.</div>
  </section>

  <section>
    <h2>Nueva ancla</h2>
    <div class="grid">
      <div>
        <label for="target">ID de la nueva ancla</label>
        <input id="target" type="number" min="2" max="255" value="2">
      </div>
      <div>
        <label for="side">Lado provisional de A3</label>
        <select id="side">
          <option value="1">Y positivo</option>
          <option value="-1">Y negativo</option>
        </select>
      </div>
      <div>
        <label for="alternative">Solucion 3D de A4</label>
        <select id="alternative">
          <option value="0">Automatica</option>
          <option value="1">Alternativa</option>
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
      <thead><tr><th>ID</th><th>X (m)</th><th>Y (m)</th><th>Z (m)</th></tr></thead>
      <tbody id="anchors"></tbody>
    </table>
  </section>

  <section>
    <h2>Ultimas distancias</h2>
    <p class="muted">PD compara la potencia total recibida con la del primer trayecto: &lt;6 dB suele ser LOS, 6-10 dB posible multitrayecto/NLOS y &gt;10 dB NLOS fuerte.</p>
    <table>
      <thead><tr><th>Ancla</th><th>Distancia UWB</th><th>RSSI</th><th>PD</th><th>Canal (LOS)</th></tr></thead>
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
  anchors.innerHTML = state.anchors.map(a => `<tr><td class="mono">${a.id}</td><td>${fmt(a.x)}</td><td>${fmt(a.y)}</td><td>${fmt(a.z)}</td></tr>`).join("");

  const calibrationStatus = document.getElementById("calibrationStatus");
  calibrationStatus.className = state.heights_calibrated ? "status" : "status error";
  calibrationStatus.textContent = state.heights_calibrated
    ? `Referencia 3D calibrada. Offset del beacon: ${fmt(state.floor_offset)} m.`
    : "Pendiente: registra A2 y A3, enciende A1-A3 y calibra desde el suelo bajo A1.";
  if (state.heights_calibrated) document.getElementById("floorOffset").value = state.floor_offset;

  const nextId = Math.max(...state.anchors.map(a => a.id), 0) + 1;
  if (!busy) document.getElementById("target").value = nextId;

  const status = document.getElementById("status");
  if (!state.last_result) {
    status.className = "status";
    status.textContent = `AP ${state.ap_ssid} en ${state.ap_ip}. Ancla origen: ${state.origin_anchor_id}.`;
  } else {
    status.className = state.last_result.ok ? "status" : "status error";
    const r = state.last_result;
    if (r.ok) {
      status.textContent = `A${r.target_id} en (${fmt(r.x)}, ${fmt(r.y)}, ${fmt(r.z)}) m. RMS ${fmt(r.rms)} m. ${r.message}`;
      if (r.alternative) {
        status.textContent += ` Alternativa: (${fmt(r.alternative.x)}, ${fmt(r.alternative.y)}, ${fmt(r.alternative.z)}) m.`;
      }
    } else {
      status.textContent = r.message;
    }
  }

  const readings = state.last_result && state.last_result.readings ? state.last_result.readings : [];
  
  // Función auxiliar para pintar el estado LOS
  const getLosBadge = (losState) => {
    if (losState === 0) return '<span style="color: #0b7a39; font-weight: 700;">LOS</span>';
    if (losState === 1) return '<span style="color: #b86b00; font-weight: 700;">Soft NLOS</span>';
    if (losState === 2) return '<span style="color: #c92a2a; font-weight: 700;">Hard NLOS</span>';
    return '<span style="color: #6a7487;">-</span>';
  };

  document.getElementById("readings").innerHTML = readings.length
    ? readings.map(r => `<tr>
        <td class="mono">${r.id}</td>
        <td>${fmt(r.distance)} m</td>
        <td>${fmt(r.rssi, 1)} dBm</td>
        <td>${fmt(r.power_diff, 2)} dB</td>
        <td>${getLosBadge(r.los_state)}</td>
      </tr>`).join("")
    : `<tr><td colspan="5" class="muted">Todavia no hay mediciones.</td></tr>`;
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
    alternative: document.getElementById("alternative").value,
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

async function calibrateHeights() {
  busy = true;
  const button = document.getElementById("calibrate");
  button.disabled = true;
  const params = new URLSearchParams({
    floor_offset: document.getElementById("floorOffset").value,
    samples: document.getElementById("samples").value
  });
  try {
    const res = await fetch(`/api/calibrate-heights?${params.toString()}`, { method: "POST" });
    render(await res.json());
  } finally {
    button.disabled = false;
    busy = false;
  }
}

async function resetAll() {
  if (!confirm("Borrar todas las anclas registradas y volver a A1=(0,0)?")) return;
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
  bool useAlternative = server.hasArg("alternative") && server.arg("alternative").toInt() == 1;

  if (target <= ORIGIN_ANCHOR_ID || target > 255) {
    lastResult = LastResult();
    lastResult.hasResult = true;
    lastResult.ok = false;
    lastResult.message = "El ID de la nueva ancla debe ser mayor que el ID del origen.";
    sendJson(400, stateJson());
    return;
  }

  samples = constrain(samples, 3, (int)MAX_SAMPLES);
  registerAnchorAtBeaconPosition((uint8_t)target, (uint8_t)samples, side >= 0 ? 1 : -1, useAlternative);
  sendJson(200, stateJson());
}

void handleReset() {
  resetCalibration();
  sendJson(200, stateJson());
}

void handleCalibrateHeights() {
  float floorOffset = server.hasArg("floor_offset") ? server.arg("floor_offset").toFloat() : 0.0f;
  int samples = server.hasArg("samples") ? server.arg("samples").toInt() : DEFAULT_SAMPLES;
  if (!isfinite(floorOffset) || floorOffset < 0.0f || floorOffset > 1.0f) {
    lastResult = LastResult();
    lastResult.hasResult = true;
    lastResult.ok = false;
    lastResult.message = "El offset de la antena del beacon debe estar entre 0 y 1 metro.";
    sendJson(400, stateJson());
    return;
  }
  samples = constrain(samples, 3, (int)MAX_SAMPLES);
  calibrateInitialAnchors((uint8_t)samples, floorOffset);
  sendJson(200, stateJson());
}

void handleExportAnchors() {
  server.sendHeader("Cache-Control", "no-store");
  server.sendHeader("Content-Disposition", "attachment; filename=\"anchors.json\"");
  server.send(200, "application/json; charset=utf-8", anchorsExportJson());
}

void sendJson(int code, const String &json) {
  server.sendHeader("Cache-Control", "no-store");
  server.send(code, "application/json; charset=utf-8", json);
}
