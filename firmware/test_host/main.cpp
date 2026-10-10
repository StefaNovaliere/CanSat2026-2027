// Se compila en la PC (no en el ESP32) para comparar el paquete con la
// versión en Python. Lo usa tests/test_telemetria.py.
//   g++ -std=c++17 -I../src ../src/telemetry.cpp main.cpp -o build/telemetry_host
#include <stdio.h>

#include "telemetry.h"

int main() {
  telemetry::Packet p{};
  p.team_id = 42;
  p.time_ms = 123456;
  p.packet_count = 789;
  p.state = static_cast<uint8_t>(telemetry::State::Descenso);
  p.altitude_m = 312.25f;
  p.pressure_pa = 91234.5f;
  p.temp_int_c = 12.5f;
  p.temp_ext_c = 7.125f;
  p.battery_mv = 3987;
  p.lat_e7 = -314012345;
  p.lon_e7 = -641234567;
  p.light_up = 1500;
  p.light_down = 320;
  p.flags = telemetry::FLAG_GPS_FIX | telemetry::FLAG_SD_OK;

  uint8_t frame[telemetry::FRAME_LEN];
  size_t n = telemetry::encodeBinary(p, frame);
  for (size_t i = 0; i < n; i++) printf("%02X", frame[i]);
  printf("\n");

  char text[telemetry::TEXT_MAX_LEN + 16];
  if (telemetry::encodeText(p, text, sizeof(text)) == 0) return 1;
  printf("%s", text);
  return 0;
}
