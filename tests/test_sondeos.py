from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from cansat import sondeos

FIXTURE = Path(__file__).parent / "fixtures" / "sondeos_sinteticos.txt"


def test_lee_dos_sondeos_con_fecha():
    s = sondeos.leer(FIXTURE)
    assert len(s) == 2
    assert s[0].fecha == datetime(2025, 6, 15, 12, tzinfo=timezone.utc)
    assert s[1].fecha == datetime(2025, 6, 16, 0, tzinfo=timezone.utc)
    assert s[0].estacion.startswith("87344")


def test_descarta_niveles_bajo_el_suelo():
    s = sondeos.leer(FIXTURE)[0]
    assert s.alt_suelo_m == 474
    assert s.agl_m[0] == 0
    assert not np.isnan(s.temp_c).any()


def test_detecta_inversion_solo_donde_hay():
    con, sin = sondeos.leer(FIXTURE)
    c = sondeos.analizar_capa(con, 400)
    assert c.hay_inversion()
    assert c.t_suelo == pytest.approx(2.0)
    assert c.t_max > 8.0
    assert not sondeos.analizar_capa(sin, 400).hay_inversion()


def test_formato_sin_encabezado_de_fecha():
    texto = """ESTACIÓN: 87344
-----------------------------------------------------------------------------
   PRES   HGHT   TEMP   DWPT   RELH   MIXR   DRCT   SKNT   THTA   THTE   THTV
    hPa     m      C      C      %    g/kg    deg   knot     K      K      K
-----------------------------------------------------------------------------
  956.0    474    3.2    1.2     87   4.42    180      4  279.9  292.4  280.7
  946.0    562    9.4    1.4     57   4.53    357      2  287.0  299.9  287.8
  925.0    755   11.4   -0.6     43   3.99     15      6  291.0  302.5  291.7
"""
    (s,) = sondeos.parsear_texto(texto)
    assert s.fecha is None
    assert list(s.temp_c) == [3.2, 9.4, 11.4]
    assert s.columnas["SKNT"][1] == 2


def test_cli_genera_csv_y_grafico(tmp_path):
    csv_out = tmp_path / "resumen.csv"
    png_out = tmp_path / "perfiles.png"
    sondeos.main([str(FIXTURE), "--csv", str(csv_out), "--grafico", str(png_out)])
    assert csv_out.read_text().count("\n") == 3
    assert png_out.stat().st_size > 10_000
