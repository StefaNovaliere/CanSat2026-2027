"""Misión "los últimos 400 metros".

Efecto: con los primeros metros de caída (el "sobrevuelo") se predice cómo
está la atmósfera en el suelo, y se compara con lo que mide la lata al final
del descenso y ya aterrizada.

Causa: dos termómetros infrarrojos, uno mirando al cielo y otro al suelo,
miden cuánto calor pierde el suelo por radiación. Con cielo despejado pierde
mucho, se enfría y se forma la inversión; con nubes, no.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import uniform_filter1d

from . import radiacion, sensores
from .atmosfera import G, RD, Atmosfera
from .descenso import Descensos
from .parametros import (GPS, INTERNO, RADIOMETRO_ABAJO, RADIOMETRO_ARRIBA, TERMISTOR, Barometro,
                         Mision, Radiometro, Termometro)


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
    medicion_suelo_c: dict[str, float] = field(default_factory=dict)      # últimos metros bajando
    medicion_aterrizado_c: dict[str, float] = field(default_factory=dict)  # quieto en el suelo
    p_suelo_predicha_pa: float = np.nan
    falla_detectada: bool = False
    duracion_s: float = np.nan
    velocidad_final_ms: float = np.nan
    # radiómetro
    cielo_medido_c: float = np.nan
    suelo_medido_c: float = np.nan
    indicador_wm2: float = np.nan        # con lo que miden los sensores
    indicador_ideal_wm2: float = np.nan  # con sensores perfectos y sin bamboleo
    despejado_detectado: bool = False
    despejado_real: bool = False
    graficos: dict | None = None


def _prediccion(alt, temp, mascara):
    if mascara.sum() < 5:
        return np.nan
    pendiente, ordenada = np.polyfit(alt[mascara], temp[mascara], 1)
    return float(ordenada)  # temperatura extrapolada a altura 0


def analizar(atm: Atmosfera, des: Descensos, i: int, rng: np.random.Generator,
             mision: Mision = Mision(), baro: Barometro = Barometro(), gps: GPS = GPS(),
             termometros: tuple[Termometro, ...] = (TERMISTOR, INTERNO),
             radiometros: tuple[Radiometro, Radiometro] | None = (RADIOMETRO_ARRIBA, RADIOMETRO_ABAJO),
             guardar_graficos: bool = False) -> Resultado:
    t_vuelo, z_vuelo, v = des.corrida(i)
    t_tierra = float(t_vuelo[-1])
    # Se sigue midiendo unos segundos con la lata quieta en el suelo.
    extra = mision.espera_aterrizado_s + mision.ventana_aterrizado_s + 0.5
    n_extra = int(round(extra / des.dt_s))
    t = np.concatenate([t_vuelo, t_tierra + des.dt_s * np.arange(1, n_extra + 1)])
    z = np.concatenate([z_vuelo, np.zeros(n_extra)])
    aire_c = atm.temperatura(z)
    r = Resultado(float(atm.temperatura(0.0)), float(atm.presion(0.0)),
                  duracion_s=t_tierra, velocidad_final_ms=float(v[-2]))

    alt = sensores.gps_altura(t, z, gps, rng)
    alt_inicial = float(np.median(alt.valor[alt.t_s < 0.5]))

    def sobrevuelo(ts):
        a = np.interp(ts, alt.t_s, alt.valor)
        return a, (ts >= mision.estabilizacion_s) & (a >= alt_inicial - mision.espesor_sobrevuelo_m)

    def ultimos_segundos(ts):
        return (ts >= t_tierra - mision.ventana_suelo_s) & (ts <= t_tierra)

    def ya_en_el_suelo(ts):
        desde = t_tierra + mision.espera_aterrizado_s
        return (ts >= desde) & (ts <= desde + mision.ventana_aterrizado_s)

    if guardar_graficos:
        r.graficos = {"t": t, "z": z, "aire": aire_c, "series": {}}

    clave = f"{termometros[0].nombre} corregido"
    t_media_sobrevuelo = np.nan
    for sensor in termometros:
        serie, _ = sensores.termometro(t, aire_c, sensor, rng)
        a, m = sobrevuelo(serie.t_s)
        abajo = ultimos_segundos(serie.t_s)
        quieto = ya_en_el_suelo(serie.t_s)
        corregida = corregir_retardo(serie, sensor.tau_s, mision.ventana_derivada_s)
        for etiqueta, valores in ((f"{sensor.nombre} corregido", corregida),
                                  (f"{sensor.nombre} crudo", serie.valor)):
            r.prediccion_c[etiqueta] = _prediccion(a, valores, m)
            r.medicion_suelo_c[etiqueta] = float(np.mean(valores[abajo]))
            r.medicion_aterrizado_c[etiqueta] = float(np.mean(valores[quieto]))
            if etiqueta == clave and m.any():
                t_media_sobrevuelo = float(np.mean(valores[m]))
            if guardar_graficos:
                r.graficos["series"][etiqueta] = (serie.t_s, a, valores, m)

    r.falla_detectada = bool(abs(r.medicion_aterrizado_c[clave] - r.prediccion_c[clave])
                             > mision.umbral_falla_modelo_c)

    # Presión en el suelo predicha desde arriba con la ecuación hipsométrica,
    # usando la temperatura media entre el sobrevuelo y la predicha en el suelo.
    p = sensores.barometro(t, atm.presion(z), baro, rng)
    a_p, m_p = sobrevuelo(p.t_s)
    if m_p.sum() >= 5:
        t_medio_k = 273.15 + 0.5 * (r.prediccion_c[clave] + t_media_sobrevuelo)
        r.p_suelo_predicha_pa = float(np.mean(p.valor[m_p])
                                      * np.exp(G * np.mean(a_p[m_p]) / (RD * t_medio_k)))

    if radiometros is not None:
        _radiometro(atm, t, z, t_tierra, alt, rng, mision, radiometros, r)
    return r


def _radiometro(atm, t, z, t_tierra, alt, rng, mision: Mision, radiometros, r: Resultado):
    arriba, abajo = radiometros
    k0 = radiacion.K0
    # El cielo se calcula a 20 Hz (alcanza para el péndulo) y se interpola.
    paso = max(1, int(round(0.05 / (t[1] - t[0]))))
    t20, z20 = t[::paso], z[::paso]
    inclinacion = radiacion.bamboleo(t20, rng)
    cielo_k = np.interp(t, t20, radiacion.lectura_arriba_k(atm, z20, inclinacion, arriba.campo_mitad_deg))
    suelo_k = np.full_like(t, atm.temperatura(0.0) + k0)

    s_arriba = radiacion.medir(t, cielo_k, arriba, rng)
    s_abajo = radiacion.medir(t, suelo_k, abajo, rng)

    vuelo = (s_arriba.t_s >= mision.estabilizacion_s) & (s_arriba.t_s <= t_tierra)
    r.cielo_medido_c = float(np.median(s_arriba.valor[vuelo]))
    a_abajo = np.interp(s_abajo.t_s, alt.t_s, alt.valor)
    ultimos = ((s_abajo.t_s >= mision.estabilizacion_s) & (s_abajo.t_s <= t_tierra)
               & (a_abajo <= mision.altura_suelo_radiometro_m))
    if not ultimos.any():
        ultimos = (s_abajo.t_s <= t_tierra)
    r.suelo_medido_c = float(np.median(s_abajo.valor[ultimos]))
    r.indicador_wm2 = float(radiacion.indicador_enfriamiento(r.cielo_medido_c, r.suelo_medido_c))
    r.despejado_detectado = r.indicador_wm2 < mision.umbral_despejado_wm2

    en_vuelo = (t20 >= mision.estabilizacion_s) & (t20 <= t_tierra)
    ideal = radiacion.lectura_arriba_k(atm, z20[en_vuelo], np.zeros(en_vuelo.sum()), arriba.campo_mitad_deg)
    r.indicador_ideal_wm2 = float(radiacion.indicador_enfriamiento(np.median(ideal) - k0, atm.temperatura(0.0)))
    r.despejado_real = atm.base_nubes() is None
