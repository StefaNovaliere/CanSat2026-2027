"""Modelos simples de sensores: retardo, ruido, error fijo, resolución y
frecuencia de muestreo. Cada medición devuelve (tiempos, valores)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter

from .parametros import GPS, Barometro, Termometro


@dataclass
class Serie:
    t_s: np.ndarray
    valor: np.ndarray


def _indices(t_s: np.ndarray, frecuencia_hz: float) -> np.ndarray:
    dt = t_s[1] - t_s[0]
    paso = max(1, int(round(1.0 / (frecuencia_hz * dt))))
    return np.arange(0, len(t_s), paso)


def _cuantizar(x, resolucion):
    return np.round(x / resolucion) * resolucion if resolucion > 0 else x


def termometro(t_s, temp_aire_c, sensor: Termometro, rng) -> tuple[Serie, float]:
    """Respuesta de primer orden: el sensor se acerca a la temperatura del aire
    con constante de tiempo tau. Devuelve la serie y el tau real sorteado."""
    dt = t_s[1] - t_s[0]
    tau = sensor.tau_s * max(0.2, 1 + rng.normal(0, sensor.sd_tau_relativo))
    alfa = 1 - np.exp(-dt / tau)
    t0 = temp_aire_c[0] + rng.normal(sensor.calor_inicial_c, sensor.sd_calor_inicial_c)
    # ts[k] = ts[k-1] + alfa * (aire[k-1] - ts[k-1]), con lfilter para que sea rápido
    resto, _ = lfilter([alfa], [1.0, -(1 - alfa)], temp_aire_c[:-1], zi=[(1 - alfa) * t0])
    ts = np.concatenate([[t0], resto])
    idx = _indices(t_s, sensor.frecuencia_hz)
    medido = (ts[idx] + rng.normal(0, sensor.sd_error_fijo_c)
              + rng.normal(0, sensor.ruido_c, len(idx)))
    return Serie(t_s[idx], _cuantizar(medido, sensor.resolucion_c)), tau


def barometro(t_s, pres_pa, sensor: Barometro, rng) -> Serie:
    idx = _indices(t_s, sensor.frecuencia_hz)
    medido = (pres_pa[idx] + rng.normal(0, sensor.sd_error_fijo_pa)
              + rng.normal(0, sensor.ruido_pa, len(idx)))
    return Serie(t_s[idx], medido)


def gps_altura(t_s, z_m, sensor: GPS, rng) -> Serie:
    idx = _indices(t_s, sensor.frecuencia_hz)
    medido = z_m[idx] + rng.normal(0, sensor.sd_error_fijo_m) + rng.normal(0, sensor.ruido_m, len(idx))
    return Serie(t_s[idx], medido)
