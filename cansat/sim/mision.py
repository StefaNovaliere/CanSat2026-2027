"""Misión "sobrevuelo vs. aterrizaje".

Con los primeros metros de caída (el "sobrevuelo") se predice cómo está la
atmósfera en el suelo. Después se compara con lo que mide la lata al final
del descenso (el "aterrizaje") y con el valor real del simulador.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import uniform_filter1d

from . import sensores
from .atmosfera import G, RD, Atmosfera
from .descenso import Descensos
from .parametros import GPS, INTERNO, TERMISTOR, Barometro, Mision, Termometro


def corregir_retardo(serie: sensores.Serie, tau_s: float, ventana_s: float) -> np.ndarray:
    """Invierte la respuesta de primer orden: aire = medido + tau * d(medido)/dt.
    Primero se suaviza, si no la derivada amplifica el ruido."""
    dt = serie.t_s[1] - serie.t_s[0]
    n = max(1, int(round(ventana_s / dt)))
    suave = uniform_filter1d(serie.valor, n, mode="nearest") if n > 1 else serie.valor
    return suave + tau_s * np.gradient(suave, serie.t_s)


@dataclass
class Resultado:
    t_suelo_real_c: float
    p_suelo_real_pa: float
    prediccion_c: dict[str, float] = field(default_factory=dict)
    medicion_suelo_c: dict[str, float] = field(default_factory=dict)
    p_suelo_predicha_pa: float = np.nan
    falla_detectada: bool = False
    duracion_s: float = np.nan
    velocidad_final_ms: float = np.nan
    graficos: dict | None = None


def _prediccion(alt, temp, mascara):
    if mascara.sum() < 5:
        return np.nan
    pendiente, ordenada = np.polyfit(alt[mascara], temp[mascara], 1)
    return float(ordenada)  # temperatura extrapolada a altura 0


def analizar(atm: Atmosfera, des: Descensos, i: int, rng: np.random.Generator,
             mision: Mision = Mision(), baro: Barometro = Barometro(), gps: GPS = GPS(),
             termometros: tuple[Termometro, ...] = (TERMISTOR, INTERNO),
             guardar_graficos: bool = False) -> Resultado:
    t, z, v = des.corrida(i)
    aire_c = atm.temperatura(z)
    r = Resultado(float(atm.temperatura(0.0)), float(atm.presion(0.0)),
                  duracion_s=float(t[-1]), velocidad_final_ms=float(v[-2]))

    alt = sensores.gps_altura(t, z, gps, rng)
    alt_inicial = float(np.median(alt.valor[alt.t_s < 0.5]))

    def sobrevuelo(ts):
        a = np.interp(ts, alt.t_s, alt.valor)
        return a, (ts >= mision.estabilizacion_s) & (a >= alt_inicial - mision.espesor_sobrevuelo_m)

    def ultimos_segundos(ts):
        return ts >= t[-1] - mision.ventana_suelo_s

    if guardar_graficos:
        r.graficos = {"t": t, "z": z, "aire": aire_c, "series": {}}

    clave = f"{termometros[0].nombre} corregido"
    t_media_sobrevuelo = np.nan
    for sensor in termometros:
        serie, _ = sensores.termometro(t, aire_c, sensor, rng)
        a, m = sobrevuelo(serie.t_s)
        abajo = ultimos_segundos(serie.t_s)
        corregida = corregir_retardo(serie, sensor.tau_s, mision.ventana_derivada_s)
        for etiqueta, valores in ((f"{sensor.nombre} corregido", corregida),
                                  (f"{sensor.nombre} crudo", serie.valor)):
            r.prediccion_c[etiqueta] = _prediccion(a, valores, m)
            r.medicion_suelo_c[etiqueta] = float(np.mean(valores[abajo]))
            if etiqueta == clave and m.any():
                t_media_sobrevuelo = float(np.mean(valores[m]))
            if guardar_graficos:
                r.graficos["series"][etiqueta] = (serie.t_s, a, valores, m)

    r.falla_detectada = bool(abs(r.medicion_suelo_c[clave] - r.prediccion_c[clave])
                             > mision.umbral_falla_modelo_c)

    # Presión en el suelo predicha desde arriba con la ecuación hipsométrica,
    # usando la temperatura media entre el sobrevuelo y la predicha en el suelo.
    p = sensores.barometro(t, atm.presion(z), baro, rng)
    a_p, m_p = sobrevuelo(p.t_s)
    if m_p.sum() >= 5:
        t_medio_k = 273.15 + 0.5 * (r.prediccion_c[clave] + t_media_sobrevuelo)
        r.p_suelo_predicha_pa = float(np.mean(p.valor[m_p])
                                      * np.exp(G * np.mean(a_p[m_p]) / (RD * t_medio_k)))
    return r
