// Paquete de telemetría. Tiene que coincidir con cansat/telemetria.py y
// docs/telemetria.md (hay un test en Python que compila esto y lo compara).
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace telemetry {

constexpr uint8_t SYNC0 = 0xCA;
constexpr uint8_t SYNC1 = 0x57;
constexpr uint8_t VERSION = 1;
constexpr size_t PAYLOAD_LEN = 42;
constexpr size_t FRAME_LEN = 2 + 2 + PAYLOAD_LEN + 2;
constexpr size_t TEXT_MAX_LEN = 160;

enum class State : uint8_t {
  Arranque = 0,
  Rampa = 1,
  Ascenso = 2,
  Apogeo = 3,
  Descenso = 4,
  Aterrizado = 5,
};

enum Flags : uint8_t {
  FLAG_GPS_FIX = 1 << 0,
  FLAG_SD_OK = 1 << 1,
  FLAG_PARACAIDAS = 1 << 2,
  FLAG_BALIZA = 1 << 3,
};

struct Packet {
  uint16_t team_id;
  uint32_t time_ms;
  uint32_t packet_count;
  uint8_t state;
  float altitude_m;
  float pressure_pa;
  float temp_int_c;
  float temp_ext_c;
  uint16_t battery_mv;
  int32_t lat_e7;  // grados * 1e7
  int32_t lon_e7;  // grados * 1e7
  uint16_t light_up;
  uint16_t light_down;
  uint8_t flags;
};

// CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF).
uint16_t crc16(const uint8_t* data, size_t len);

// Escribe FRAME_LEN bytes en out. Devuelve la cantidad escrita.
size_t encodeBinary(const Packet& p, uint8_t* out);

// Escribe "$CTRL,...*CRC\r\n" terminado en '\0'. Devuelve el largo sin el '\0',
// o 0 si no entra en el buffer.
size_t encodeText(const Packet& p, char* out, size_t out_size);

}  // namespace telemetry
