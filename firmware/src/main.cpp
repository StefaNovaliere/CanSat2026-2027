// Esqueleto del firmware. Faltan los drivers (barómetro, IMU, ADS1115,
// TSL2561, GPS, SD y radio), por eso hay TODO en todos lados.
//
// Idea de tareas (FreeRTOS):
//   núcleo 1: sensorTask  -> lee sensores a frecuencia completa y llena un buffer en RAM
//   núcleo 0: loggerTask  -> vacía el buffer a la SD en bloques, flush cada 1 s
//   núcleo 0: radioTask   -> manda un paquete resumen a 1-5 Hz
#include <Arduino.h>

#include "telemetry.h"

namespace {

constexpr uint16_t TEAM_ID = 0;  // TODO: número de equipo que asigne CONAE
constexpr uint32_t RADIO_PERIOD_MS = 200;  // 5 Hz, a confirmar con las bases
constexpr uint32_t FLUSH_PERIOD_MS = 1000;

telemetry::Packet latest{};  // último estado conocido, protegido por el mutex
SemaphoreHandle_t latestMutex;
uint32_t packetCount = 0;

void sensorTask(void*) {
  for (;;) {
    // TODO: leer sensores, escribir muestra completa en el buffer circular
    // TODO: actualizar máquina de estados (rampa, ascenso, apogeo, descenso, aterrizado)
    if (xSemaphoreTake(latestMutex, portMAX_DELAY) == pdTRUE) {
      latest.time_ms = millis();
      xSemaphoreGive(latestMutex);
    }
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}

void loggerTask(void*) {
  uint32_t lastFlush = millis();
  for (;;) {
    // TODO: sacar bloques del buffer circular y escribirlos en la SD
    if (millis() - lastFlush >= FLUSH_PERIOD_MS) {
      // TODO: file.flush()
      lastFlush = millis();
    }
    vTaskDelay(pdMS_TO_TICKS(20));
  }
}

void radioTask(void*) {
  uint8_t frame[telemetry::FRAME_LEN];
  for (;;) {
    telemetry::Packet p;
    if (xSemaphoreTake(latestMutex, portMAX_DELAY) == pdTRUE) {
      p = latest;
      xSemaphoreGive(latestMutex);
    }
    p.team_id = TEAM_ID;
    p.packet_count = packetCount++;
    size_t n = telemetry::encodeBinary(p, frame);
    // TODO: mandar por la radio. Mientras tanto sale por serie para probar
    // la estación terrena con el cable.
    Serial.write(frame, n);
    vTaskDelay(pdMS_TO_TICKS(RADIO_PERIOD_MS));
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);
  latestMutex = xSemaphoreCreateMutex();
  xTaskCreatePinnedToCore(sensorTask, "sensores", 4096, nullptr, 3, nullptr, 1);
  xTaskCreatePinnedToCore(loggerTask, "logger", 4096, nullptr, 2, nullptr, 0);
  xTaskCreatePinnedToCore(radioTask, "radio", 4096, nullptr, 1, nullptr, 0);
}

void loop() { vTaskDelay(portMAX_DELAY); }
