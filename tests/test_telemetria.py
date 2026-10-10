import shutil
import subprocess
from pathlib import Path

import pytest

from cansat import telemetria as t

RAIZ = Path(__file__).resolve().parents[1]


def paquete_ejemplo() -> t.Paquete:
    # Mismo paquete que firmware/test_host/main.cpp
    return t.Paquete(
        team_id=42, time_ms=123456, packet_count=789, state=t.Estado.DESCENSO,
        altitude_m=312.25, pressure_pa=91234.5, temp_int_c=12.5, temp_ext_c=7.125,
        battery_mv=3987, lat_e7=-314012345, lon_e7=-641234567,
        light_up=1500, light_down=320, flags=t.Flags.GPS_FIX | t.Flags.SD_OK,
    )


def test_crc_valor_de_referencia():
    assert t.crc16(b"123456789") == 0x29B1


def test_binario_ida_y_vuelta():
    p = paquete_ejemplo()
    frame = t.a_binario(p)
    assert len(frame) == t.FRAME_LEN == 48
    assert t.desde_binario(frame) == p


def test_binario_detecta_corrupcion():
    frame = bytearray(t.a_binario(paquete_ejemplo()))
    frame[10] ^= 0x01
    with pytest.raises(t.ErrorPaquete):
        t.desde_binario(bytes(frame))


def test_texto_ida_y_vuelta():
    p = paquete_ejemplo()
    linea = t.a_texto(p)
    assert linea.startswith("$CTRL,42,") and linea.endswith("\r\n")
    assert t.desde_texto(linea) == p


def test_texto_detecta_corrupcion():
    linea = t.a_texto(paquete_ejemplo()).replace("312.25", "312.26")
    with pytest.raises(t.ErrorPaquete):
        t.desde_texto(linea)


@pytest.mark.parametrize("v", [0, 1, -1, 314012345, -314012345, -641234567, 9999999])
def test_grados_sin_perder_precision(v):
    assert t._desde_grados(t._grados_e7(v)) == v


@pytest.mark.skipif(shutil.which("g++") is None, reason="no hay g++")
def test_firmware_y_python_coinciden(tmp_path):
    exe = tmp_path / "telemetry_host"
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Werror",
         "-I", str(RAIZ / "firmware/src"),
         str(RAIZ / "firmware/src/telemetry.cpp"),
         str(RAIZ / "firmware/test_host/main.cpp"),
         "-o", str(exe)],
        check=True,
    )
    # Se lee en bytes para que no se coman el \r del final.
    salida = subprocess.run([str(exe)], check=True, capture_output=True).stdout.decode("ascii")
    hex_frame, linea_texto = salida.split("\n", 1)

    p = paquete_ejemplo()
    assert bytes.fromhex(hex_frame) == t.a_binario(p)
    assert linea_texto == t.a_texto(p)
