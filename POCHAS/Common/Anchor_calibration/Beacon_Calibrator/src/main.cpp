#include <Arduino.h>
#include <SPI.h>
#include <WiFi.h>
#include <WebServer.h>
#include <Preferences.h>
#include "DW3000.h"

#ifndef BEACON_UWB_ID
#define BEACON_UWB_ID 250
#endif

static const char *AP_SSID = "Beacon-Calibrator";
static const char *AP_PASSWORD = "anchors1234";

static const unsigned long SERIAL_BAUD_RATE = 921600;
static const uint8_t MAX_ANCHORS = 15;
static const uint8_t DEFAULT_SAMPLES = 7;
static const unsigned long RESPONSE_TIMEOUT_MS = 14;
static const unsigned long TRANSACTION_TIMEOUT_MS = 55;
static const float MAX_REASONABLE_RANGE_M = 80.0f;

WebServer server(80);
Preferences prefs;

float distancias[MAX_ANCHORS][MAX_ANCHORS] = {{0.0f}};

struct DistanceReading {
  uint8_t id = 0;
  float distance = 0.0f;
  bool ok = false;
};

void initializeDW3000();
bool performRanging(uint8_t anchorId, DistanceReading &reading);
bool measureAnchorMedian(uint8_t anchorId, uint8_t samples, DistanceReading &reading);
void loadDistances();
void saveDistance(uint8_t from, uint8_t to, float distance);
void clearDistances();

String generateJson();
String htmlPage();
void handleRoot();
void handleMeasure();
void handleDownload();
void handleReset();

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  delay(300);

  loadDistances();
  
  SPI.begin();
  initializeDW3000();

  WiFi.mode(WIFI_AP);
  WiFi.setSleep(false);
  WiFi.softAP(AP_SSID, AP_PASSWORD);

  server.on("/", HTTP_GET, handleRoot);
  server.on("/api/measure", HTTP_POST, handleMeasure);
  server.on("/api/reset", HTTP_POST, handleReset);
  server.on("/data.json", HTTP_GET, handleDownload);
  server.begin();

  Serial.println("\n=== DISTANCES UWB ===");
  Serial.printf("WiFi: %s / %s\n", AP_SSID, AP_PASSWORD);
  Serial.printf("Web: http://%s/\n", WiFi.softAPIP().toString().c_str());
}

void loop() {
  server.handleClient();
}

void initializeDW3000() {
  DW3000.begin();
  SPI.setFrequency(8000000);

  DW3000.hardReset();
  delay(100);
  DW3000.softReset();
  delay(100);

  int retries = 0;
  while (!DW3000.checkForIDLE() && retries < 5) {
    delay(50);
    retries++;
  }
  
  if (retries >= 5) {
    Serial.println("[Aviso] DW3000 did not report IDLE status, forcing initialization.");
  }

  DW3000.setChannel(CHANNEL_5);
  DW3000.setPreambleCode(9);
  DW3000.setSenderID(BEACON_UWB_ID);
  DW3000.init();
  SPI.setFrequency(20000000);
  DW3000.setupGPIO();
  DW3000.configureAsTX();
  DW3000.clearSystemStatus();
}

bool performRanging(uint8_t anchorId, DistanceReading &reading) {
  reading = DistanceReading();
  reading.id = anchorId;

  int currStage = 0;
  int tRoundA = 0, tReplyA = 0;
  long long rx = 0, tx = 0;
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
        if (rxStatus == 0) break;
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
        if (rxStatus == 0) break;
        DW3000.clearSystemStatus();
        if (rxStatus == 1 && !DW3000.ds_isErrorFrame() && DW3000.ds_getStage() == 4) {
          clockOffset = DW3000.getRawClockOffset();
          int tRoundB = DW3000.read(0x12, 0x04);
          int tReplyB = DW3000.read(0x12, 0x08);
          int rangingTime = DW3000.ds_processRTInfo(tRoundA, tReplyA, tRoundB, tReplyB, clockOffset);
          float distance = DW3000.convertToCM(rangingTime) / 100.0f;

          DW3000.configureAsTX();
          if (!isfinite(distance) || distance <= 0.0f || distance > MAX_REASONABLE_RANGE_M) return false;

          reading.distance = distance;
          reading.ok = true;
          return true;
        }
        DW3000.configureAsTX();
        return false;
      }
    }
  }
  DW3000.configureAsTX();
  return false;
}

bool measureAnchorMedian(uint8_t anchorId, uint8_t samples, DistanceReading &reading) {
  float distances[15];
  uint8_t okCount = 0;

  for (uint8_t sample = 0; sample < samples; sample++) {
    DistanceReading attemptReading;
    bool ok = false;
    
    for (uint8_t attempt = 0; attempt < 3 && !ok; attempt++) {
      ok = performRanging(anchorId, attemptReading);
      if (!ok) delay(15);
    }
    
    if (!ok && sample == 0) {
      reading.id = anchorId;
      return false;
    }

    if (ok) {
      distances[okCount++] = attemptReading.distance;
    }
    delay(20);
  }

  if (okCount == 0) {
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
  reading.ok = true;
  return true;
}

void loadDistances() {
  prefs.begin("uwbdata", true);
  for (uint8_t i = 1; i < MAX_ANCHORS; i++) {
    for (uint8_t j = 1; j < MAX_ANCHORS; j++) {
      char key[16];
      snprintf(key, sizeof(key), "d%u_%u", i, j);
      distancias[i][j] = prefs.getFloat(key, 0.0f);
    }
  }
  prefs.end();
}

void saveDistance(uint8_t from, uint8_t to, float distance) {
  distancias[from][to] = distance;
  char key[16];
  snprintf(key, sizeof(key), "d%u_%u", from, to);
  prefs.begin("uwbdata", false);
  prefs.putFloat(key, distance);
  prefs.end();
}

void clearDistances() {
  for (uint8_t i = 0; i < MAX_ANCHORS; i++) {
    for (uint8_t j = 0; j < MAX_ANCHORS; j++) {
      distancias[i][j] = 0.0f;
    }
  }
  prefs.begin("uwbdata", false);
  prefs.clear();
  prefs.end();
}

String generateJson() {
  String json = "{\n";
  bool firstOuter = true;
  for (uint8_t current = 1; current < MAX_ANCHORS; current++) {
    bool hasMeasurements = false;
    String nodeData = "";
    
    for (uint8_t target = 1; target < MAX_ANCHORS; target++) {
      if (distancias[current][target] > 0.0f) {
        if (hasMeasurements) nodeData += ", ";
        nodeData += "\"" + String(target) + "\": " + String(distancias[current][target], 3);
        hasMeasurements = true;
      }
    }

    if (hasMeasurements) {
      if (!firstOuter) json += ",\n";
      json += "  \"" + String(current) + "\": { " + nodeData + " }";
      firstOuter = false;
    }
  }
  json += "\n}\n";
  return json;
}

String htmlPage() {
  return R"rawliteral(
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Distances UWB</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #f5f7fb; color: #172033; max-width: 600px; margin: 0 auto; padding: 20px; }
    section { background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }
    button, input { padding: 10px; border-radius: 6px; font-size: 1rem; }
    input { width: 100px; border: 1px solid #ccc; margin-right: 10px; }
    button { background: #1769e0; color: white; border: none; cursor: pointer; }
    button.secondary { background: #4caf50; }
    button.danger { background: #e53935; }
    button:disabled { opacity: 0.6; }
    pre { background: #eee; padding: 10px; border-radius: 6px; overflow-x: auto; }
    .success { color: #0b7a39; font-weight: bold; }
    .error { color: #c92a2a; font-weight: bold; }
  </style>
</head>
<body>
  <h2>Distances UWB</h2>
  
  <section>
    <label><strong>I am in anchor ID:</strong></label><br><br>
    <input type="number" id="currentId" min="1" max="14" value="2">
    <button id="btnMeasure" onclick="measure()">Measure Distances</button>
    <p id="status" style="color: #666;"></p>
  </section>

  <section>
    <button class="secondary" onclick="window.location.href='/data.json'">Download JSON</button>
    <button class="danger" onclick="resetData()" style="float: right;">Clear All</button>
    <h3>Current Status (JSON):</h3>
    <pre id="jsonPreview">Loading...</pre>
  </section>

<script>
  async function loadPreview() {
    const res = await fetch('/data.json');
    document.getElementById('jsonPreview').textContent = await res.text();
  }
  
  async function measure() {
    const btn = document.getElementById('btnMeasure');
    const status = document.getElementById('status');
    const inputId = document.getElementById('currentId');
    const id = inputId.value;
    
    btn.disabled = true;
    status.className = "";
    status.textContent = "Scanning active anchors... (this will take a few seconds)";
    
    try {
      const res = await fetch(`/api/measure?current=${id}`, { method: 'POST' });
      const data = await res.json();
      
      if (data.count > 0) {
        status.className = "success";
        status.textContent = `Measurement saved! Found ${data.count} anchors.`;
        inputId.value = parseInt(id) + 1;
      } else {
        status.className = "error";
        status.textContent = "Warning: No other anchors detected or communication failed.";
      }
      loadPreview();
    } catch(e) {
      status.className = "error";
      status.textContent = "Error connecting to ESP32.";
    }
    btn.disabled = false;
  }

  async function resetData() {
    if(confirm("Are you sure you want to clear all measurements?")) {
      await fetch('/api/reset', { method: 'POST' });
      loadPreview();
    }
  }

  loadPreview();
</script>
</body>
</html>
)rawliteral";
}

void handleRoot() {
  server.send(200, "text/html; charset=utf-8", htmlPage());
}

void handleMeasure() {
  if (!server.hasArg("current")) {
    server.send(400, "application/json", "{\"error\":\"Falta ID actual\"}");
    return;
  }
  
  uint8_t currentId = server.arg("current").toInt();
  int anclasEncontradas = 0;
  
  Serial.printf("\nStarting scanning from anchor %u...\n", currentId);

  for (uint8_t target = 1; target < MAX_ANCHORS; target++) {
    if (target == currentId) continue;
    
    // FIX 1: Reiniciar el estado del hardware para cada ancla.
    // Esto asegura que los timeouts de las anclas anteriores 
    // no bloqueen la recepción de la actual.
    initializeDW3000(); 
    
    DistanceReading reading;
    
    if (measureAnchorMedian(target, DEFAULT_SAMPLES, reading)) {
      saveDistance(currentId, target, reading.distance);
      anclasEncontradas++;
      Serial.printf("-> Success: Anchor %u at %.2f meters\n", target, reading.distance);
    }

    // FIX 2: Ceder tiempo al sistema operativo del ESP32
    // Evita que el stack WiFi se caiga o el Watchdog salte.
    yield(); 
  }
  
  Serial.println("Scanning completed.");
  
  String response = "{\"success\":true,\"count\":";
  response += anclasEncontradas;
  response += "}";
  
  server.send(200, "application/json", response);
}
void handleReset() {
  clearDistances();
  server.send(200, "text/plain", "Cleared");
}

void handleDownload() {
  server.sendHeader("Content-Disposition", "attachment; filename=\"distances.json\"");
  server.send(200, "application/json; charset=utf-8", generateJson());
}