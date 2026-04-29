#include <Arduino.h>
#include <SPI.h>
#include "DW3000.h"
#include <ArduinoJson.h>


// FreeRTOS Includes
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>

// ===== PROTOTIPOS DE FUNCIONES =====
// En C++ estándar (PlatformIO), las funciones deben declararse antes de usarse.
uint8_t classifyLOSState(float pd);
float constrainSuspiciousPositiveJump(float measurement, int anchor_idx, uint8_t los_state, unsigned long now_ms);
float kalmanFilterDistance(float measurement, int anchor_id);
float calculateMedian(float new_val, int anchor_idx);
void TaskUWB(void *pvParameters);
void TaskSerial(void *pvParameters);

// ===== TAG IDENTIFICATION =====
#define TAG_ID 1 
#define MAX_ANCHORS 10

// ===== SERIAL CONFIGURATION =====
const unsigned long SERIAL_BAUD_RATE = 921600;
const size_t SERIAL_JSON_CAPACITY = 4096;

// ===== TDMA Configuration (INDOOR) =====
const unsigned long TDMA_CYCLE_MS = 33;
// Target: ~30 Hz
const unsigned long TDMA_SLOT_DURATION_MS = 33;  // Full cycle for this tag

// ===== RANGING CONFIGURATION =====
int NUM_ANCHORS = MAX_ANCHORS; 
int ID_PONG[MAX_ANCHORS] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10};

// Queue for Inter-Core Communication
struct TagDataPacket {
    float anchor_dist[MAX_ANCHORS];
    float anchor_raw_dist[MAX_ANCHORS];
    float anchor_rssi[MAX_ANCHORS];
    float anchor_pd[MAX_ANCHORS];
    bool anchor_resp[MAX_ANCHORS];
    uint8_t anchor_los[MAX_ANCHORS];
    uint8_t anchors_visible;
    unsigned long timestamp;
};
QueueHandle_t uwbQueue;

// ===== DYNAMIC ANCHOR SKIPPING (Core 1 Local) =====
bool anchor_is_active[MAX_ANCHORS] = {true, true, true, true, true, true, true, true, true, true};
int anchor_fail_count[MAX_ANCHORS] = {0};
unsigned long anchor_inactive_ts[MAX_ANCHORS] = {0};
const int MAX_FAILURES = 2;
const unsigned long RETRY_INTERVAL = 2000;
// 2 seconds

// Variables for Kalman Filter (Core 1 Local)
float kalman_dist[MAX_ANCHORS][2] = { {0} };
float kalman_dist_q = 0.06;
float kalman_dist_r = 0.06; 
unsigned long anchor_last_measurement_ts[MAX_ANCHORS] = {0};

// ===== MEDIAN FILTER VARIABLES (Core 1 Local) =====
const int MEDIAN_WINDOW_SIZE = 5;
float median_buffer[MAX_ANCHORS][MEDIAN_WINDOW_SIZE] = {0};
int median_idx[MAX_ANCHORS] = {0};
bool median_init[MAX_ANCHORS] = {false};

// ===== HELPER FUNCTIONS =====

const float MAX_TAG_SPEED_MPS = 2.5f;
const float BASE_RANGE_JUMP_M = 0.12f;
const unsigned long RANGE_FILTER_STALE_MS = 1200;
const float SOFT_NLOS_PD_DB = 6.0f;
const float HARD_NLOS_PD_DB = 10.0f;

uint8_t classifyLOSState(float pd) {
  if (pd > HARD_NLOS_PD_DB) return 2;
  if (pd >= SOFT_NLOS_PD_DB) return 1;
  return 0;
}

float constrainSuspiciousPositiveJump(float measurement, int anchor_idx, uint8_t los_state, unsigned long now_ms) {
  if (measurement <= 0.0f) return 0.0f;
  unsigned long last_ts = anchor_last_measurement_ts[anchor_idx];
  anchor_last_measurement_ts[anchor_idx] = now_ms;

  float previous_filtered = kalman_dist[anchor_idx][0];
  if (last_ts == 0 || previous_filtered <= 0.001f) return measurement;

  unsigned long elapsed_ms = now_ms - last_ts;
  if (elapsed_ms > RANGE_FILTER_STALE_MS) return measurement;

  float allowed_growth = BASE_RANGE_JUMP_M + (MAX_TAG_SPEED_MPS * (elapsed_ms / 1000.0f));
  if (los_state == 1) allowed_growth *= 0.75f;
  if (los_state == 2) allowed_growth *= 0.50f;

  float max_plausible_distance = previous_filtered + allowed_growth;
  if (measurement > max_plausible_distance) {
    measurement = max_plausible_distance;
  }

  return measurement;
}

float kalmanFilterDistance(float measurement, int anchor_id) {
  kalman_dist[anchor_id][1] = kalman_dist[anchor_id][1] + kalman_dist_q;
  float k = kalman_dist[anchor_id][1] / (kalman_dist[anchor_id][1] + kalman_dist_r);
  kalman_dist[anchor_id][0] = kalman_dist[anchor_id][0] + k * (measurement - kalman_dist[anchor_id][0]);
  kalman_dist[anchor_id][1] = (1 - k) * kalman_dist[anchor_id][1];
  return kalman_dist[anchor_id][0];
}

// Median Filter Function
float calculateMedian(float new_val, int anchor_idx) {
    if (!median_init[anchor_idx]) {
        for(int i=0; i<MEDIAN_WINDOW_SIZE; i++) median_buffer[anchor_idx][i] = new_val;
        median_init[anchor_idx] = true;
    }

    median_buffer[anchor_idx][median_idx[anchor_idx]] = new_val;
    median_idx[anchor_idx] = (median_idx[anchor_idx] + 1) % MEDIAN_WINDOW_SIZE;

    float sorted[MEDIAN_WINDOW_SIZE];
    for (int i = 0; i < MEDIAN_WINDOW_SIZE; i++) {
        sorted[i] = median_buffer[anchor_idx][i];
    }

    // Bubble Sort
    for (int i = 0; i < MEDIAN_WINDOW_SIZE - 1; i++) {
        for (int j = 0; j < MEDIAN_WINDOW_SIZE - i - 1; j++) {
            if (sorted[j] > sorted[j + 1]) {
                float temp = sorted[j];
                sorted[j] = sorted[j + 1];
                sorted[j + 1] = temp;
            }
        }
    }

    return sorted[MEDIAN_WINDOW_SIZE / 2];
}

// ===== TASKS =====

// CORE 1: UWB Physics Task
void TaskUWB(void *pvParameters) {
    Serial.println("[Core 1] UWB Task Started");
    float local_anchor_distance[NUM_ANCHORS] = {0};
    float local_anchor_raw_distance[NUM_ANCHORS] = {0};
    float local_pot_sig[NUM_ANCHORS] = {0};
    float local_anchor_pd[NUM_ANCHORS] = {0};
    uint8_t local_anchor_los[NUM_ANCHORS] = {0};
    bool local_anchor_responded[NUM_ANCHORS] = {false};
    
    int curr_stage = 0;
    int t_roundA = 0, t_replyA = 0;
    long long rx = 0, tx = 0;
    int clock_offset = 0;
    int ranging_time = 0;
    bool waitingForResponse = false;
    unsigned long timeoutStart = 0;
    const unsigned long RESPONSE_TIMEOUT = 10;
    int rx_status;
    int fin_de_com = 0;
    unsigned long lastUpdate = millis();
    unsigned long lastActivityTime = millis();
    bool lowPowerMode = false;
    unsigned long updateInterval = 12;

    for(;;) {
        unsigned long currentMillis = millis();

        if (!lowPowerMode && (currentMillis - lastActivityTime >= 300000)) {
            lowPowerMode = true;
            updateInterval = 1000;
        }

        if (currentMillis - lastUpdate >= updateInterval) {
            lastUpdate = currentMillis;
            unsigned long time_in_cycle = currentMillis % TDMA_CYCLE_MS;
            unsigned long assigned_slot_start = (TAG_ID - 1) * TDMA_SLOT_DURATION_MS;
            unsigned long assigned_slot_end = assigned_slot_start + TDMA_SLOT_DURATION_MS;
            bool is_my_slot = (time_in_cycle >= assigned_slot_start && time_in_cycle < assigned_slot_end);

            if (is_my_slot && !lowPowerMode) {
                lastActivityTime = currentMillis;

                for(int k=0; k<NUM_ANCHORS; k++) {
                   local_anchor_responded[k] = false;
                }

                for (int ii = 0; ii < NUM_ANCHORS; ii++) {
                    if (!anchor_is_active[ii]) {
                        if (millis() - anchor_inactive_ts[ii] < RETRY_INTERVAL) {
                            local_anchor_distance[ii] = 0;
                            local_anchor_raw_distance[ii] = 0;
                            local_pot_sig[ii] = -120.0f;
                            local_anchor_pd[ii] = 0.0f;
                            local_anchor_los[ii] = 0;
                            continue;
                        }
                    }

                    DW3000.setDestinationID(ID_PONG[ii]);
                    fin_de_com = 0;
                    curr_stage = 0;
                    waitingForResponse = false;

                    while (fin_de_com == 0) {
                        if (waitingForResponse && ((millis() - timeoutStart) >= RESPONSE_TIMEOUT)) {
                            anchor_fail_count[ii]++;
                            if (anchor_fail_count[ii] >= MAX_FAILURES) {
                                anchor_is_active[ii] = false;
                                anchor_inactive_ts[ii] = millis();
                                anchor_fail_count[ii] = 0;
                            }
                            DW3000.clearSystemStatus();
                            DW3000.configureAsTX(); 
                            
                            local_anchor_distance[ii] = 0;
                            local_anchor_raw_distance[ii] = 0; local_pot_sig[ii] = -120.0f; local_anchor_pd[ii] = 0.0f; local_anchor_los[ii] = 0;
                            fin_de_com = 1; break;
                        }

                        switch (curr_stage) {
                            case 0: 
                                DW3000.ds_sendFrame(1);
                                tx = DW3000.readTXTimestamp();
                                curr_stage = 1; timeoutStart = millis(); waitingForResponse = true;
                                break;
                            case 1: 
                                if ((rx_status = DW3000.receivedFrameSucc())) {
                                    DW3000.clearSystemStatus();
                                    if ((rx_status == 1) && (DW3000.getDestinationID() == ID_PONG[ii]) && !DW3000.ds_isErrorFrame()) {
                                        curr_stage = 2;
                                        waitingForResponse = false;
                                    } else {
                                        anchor_fail_count[ii]++;
                                        if (anchor_fail_count[ii] >= MAX_FAILURES) { anchor_is_active[ii] = false; anchor_inactive_ts[ii] = millis(); anchor_fail_count[ii] = 0;
                                        }
                                        DW3000.clearSystemStatus();
                                        DW3000.configureAsTX();
                                        local_anchor_distance[ii] = 0; local_anchor_raw_distance[ii] = 0; local_pot_sig[ii] = -120.0f; local_anchor_pd[ii] = 0.0f; local_anchor_los[ii] = 0; fin_de_com = 1;
                                    }
                                }
                                break;
                            case 2: 
                                rx = DW3000.readRXTimestamp();
                                DW3000.ds_sendFrame(3);
                                t_roundA = rx - tx; tx = DW3000.readTXTimestamp(); t_replyA = tx - rx;
                                curr_stage = 3; timeoutStart = millis();
                                waitingForResponse = true;
                                break;
                            case 3: 
                                if ((rx_status = DW3000.receivedFrameSucc())) {
                                    DW3000.clearSystemStatus();
                                    if (rx_status == 1 && !DW3000.ds_isErrorFrame()) {
                                        clock_offset = DW3000.getRawClockOffset();
                                        curr_stage = 4; waitingForResponse = false;
                                    } else {
                                        anchor_fail_count[ii]++;
                                        if (anchor_fail_count[ii] >= MAX_FAILURES) { anchor_is_active[ii] = false; anchor_inactive_ts[ii] = millis(); anchor_fail_count[ii] = 0;
                                        }
                                        DW3000.clearSystemStatus();
                                        DW3000.configureAsTX();
                                        local_anchor_distance[ii] = 0; local_anchor_raw_distance[ii] = 0; local_pot_sig[ii] = -120.0f; local_anchor_pd[ii] = 0.0f; local_anchor_los[ii] = 0; fin_de_com = 1;
                                    }
                                }
                                break;
                            case 4: 
                                ranging_time = DW3000.ds_processRTInfo(t_roundA, t_replyA, DW3000.read(0x12, 0x04), DW3000.read(0x12, 0x08), clock_offset);
                                float distance_meters = DW3000.convertToCM(ranging_time) / 100.0;
                                local_pot_sig[ii] = DW3000.getSignalStrength();
                                local_anchor_pd[ii] = DW3000.getPowerDifference();
                                local_anchor_los[ii] = classifyLOSState(local_anchor_pd[ii]);
                                anchor_is_active[ii] = true;
                                anchor_fail_count[ii] = 0;
                                local_anchor_raw_distance[ii] = (distance_meters > 0) ? distance_meters : 0.0f;
                                if (distance_meters > 0) {
                                    local_anchor_responded[ii] = true;
                                    float median_dist = calculateMedian(distance_meters, ii);
                                    float plausibility_limited_dist = constrainSuspiciousPositiveJump(median_dist, ii, local_anchor_los[ii], millis());
                                    local_anchor_distance[ii] = kalmanFilterDistance(plausibility_limited_dist, ii);
                                } else {
                                    local_anchor_responded[ii] = false;
                                    local_anchor_distance[ii] = 0;
                                }
                                fin_de_com = 1;
                                break;
                        }
                    }
                } 
                int responding_anchors = 0;
                for(int k=0; k<NUM_ANCHORS; k++) {
                    if(local_anchor_responded[k]) responding_anchors++;
                }

                TagDataPacket packet;
                packet.anchors_visible = responding_anchors;
                packet.timestamp = millis();
                for(int i=0; i<NUM_ANCHORS; i++) {
                    packet.anchor_dist[i] = local_anchor_distance[i];
                    packet.anchor_raw_dist[i] = local_anchor_raw_distance[i];
                    packet.anchor_rssi[i] = local_pot_sig[i];
                    packet.anchor_pd[i] = local_anchor_pd[i];
                    packet.anchor_resp[i] = local_anchor_responded[i];
                    packet.anchor_los[i] = local_anchor_los[i];
                }
                
                xQueueOverwrite(uwbQueue, &packet);
            }
        }
        vTaskDelay(1);
    }
}

// CORE 0: Serial Output Task
void TaskSerial(void *pvParameters) {
    Serial.println("[Core 0] Serial Task Started");
    TagDataPacket packet;

    for(;;) {
        if (xQueueReceive(uwbQueue, &packet, pdMS_TO_TICKS(10)) == pdTRUE) {
            StaticJsonDocument<SERIAL_JSON_CAPACITY> doc;
            doc["tag_id"] = TAG_ID;
            doc["timestamp_ms"] = packet.timestamp;
            doc["anchors_visible"] = packet.anchors_visible;

            JsonObject anchorDistances = doc.createNestedObject("anchor_distances");
            for (int i = 0; i < NUM_ANCHORS; i++) {
                if (packet.anchor_resp[i]) {
                    anchorDistances[String(ID_PONG[i])] = packet.anchor_dist[i];
                }
            }

            serializeJson(doc, Serial);
            Serial.println();
        }

        vTaskDelay(1); 
    }
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);

    for(int i = 0; i < MAX_ANCHORS; i++) {
      anchor_is_active[i] = true;
    }
  
  uwbQueue = xQueueCreate(1, sizeof(TagDataPacket)); 

  SPI.begin();
  DW3000.begin();
  SPI.setFrequency(8000000);
  DW3000.hardReset(); delay(200);
  DW3000.softReset(); delay(200);

  DW3000.setChannel(CHANNEL_5);
  DW3000.setPreambleCode(9);
  
  DW3000.init();
  SPI.setFrequency(20000000);
  DW3000.setupGPIO();
  DW3000.configureAsTX();
  DW3000.clearSystemStatus();

  // Mantenemos la creación de tareas igual que en tu código original [cite: 95, 96]
  xTaskCreatePinnedToCore(TaskUWB, "UWB_Task", 10000, NULL, 2, NULL, 1);
  xTaskCreatePinnedToCore(TaskSerial, "Serial_Task", 10000, NULL, 1, NULL, 0);
}

void loop() {
  vTaskDelete(NULL);
}