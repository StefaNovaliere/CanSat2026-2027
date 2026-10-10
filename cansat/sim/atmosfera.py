"""Perfil de atmósfera por altura sobre el suelo: temperatura, presión y densidad."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

G = 9.80665
RD = 287.05  # constante del aire seco, J/(kg K)


@dataclass
class Atmosfera:
    nombre: str
    z_m: np.ndarray       # altura sobre el suelo, grilla de 1 m
    temp_c: np.ndarray
    pres_pa: np.ndarray

    def temperatura(self, z):
        return np.interp(z, self.z_m, self.temp_c)

    def presion(self, z):
        return np.exp(np.interp(z, self.z_m, np.log(self.pres_pa)))

    def densidad(self, z):
        return self.presion(z) / (RD * (self.temperatura(z) + 273.15))

    @classmethod
    def desde_temperatura(cls, nombre, z_m, temp_c, p_suelo_pa):
        """Integra la presión hacia arriba con la ecuación hipsométrica."""
        t_k = temp_c + 273.15
        t_medio = (t_k[1:] + t_k[:-1]) / 2
        dz = np.diff(z_m)
        log_p = np.log(p_suelo_pa) - np.concatenate([[0.0], np.cumsum(G * dz / (RD * t_medio))])
        return cls(nombre, z_m, temp_c, np.exp(log_p))


def _grilla(tope_m=1500.0):
    return np.arange(0.0, tope_m + 1.0, 1.0)


def estandar(t_suelo_c=10.0, gradiente_c_km=6.5, p_suelo_hpa=950.0) -> Atmosfera:
    """Temperatura que baja con la altura a ritmo constante. Sin sorpresas abajo."""
    z = _grilla()
    t = t_suelo_c - gradiente_c_km / 1000 * z
    return Atmosfera.desde_temperatura("estándar", z, t, p_suelo_hpa * 100)


def con_inversion(t_suelo_c=2.0, salto_c=6.0, espesor_inversion_m=100.0,
                  gradiente_c_km=6.5, p_suelo_hpa=950.0) -> Atmosfera:
    """Inversión pegada al suelo: sube `salto_c` en los primeros metros y
    arriba se comporta normal. Parecida a una mañana fría de invierno."""
    z = _grilla()
    t = (t_suelo_c + salto_c * np.minimum(z / espesor_inversion_m, 1.0)
         - gradiente_c_km / 1000 * np.maximum(z - espesor_inversion_m, 0.0))
    return Atmosfera.desde_temperatura("inversión", z, t, p_suelo_hpa * 100)


def desde_sondeo(s) -> Atmosfera:
    """Usa un sondeo real (cansat.sondeos.Sondeo). Las alturas se toman
    sobre el suelo de la estación del sondeo."""
    tope = float(min(s.agl_m[-1], 1500.0))
    z = _grilla(tope)
    t = s.columna_a("TEMP", z)
    ok = ~np.isnan(s.pres_hpa)
    log_p = np.interp(z, s.agl_m[ok], np.log(s.pres_hpa[ok] * 100))
    return Atmosfera(s.etiqueta(), z, t, np.exp(log_p))
