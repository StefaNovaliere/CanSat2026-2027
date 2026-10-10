import numpy as np
import pytest

from cansat.sim import atmosfera, descenso, mision, radiacion
from cansat.sim.parametros import Vuelo


def test_humedad_y_nubes():
    despejado = atmosfera.estandar()
    assert despejado.base_nubes() is None
    assert despejado.humedad_relativa(0) == pytest.approx(70, abs=5)  # 5 °C de depresión ≈ 70 %
    nublado = atmosfera.estandar(nubes_base_m=300)
    assert nublado.base_nubes() == pytest.approx(300, abs=1)


def test_cielo_despejado_frio_y_nublado_como_la_nube():
    z = np.array([200.0])
    despejado = radiacion.lectura_arriba_k(atmosfera.estandar(), z, np.zeros(1), 45)[0] - 273.15
    nublado_atm = atmosfera.estandar(nubes_base_m=600)
    nublado = radiacion.lectura_arriba_k(nublado_atm, z, np.zeros(1), 45)[0] - 273.15
    assert despejado < -10                       # cielo despejado mucho más frío que el aire
    assert nublado == pytest.approx(nublado_atm.temperatura(600), abs=0.1)


def test_inclinar_el_sensor_lo_calienta():
    atm = atmosfera.estandar()
    derecho, inclinado = radiacion.lectura_arriba_k(atm, np.array([200.0, 200.0]), np.radians([0, 25]), 45)
    assert inclinado > derecho + 1


def test_debajo_de_una_inversion_el_cielo_se_ve_mas_calido():
    atm = atmosfera.con_inversion(salto_c=8, espesor_inversion_m=100)
    abajo, arriba = radiacion.lectura_arriba_k(atm, np.array([10.0, 300.0]), np.zeros(2), 45)
    assert abajo > arriba


def test_la_mision_distingue_despejado_de_nublado():
    rng = np.random.default_rng(2)
    resultados = {}
    for atm in (atmosfera.con_inversion(), atmosfera.con_inversion(nubes_base_m=250)):
        des = descenso.simular(atm, Vuelo(), 20, rng)
        res = [mision.analizar(atm, des, i, rng) for i in range(des.corridas)]
        resultados[atm.base_nubes() is None] = res
    assert all(r.despejado_detectado for r in resultados[True])
    assert not any(r.despejado_detectado for r in resultados[False])
    assert np.mean([r.indicador_wm2 for r in resultados[True]]) < -60
