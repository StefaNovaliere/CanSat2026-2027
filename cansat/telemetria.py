"""Paquete de telemetría: estructura, formato texto y formato binario.

Es un borrador hasta que CONAE diga si hay un formato obligatorio.
La especificación está en docs/telemetria.md y tiene que coincidir con
firmware/src/telemetry.cpp (hay un test que lo verifica).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, fields
from enum import IntEnum

SYNC = b"\xCA\x57"
VERSION = 1

# Orden y tipos del payload binario (little-endian, sin padding).
PAYLOAD_FMT = "<HIIBffffHiiHHB"
PAYLOAD_LEN = struct.calcsize(PAYLOAD_FMT)  # 42 bytes
FRAME_LEN = len(SYNC) + 2 + PAYLOAD_LEN + 2  # sync + versión + largo + payload + CRC

TEXT_PREFIX = "CTRL"


class Estado(IntEnum):
    ARRANQUE = 0
    RAMPA = 1
    ASCENSO = 2
    APOGEO = 3
    DESCENSO = 4
    ATERRIZADO = 5


class Flags:
    GPS_FIX = 1 << 0
    SD_OK = 1 << 1
    PARACAIDAS = 1 << 2
    BALIZA = 1 << 3


@dataclass
class Paquete:
    team_id: int
    time_ms: int
    packet_count: int
    state: int
    altitude_m: float
    pressure_pa: float
    temp_int_c: float
    temp_ext_c: float
    battery_mv: int
    lat_e7: int  # latitud en grados * 1e7
    lon_e7: int  # longitud en grados * 1e7
    light_up: int
    light_down: int
    flags: int = 0

    @property
    def lat(self) -> float:
        return self.lat_e7 / 1e7

    @property
    def lon(self) -> float:
        return self.lon_e7 / 1e7


CAMPOS = [f.name for f in fields(Paquete)]


class ErrorPaquete(ValueError):
    pass


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: polinomio 0x1021, valor inicial 0xFFFF."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


# --- binario ---------------------------------------------------------------

def a_binario(p: Paquete) -> bytes:
    payload = struct.pack(
        PAYLOAD_FMT,
        p.team_id, p.time_ms, p.packet_count, p.state,
        p.altitude_m, p.pressure_pa, p.temp_int_c, p.temp_ext_c,
        p.battery_mv, p.lat_e7, p.lon_e7, p.light_up, p.light_down, p.flags,
    )
    cuerpo = bytes([VERSION, PAYLOAD_LEN]) + payload
    return SYNC + cuerpo + struct.pack("<H", crc16(cuerpo))


def desde_binario(frame: bytes) -> Paquete:
    if len(frame) != FRAME_LEN or frame[:2] != SYNC:
        raise ErrorPaquete("largo o sync incorrecto")
    cuerpo = frame[2:-2]
    (crc_rx,) = struct.unpack("<H", frame[-2:])
    if crc16(cuerpo) != crc_rx:
        raise ErrorPaquete("CRC incorrecto")
    if cuerpo[0] != VERSION or cuerpo[1] != PAYLOAD_LEN:
        raise ErrorPaquete(f"versión {cuerpo[0]} o largo {cuerpo[1]} no soportados")
    return Paquete(*struct.unpack(PAYLOAD_FMT, cuerpo[2:]))


# --- texto -----------------------------------------------------------------
# $CTRL,campo1,campo2,...*CRC\r\n  (CRC en hex sobre lo que está entre $ y *)

def _grados_e7(v: int) -> str:
    signo = "-" if v < 0 else ""
    a = abs(v)
    return f"{signo}{a // 10_000_000}.{a % 10_000_000:07d}"


def _desde_grados(s: str) -> int:
    negativo = s.startswith("-")
    entero, _, dec = s.lstrip("-").partition(".")
    v = int(entero) * 10_000_000 + int((dec + "0000000")[:7])
    return -v if negativo else v


def a_texto(p: Paquete) -> str:
    valores = [
        TEXT_PREFIX, str(p.team_id), str(p.time_ms), str(p.packet_count), str(p.state),
        f"{p.altitude_m:.2f}", f"{p.pressure_pa:.1f}",
        f"{p.temp_int_c:.3f}", f"{p.temp_ext_c:.3f}",
        str(p.battery_mv), _grados_e7(p.lat_e7), _grados_e7(p.lon_e7),
        str(p.light_up), str(p.light_down), str(p.flags),
    ]
    cuerpo = ",".join(valores)
    return f"${cuerpo}*{crc16(cuerpo.encode('ascii')):04X}\r\n"


def desde_texto(linea: str) -> Paquete:
    linea = linea.strip()
    if not linea.startswith("$") or "*" not in linea:
        raise ErrorPaquete("no es una línea de telemetría")
    cuerpo, _, crc_txt = linea[1:].rpartition("*")
    try:
        crc_rx = int(crc_txt, 16)
    except ValueError as e:
        raise ErrorPaquete("CRC ilegible") from e
    if crc16(cuerpo.encode("ascii")) != crc_rx:
        raise ErrorPaquete("CRC incorrecto")
    partes = cuerpo.split(",")
    if partes[0] != TEXT_PREFIX or len(partes) != len(CAMPOS) + 1:
        raise ErrorPaquete("prefijo o cantidad de campos incorrecta")
    v = partes[1:]
    return Paquete(
        team_id=int(v[0]), time_ms=int(v[1]), packet_count=int(v[2]), state=int(v[3]),
        altitude_m=float(v[4]), pressure_pa=float(v[5]),
        temp_int_c=float(v[6]), temp_ext_c=float(v[7]),
        battery_mv=int(v[8]), lat_e7=_desde_grados(v[9]), lon_e7=_desde_grados(v[10]),
        light_up=int(v[11]), light_down=int(v[12]), flags=int(v[13]),
    )
