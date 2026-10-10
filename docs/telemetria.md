# Paquete de telemetría (borrador v1)

Borrador hasta que CONAE diga si hay formato o frecuencia obligatoria. Si piden algo distinto, se cambia acá, en `cansat/telemetria.py` y en `firmware/src/telemetry.cpp` (el test `tests/test_telemetria.py` compila el C++ y verifica que los dos lados den lo mismo).

Por radio va un resumen a 1-5 Hz. Los datos completos, a frecuencia alta, van a la SD.

## Campos

| Campo | Tipo | Unidad | Comentario |
| --- | --- | --- | --- |
| team_id | uint16 | | número de equipo |
| time_ms | uint32 | ms | desde que arrancó el micro |
| packet_count | uint32 | | sirve para contar paquetes perdidos |
| state | uint8 | | 0 arranque, 1 rampa, 2 ascenso, 3 apogeo, 4 descenso, 5 aterrizado |
| altitude_m | float32 | m | sobre el lugar de lanzamiento, del barómetro |
| pressure_pa | float32 | Pa | |
| temp_int_c | float32 | °C | sensor de adentro de la lata |
| temp_ext_c | float32 | °C | termistor en la cámara de aire |
| battery_mv | uint16 | mV | |
| lat_e7 | int32 | grados × 10⁷ | |
| lon_e7 | int32 | grados × 10⁷ | |
| light_up | uint16 | cuentas | TSL2561 mirando para arriba |
| light_down | uint16 | cuentas | TSL2561 mirando para abajo |
| flags | uint8 | | bit 0 GPS con fix, bit 1 SD ok, bit 2 paracaídas, bit 3 baliza |

## Formato binario (48 bytes)

`CA 57` (sync) · versión (1 byte) · largo del payload (1 byte, 42) · payload · CRC16 (2 bytes).

Todo en little-endian y en el orden de la tabla. El CRC es CRC-16/CCITT-FALSE (polinomio 0x1021, valor inicial 0xFFFF) y se calcula sobre versión, largo y payload.

## Formato texto

```
$CTRL,team_id,time_ms,packet_count,state,altitude_m,pressure_pa,temp_int_c,temp_ext_c,battery_mv,lat,lon,light_up,light_down,flags*CRC
```

Termina en `\r\n`. Latitud y longitud van en grados con 7 decimales. El CRC es el mismo algoritmo, en hex con 4 dígitos, calculado sobre lo que está entre `$` y `*`.
