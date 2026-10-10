#include "telemetry.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace telemetry {

uint16_t crc16(const uint8_t* data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (int b = 0; b < 8; b++) {
      crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021)
                           : static_cast<uint16_t>(crc << 1);
    }
  }
  return crc;
}

namespace {

// Escritura byte a byte en little-endian, así no dependemos del padding
// del struct ni de la arquitectura.
struct Writer {
  uint8_t* p;
  void u8(uint8_t v) { *p++ = v; }
  void u16(uint16_t v) {
    u8(v & 0xFF);
    u8(v >> 8);
  }
  void u32(uint32_t v) {
    u16(v & 0xFFFF);
    u16(v >> 16);
  }
  void i32(int32_t v) { u32(static_cast<uint32_t>(v)); }
  void f32(float v) {
    uint32_t bits;
    memcpy(&bits, &v, sizeof(bits));
    u32(bits);
  }
};

// Grados * 1e7 a texto sin pasar por float (no perdemos precisión).
int formatE7(char* out, size_t size, int32_t v) {
  int64_t a = v;
  const char* sign = "";
  if (a < 0) {
    sign = "-";
    a = -a;
  }
  return snprintf(out, size, "%s%ld.%07ld", sign, static_cast<long>(a / 10000000),
                  static_cast<long>(a % 10000000));
}

}  // namespace

size_t encodeBinary(const Packet& p, uint8_t* out) {
  Writer w{out};
  w.u8(SYNC0);
  w.u8(SYNC1);
  uint8_t* body = w.p;
  w.u8(VERSION);
  w.u8(static_cast<uint8_t>(PAYLOAD_LEN));
  w.u16(p.team_id);
  w.u32(p.time_ms);
  w.u32(p.packet_count);
  w.u8(p.state);
  w.f32(p.altitude_m);
  w.f32(p.pressure_pa);
  w.f32(p.temp_int_c);
  w.f32(p.temp_ext_c);
  w.u16(p.battery_mv);
  w.i32(p.lat_e7);
  w.i32(p.lon_e7);
  w.u16(p.light_up);
  w.u16(p.light_down);
  w.u8(p.flags);
  w.u16(crc16(body, static_cast<size_t>(w.p - body)));
  return static_cast<size_t>(w.p - out);
}

size_t encodeText(const Packet& p, char* out, size_t out_size) {
  char lat[16], lon[16];
  formatE7(lat, sizeof(lat), p.lat_e7);
  formatE7(lon, sizeof(lon), p.lon_e7);

  char body[TEXT_MAX_LEN];
  int n = snprintf(body, sizeof(body), "CTRL,%u,%lu,%lu,%u,%.2f,%.1f,%.3f,%.3f,%u,%s,%s,%u,%u,%u",
                   p.team_id, static_cast<unsigned long>(p.time_ms),
                   static_cast<unsigned long>(p.packet_count), p.state, p.altitude_m,
                   p.pressure_pa, p.temp_int_c, p.temp_ext_c, p.battery_mv, lat, lon,
                   p.light_up, p.light_down, p.flags);
  if (n < 0 || static_cast<size_t>(n) >= sizeof(body)) return 0;

  uint16_t crc = crc16(reinterpret_cast<const uint8_t*>(body), static_cast<size_t>(n));
  int m = snprintf(out, out_size, "$%s*%04X\r\n", body, crc);
  if (m < 0 || static_cast<size_t>(m) >= out_size) return 0;
  return static_cast<size_t>(m);
}

}  // namespace telemetry
