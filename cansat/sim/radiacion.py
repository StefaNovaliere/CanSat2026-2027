"""Radiación infrarroja: lo que ve un termómetro infrarrojo mirando al cielo
o al suelo, y el indicador de enfriamiento radiativo.

Idea tomada de los radiómetros de flujo neto de las sondas chicas de Pioneer
Venus (1978): medir la radiación que baja y la que sube para saber dónde se
gana y dónde se pierde energía.

Modelo simple, con supuestos fuertes:
- Cielo despejado: emisividad efectiva de Brutsaert (1975), que es de banda
  ancha. Un sensor real de banda de ventana (8-14 µm) ve el cielo despejado más
  frío que esto, así que la diferencia real entre despejado y nublado debería
  ser mayor que la simulada.
- Variación con el ángulo: emisividad(θ) = 1 - (1 - e0)^(1/cos θ).
- Nubes bajas: cuerpo negro a la temperatura de su base.
- Suelo: cuerpo negro a la temperatura del aire a 0 m (la piel del suelo en
  una noche despejada suele estar más fría; no se modela).
"""

from __future__ import annotations

import numpy as np
from scipy.signal import lfilter

from .atmosfera import Atmosfera
from .parametros import Radiometro
from .sensores import Serie, _indices

SIGMA = 5.670374419e-8
K0 = 273.15


def emisividad_brutsaert(t_c, e_hpa):
    """Emisividad hemisférica del cielo despejado (Brutsaert 1975)."""
    return 1.24 * (np.asarray(e_hpa) / (np.asarray(t_c) + K0)) ** (1 / 7)


def _hemisferica(e0):
    # Promedio ponderado por coseno de 1 - (1 - e0)^(1/mu) sobre el hemisferio.
    mu = np.linspace(1e-3, 1.0, 400)
    return 1 - 2 * np.trapezoid((1 - e0[:, None]) ** (1 / mu) * mu, mu, axis=1)


_E0 = np.linspace(0.01, 0.999, 300)
_EH = _hemisferica(_E0)


def emisividad_cenit(e_hemisferica):
    """La emisividad en el cenit que da esa emisividad hemisférica."""
    return np.interp(e_hemisferica, _EH, _E0)


CAPA_EMISORA_M = 1000.0  # el cielo despejado se calcula con el aire de este espesor por encima


def _capa_de_arriba(atm: Atmosfera, z):
    """Presión de vapor media y temperatura media (pesada por el vapor) entre z y
    z + CAPA_EMISORA_M. Así, debajo de una inversión el cielo se ve más cálido,
    porque irradia también la capa cálida de arriba."""
    if "integrales_vapor" not in atm._cache:
        e = atm.presion_vapor_hpa(atm.z_m)
        t = atm.temp_c
        dz = np.diff(atm.z_m)
        atm._cache["integrales_vapor"] = (
            np.concatenate([[0.0], np.cumsum((e[1:] + e[:-1]) / 2 * dz)]),
            np.concatenate([[0.0], np.cumsum((e[1:] * t[1:] + e[:-1] * t[:-1]) / 2 * dz)]),
        )
    c_e, c_et = atm._cache["integrales_vapor"]
    z1 = np.clip(z, atm.z_m[0], atm.z_m[-1] - 1)
    z2 = np.minimum(z1 + CAPA_EMISORA_M, atm.z_m[-1])
    integral_e = np.interp(z2, atm.z_m, c_e) - np.interp(z1, atm.z_m, c_e)
    integral_et = np.interp(z2, atm.z_m, c_et) - np.interp(z1, atm.z_m, c_et)
    return integral_e / (z2 - z1), integral_et / integral_e


def brillo_cielo_k(atm: Atmosfera, z, cos_cenit):
    """Temperatura de brillo del cielo vista desde la altura z en una dirección
    (cos_cenit = 1 mirando derecho para arriba). z y cos_cenit pueden ser arrays."""
    z = np.asarray(z, dtype=float)
    cos_cenit = np.asarray(cos_cenit, dtype=float)
    t_aire = atm.temperatura(z) + K0
    base = atm.base_nubes()

    e_capa, t_capa_c = _capa_de_arriba(atm, z)
    e0 = emisividad_cenit(np.clip(emisividad_brutsaert(t_capa_c, e_capa), 0, 0.999))
    mu = np.clip(cos_cenit, 1e-3, 1.0)
    eps = 1 - (1 - e0) ** (1 / mu)
    t_cielo = eps ** 0.25 * (t_capa_c + K0)

    if base is not None:
        t_nube = atm.temperatura(base) + K0
        # Debajo de la nube se ve la base de la nube; adentro, el aire de alrededor.
        t_cielo = np.where(z < base, t_nube, t_aire)
    # Por debajo del horizonte se ve suelo o aire cercano: temperatura del aire.
    return np.where(cos_cenit <= 0.0, t_aire, t_cielo)


def _direcciones(campo_mitad_deg, anillos=6, azimuts=12):
    """Direcciones dentro del campo de visión del sensor y su peso (ángulo sólido × coseno)."""
    beta = np.radians(np.linspace(0, campo_mitad_deg, anillos + 1)[1:] - campo_mitad_deg / (2 * anillos))
    phi = np.linspace(0, 2 * np.pi, azimuts, endpoint=False)
    b, p = np.meshgrid(beta, phi, indexing="ij")
    peso = np.cos(b) * np.sin(b)
    return b.ravel(), p.ravel(), (peso / peso.sum()).ravel()


def lectura_arriba_k(atm, z, inclinacion_rad, campo_mitad_deg):
    """Lo que ve un sensor que apunta al cenit inclinado `inclinacion_rad`,
    promediando la radiación en su campo de visión."""
    b, p, w = _direcciones(campo_mitad_deg)
    z = np.asarray(z, dtype=float)[:, None]
    tau = np.asarray(inclinacion_rad, dtype=float)[:, None]
    cos_cenit = np.cos(b) * np.cos(tau) - np.sin(b) * np.sin(p) * np.sin(tau)
    t = brillo_cielo_k(atm, np.broadcast_to(z, cos_cenit.shape), cos_cenit)
    return (np.sum(w * t ** 4, axis=1)) ** 0.25


def indicador_enfriamiento(t_cielo_c, t_suelo_c):
    """σ(T_cielo⁴ - T_suelo⁴) en W/m². Negativo = el suelo pierde calor hacia el cielo.
    Es lo que ven los sensores, no el flujo neto hemisférico exacto."""
    return SIGMA * ((np.asarray(t_cielo_c) + K0) ** 4 - (np.asarray(t_suelo_c) + K0) ** 4)


def bamboleo(t_s, rng, amplitud_deg=12.0, sd_amplitud_deg=5.0, periodo_s=1.8, sd_periodo_s=0.2):
    """Inclinación del CanSat colgando del paracaídas: un péndulo con algo de ruido."""
    a = np.radians(np.clip(rng.normal(amplitud_deg, sd_amplitud_deg), 2.0, 30.0))
    periodo = max(0.8, rng.normal(periodo_s, sd_periodo_s))
    fase = rng.uniform(0, 2 * np.pi)
    ruido = np.radians(rng.normal(0, 2.0, len(t_s)))
    return np.abs(a * np.sin(2 * np.pi * t_s / periodo + fase) + ruido)


def medir(t_s, verdadero_k, sensor: Radiometro, rng) -> Serie:
    """Aplica al valor verdadero la respuesta, el error por cambio brusco de
    temperatura del sensor (choque térmico al salir del cohete), el error fijo,
    el ruido y la frecuencia de muestreo."""
    dt = t_s[1] - t_s[0]
    verdadero_c = verdadero_k - K0
    alfa = 1 - np.exp(-dt / sensor.tau_s)
    resp, _ = lfilter([alfa], [1.0, -(1 - alfa)], verdadero_c, zi=[(1 - alfa) * verdadero_c[0]])
    choque = rng.normal(0, sensor.sd_choque_termico_c) * np.exp(-t_s / sensor.tau_choque_s)
    idx = _indices(t_s, sensor.frecuencia_hz)
    medido = (resp[idx] + choque[idx] + rng.normal(0, sensor.sd_error_fijo_c)
              + rng.normal(0, sensor.ruido_c, len(idx)))
    return Serie(t_s[idx], medido)
