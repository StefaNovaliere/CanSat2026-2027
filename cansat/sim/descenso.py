"""Descenso vertical con paracaídas. Todas las corridas se integran juntas
(vectorizado) para que miles de vuelos tarden segundos.

Por ahora es 1D: no hay viento ni péndulo. Eso viene en la etapa 2.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .atmosfera import G, Atmosfera
from .parametros import Vuelo


@dataclass
class Descensos:
    t_s: np.ndarray          # tiempos comunes (pasos,)
    z_m: np.ndarray          # altura sobre el suelo (pasos, corridas); 0 después de aterrizar
    v_ms: np.ndarray         # velocidad hacia abajo (pasos, corridas)
    t_aterrizaje_s: np.ndarray
    altura_separacion_m: np.ndarray
    dt_s: float

    @property
    def corridas(self) -> int:
        return self.z_m.shape[1]

    def corrida(self, i: int):
        """Tiempo, altura y velocidad de una corrida hasta que aterriza."""
        n = int(round(self.t_aterrizaje_s[i] / self.dt_s)) + 1
        return self.t_s[:n], self.z_m[:n, i], self.v_ms[:n, i]


def simular(atm: Atmosfera, vuelo: Vuelo, corridas: int, rng: np.random.Generator,
            t_max_s: float = 300.0) -> Descensos:
    n = corridas
    h0 = rng.normal(vuelo.altura_separacion_m, vuelo.sd_altura_separacion_m, n)
    h0 = np.clip(h0, 50.0, atm.z_m[-1] - 1)
    demora = np.clip(rng.normal(vuelo.demora_apertura_s, vuelo.sd_demora_apertura_s, n), 0.0, None)
    masa = rng.normal(vuelo.masa_kg, vuelo.sd_masa_kg, n)
    cd_par = np.clip(rng.normal(vuelo.cd_paracaidas, vuelo.sd_cd_paracaidas, n), 0.1, None)
    area_lata = np.pi * (vuelo.diametro_lata_m / 2) ** 2
    area_par = np.pi * (vuelo.diametro_paracaidas_m / 2) ** 2

    dt = vuelo.dt_s
    pasos_max = int(t_max_s / dt)
    z_hist = np.empty((pasos_max + 1, n))
    v_hist = np.empty((pasos_max + 1, n))
    z = h0.copy()
    v = np.full(n, vuelo.velocidad_inicial_ms, dtype=float)
    t_aterrizaje = np.full(n, np.nan)
    z_hist[0], v_hist[0] = z, v

    k = 0
    for k in range(1, pasos_max + 1):
        t = k * dt
        en_vuelo = np.isnan(t_aterrizaje)
        apertura = np.clip((t - demora) / vuelo.tiempo_apertura_s, 0.0, 1.0)
        cda = vuelo.cd_lata * area_lata + cd_par * area_par * apertura
        rho = atm.densidad(np.clip(z, 0.0, None))
        a = G - 0.5 * rho * cda * v * np.abs(v) / masa
        v = np.where(en_vuelo, v + a * dt, 0.0)
        z = np.where(en_vuelo, z - v * dt, 0.0)
        toca = en_vuelo & (z <= 0.0)
        t_aterrizaje[toca] = t
        z[toca] = 0.0
        z_hist[k], v_hist[k] = z, v
        if not np.isnan(t_aterrizaje).any():
            break

    if np.isnan(t_aterrizaje).any():
        raise RuntimeError("Hay corridas que no aterrizaron: revisar paracaídas o t_max_s")
    return Descensos(np.arange(k + 1) * dt, z_hist[:k + 1], v_hist[:k + 1],
                     t_aterrizaje, h0, dt)
