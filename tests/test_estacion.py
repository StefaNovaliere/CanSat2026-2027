import csv

from cansat import telemetria as t
from cansat.estacion import __main__ as estacion
from cansat.estacion.receptor import Receptor


def paquete(n: int) -> t.Paquete:
    return t.Paquete(team_id=1, time_ms=n * 200, packet_count=n, state=t.Estado.DESCENSO,
                     altitude_m=400 - n, pressure_pa=95000 + n, temp_int_c=10.0, temp_ext_c=8.0,
                     battery_mv=4000, lat_e7=0, lon_e7=0, light_up=0, light_down=0)


def test_binario_con_basura_y_paquete_perdido():
    datos = (b"\x00\x13basura" + t.a_binario(paquete(0)) + t.a_binario(paquete(1))
             + b"\xCA" + t.a_binario(paquete(3)))  # falta el 2 y hay un sync suelto
    r = Receptor()
    recibidos = r.alimentar(datos)
    assert [p.packet_count for p in recibidos] == [0, 1, 3]
    assert r.perdidos == 1
    assert r.descartados > 0


def test_paquete_partido_en_dos_lecturas():
    frame = t.a_binario(paquete(7))
    r = Receptor()
    assert r.alimentar(frame[:20]) == []
    (p,) = r.alimentar(frame[20:])
    assert p == paquete(7)


def test_frame_corrupto_no_tapa_al_siguiente():
    malo = bytearray(t.a_binario(paquete(0)))
    malo[15] ^= 0xFF
    r = Receptor()
    recibidos = r.alimentar(bytes(malo) + t.a_binario(paquete(1)))
    assert [p.packet_count for p in recibidos] == [1]
    assert r.errores >= 1


def test_texto_y_binario_mezclados():
    datos = t.a_texto(paquete(0)).encode() + t.a_binario(paquete(1)) + t.a_texto(paquete(2)).encode()
    recibidos = Receptor().alimentar(datos)
    assert [p.packet_count for p in recibidos] == [0, 1, 2]


def test_cli_desde_archivo(tmp_path):
    archivo = tmp_path / "vuelo.bin"
    archivo.write_bytes(b"".join(t.a_binario(paquete(n)) for n in range(10)))
    salida = tmp_path / "vuelo.csv"
    estacion.main(["--archivo", str(archivo), "--salida", str(salida), "--silencioso"])
    with open(salida, newline="") as f:
        filas = list(csv.DictReader(f))
    assert len(filas) == 10
    assert filas[3]["packet_count"] == "3"
