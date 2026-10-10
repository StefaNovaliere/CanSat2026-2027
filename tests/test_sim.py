import numpy as np

from cansat import sondeos
from cansat.estacion.receptor import Receptor
from cansat.sim import __main__ as sim
from cansat.sim import atmosfera, descenso, mision, sensores
from cansat.sim.parametros import Vuelo


def test_atmosfera_estandar_es_coherente():
    atm = atmosfera.estandar(t_suelo_c=15, p_suelo_hpa=1013.25)
    # unos 12 hPa menos cada 100 m cerca del nivel del mar
    assert 1000 < atm.presion(100) / 100 < 1002
    assert atm.temperatura(400) == np.float64(15 - 0.0065 * 400)


def test_paracaidas_baja_a_velocidad_razonable():
    rng = np.random.default_rng(0)
    des = descenso.simular(atmosfera.estandar(), Vuelo(), 20, rng)
    assert np.all(des.t_aterrizaje_s > 30) and np.all(des.t_aterrizaje_s < 70)
    t, z, v = des.corrida(0)
    assert 6 < v[-2] < 12


def test_correccion_de_retardo_recupera_una_rampa():
    t = np.arange(0, 20, 0.01)
    aire = 10 - 0.5 * t  # baja medio grado por segundo
    tau = 2.0
    serie, _ = sensores.termometro(
        t, aire,
        sensores.Termometro("x", tau, 0.0, 0.0, 0.0, 0.0, 10, 0.0, 0.0),
        np.random.default_rng(0))
    corregida = mision.corregir_retardo(serie, tau, 0.5)
    medio = (serie.t_s > 10) & (serie.t_s < 18)
    real = np.interp(serie.t_s, t, aire)
    assert np.max(np.abs(serie.valor[medio] - real[medio])) > 0.9  # sin corregir atrasa ~1 °C
    assert np.max(np.abs(corregida[medio] - real[medio])) < 0.05


def test_mision_detecta_inversion_y_no_inventa_fallas():
    rng = np.random.default_rng(3)
    for atm, esperado in ((atmosfera.con_inversion(), True), (atmosfera.estandar(), False)):
        des = descenso.simular(atm, Vuelo(), 30, rng)
        res = [mision.analizar(atm, des, i, rng) for i in range(des.corridas)]
        assert all(r.falla_detectada == esperado for r in res)


def test_corre_con_un_sondeo_y_exporta_telemetria(tmp_path):
    from pathlib import Path
    fixture = Path(__file__).parent / "fixtures" / "sondeos_sinteticos.txt"
    sim.main(["--sondeo", str(fixture), "--corridas", "20", "--salida", str(tmp_path), "--telemetria"])
    assert (tmp_path / "errores.png").exists()
    r = Receptor()
    paquetes = r.alimentar((tmp_path / "telemetria_simulada.bin").read_bytes())
    assert len(paquetes) > 100
    assert paquetes[0].altitude_m > 250 and paquetes[-1].state == 5
    assert r.errores == 0


def test_ya_en_el_suelo_mide_bien_aunque_la_inversion_sea_fuerte():
    rng = np.random.default_rng(5)
    atm = atmosfera.con_inversion(salto_c=10.0, espesor_inversion_m=50.0)
    des = descenso.simular(atm, Vuelo(), 30, rng)
    res = [mision.analizar(atm, des, i, rng) for i in range(des.corridas)]
    err_bajando = np.mean([r.medicion_suelo_c["termistor corregido"] - r.t_suelo_real_c for r in res])
    err_quieto = np.mean([r.medicion_aterrizado_c["termistor corregido"] - r.t_suelo_real_c for r in res])
    assert err_bajando > 0.3
    assert abs(err_quieto) < 0.1
