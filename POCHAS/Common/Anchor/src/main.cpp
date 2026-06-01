#include <Arduino.h>
#include "DW3000.h"



void initializeDW3000();
void manageActivity();
void handleStage0_AwaitRanging();
void handleStage1_SendResponse();
void handleStage2_AwaitSecondResponse();
void handleStage3_SendInfo();
void handleStage4_Cleanup();
void handleUnknownStage();
void resetToStage0();
void printPerformanceStats();


// ===== CONFIGURATION OF ANCHOR =====
static int ID_PONG = 8; // Unique ID of the anchor (Cambiar esta linea en las 6 anclas)

// ====== SERIAL COMMUNICATION ======
const unsigned long SERIAL_BAUD_RATE = 921600;

// ===== COMMUNICATION VARIABLES =====
static int frame_buffer = 0;
static int rx_status;
static int tx_status;

// States of the double-sided ranging protocol
static int curr_stage = 0;
static int t_roundB = 0;
static int t_replyB = 0;
static long long rx = 0;
static long long tx = 0;

// ===== IMPROVED ACTIVITY MANAGEMENT =====
unsigned long lastSuccessfulActivityTime = 0;
unsigned long lastDebugOutput = 0;
const unsigned long ANCHOR_RESET_TIMEOUT_MS = 30000; // 30 seconds
const unsigned long DEBUG_INTERVAL_MS = 10000; // Debug every 10 seconds

// ===== PERFORMANCE STATISTICS =====
struct AnchorStats {
  unsigned long total_requests = 0;
  unsigned long successful_responses = 0;
  unsigned long error_frames = 0;
  unsigned long timeouts = 0;
  unsigned long uptime_start = 0;
} stats;

// ===== OPTIMIZED CONFIGURATIONS =====
const unsigned long RX_TIMEOUT_MS = 20; // Optimized for 20Hz Tag (was 100ms)
const unsigned long RESPONSE_DELAY_US = 50; // Minimum delay between responses

void setup() {
  Serial.begin(SERIAL_BAUD_RATE); // Standard speed for stability
  
  // Initialize statistics
  stats.uptime_start = millis();
  
  initializeDW3000();
  
  Serial.println("> ANCHOR 1 OPTIMIZED - Double-sided PONG v2.0 <");
  Serial.println("[INFO] Setup completed. Ready for ranging.");
  
  lastSuccessfulActivityTime = millis();
  lastDebugOutput = millis();
}

void initializeDW3000() {
  DW3000.begin();
  DW3000.hardReset();
  delay(10); // Reduced for faster startup (was 100ms)
  
  // Verification with retries
  int retries = 0;
  while (!DW3000.checkForIDLE() && retries < 5) {
    Serial.printf("[WARNING] IDLE check failed, retry %d/5\n", ++retries);
    delay(10); // Reduced retry delay
  }
  
  if (retries >= 5) {
    Serial.println("[ERROR] DW3000 initialization failed! Restarting...");
    ESP.restart();
  }
  
  DW3000.softReset();
  delay(10); // Reduced (was 100ms)
  
  if (!DW3000.checkForIDLE()) {
    Serial.println("[ERROR] DW3000 soft reset failed! Restarting...");
    ESP.restart();
  }
  
  // FORCE CHANNEL 5 CONFIGURATION (Match TAG)
  DW3000.setChannel(CHANNEL_5);
  DW3000.setPreambleCode(9);
  
  DW3000.init();
  DW3000.setupGPIO();
  DW3000.configureAsTX();
  DW3000.clearSystemStatus();
  DW3000.standardRX();
  
  Serial.println("[INFO] DW3000 initialized correctly");
}

void loop() {
  // Improved activity management and auto-restart
  manageActivity();
  
  // Improved periodic debug
  if (millis() - lastDebugOutput > DEBUG_INTERVAL_MS) {
    printPerformanceStats();
    lastDebugOutput = millis();
  }
  
  // Main state machine
  switch (curr_stage) {
    case 0:
      handleStage0_AwaitRanging();
      break;
      
    case 1:
      handleStage1_SendResponse();
      break;
      
    case 2:
      handleStage2_AwaitSecondResponse();
      break;
      
    case 3:
      handleStage3_SendInfo();
      break;
      
    case 4:
      handleStage4_Cleanup();
      break;
      
    default:
      handleUnknownStage();
      break;
  }
}

void manageActivity() {
  unsigned long currentTime = millis();
  
  // Auto-restart by inactivity
  if (currentTime - lastSuccessfulActivityTime > ANCHOR_RESET_TIMEOUT_MS) {
    Serial.println("[AUTO-RESET] Inactivity detected. Restarting anchor...");
    printPerformanceStats();
    delay(100);
    ESP.restart();
  }
}

void handleStage0_AwaitRanging() {
  t_roundB = 0;
  t_replyB = 0;
  
  if (rx_status = DW3000.receivedFrameSucc()) {
    DW3000.clearSystemStatus();
    stats.total_requests++;
    
    if (rx_status == 1) {
      if (DW3000.ds_isErrorFrame()) {
        Serial.println("[WARNING] Error frame detected, returning to stage 0");
        stats.error_frames++;
        resetToStage0();
        return;
      }
      
      if (DW3000.getDestinationID() != ID_PONG) {
        // Not
        DW3000.standardRX();
        return;
      }
      
      if (DW3000.ds_getStage() != 1) {
        Serial.printf("[WARNING] Incorrect stage received: %d\n", DW3000.ds_getStage());
        DW3000.ds_sendErrorFrame();
        stats.error_frames++;
        resetToStage0();
        return;
      }
      
      // Everything is correct, advance to stage 1
      curr_stage = 1;
      
    } else {
      Serial.println("[ERROR] Error in stage 0");
      stats.timeouts++;
      DW3000.clearSystemStatus();
      resetToStage0();
    }
  }
}

void handleStage1_SendResponse() {
  DW3000.setDestinationID(ID_PONG);
  DW3000.ds_sendFrame(2);
  
  rx = DW3000.readRXTimestamp();
  tx = DW3000.readTXTimestamp();
  t_replyB = tx - rx;
  
  curr_stage = 2;
}

void handleStage2_AwaitSecondResponse() {
  if (rx_status = DW3000.receivedFrameSucc()) {
    DW3000.clearSystemStatus();
    
    if (rx_status == 1) {
      if (DW3000.ds_isErrorFrame()) {
        Serial.println("[WARNING] Error frame in stage 2");
        stats.error_frames++;
        resetToStage0();
        return;
      }
      
      if (DW3000.getDestinationID() != ID_PONG) {
        Serial.println("[DEBUG] Destination different in stage 2, cleaning");
        curr_stage = 4; // Clean and return to stage 0
        return;
      }
      
      if (DW3000.ds_getStage() != 3) {
        Serial.printf("[WARNING] Incorrect stage in stage 2: %d\n", DW3000.ds_getStage());
        DW3000.ds_sendErrorFrame();
        stats.error_frames++;
        resetToStage0();
        return;
      }
      
      curr_stage = 3;
      
    } else {
      Serial.println("[ERROR] Error in stage 2");
      stats.timeouts++;
      resetToStage0();
    }
  }
}

void handleStage3_SendInfo() {
  rx = DW3000.readRXTimestamp();
  t_roundB = rx - tx;
  
  // Send timing information
  DW3000.ds_sendRTInfo(t_roundB, t_replyB);
  
  // Transaction completed successfully
  stats.successful_responses++;
  lastSuccessfulActivityTime = millis();
  
  resetToStage0();
}

void handleStage4_Cleanup() {
  // Quick cleanup and return to stage 0
  resetToStage0();
}

void handleUnknownStage() {
  Serial.printf("[ERROR] Unknown stage (%d), restarting\n", curr_stage);
  resetToStage0();
}

void resetToStage0() {
  curr_stage = 0;
  DW3000.standardRX();
  
  // Small delay to stabilize
  delayMicroseconds(RESPONSE_DELAY_US);
}

void printPerformanceStats() {
  unsigned long uptime = millis() - stats.uptime_start;
  float success_rate = stats.total_requests > 0 ? 
    (float)stats.successful_responses / stats.total_requests * 100.0 : 0.0;
  
  Serial.println("\n=== ANCHOR 1 STATISTICS ===");
  Serial.printf("Success rate: %.1f%%\n", success_rate);
  Serial.printf("Frames with error: %lu\n", stats.error_frames);
  Serial.printf("Timeouts: %lu\n", stats.timeouts);
  Serial.printf("Last activity: %lu ms ago\n", millis() - lastSuccessfulActivityTime);
  Serial.println("================================\n");
} 