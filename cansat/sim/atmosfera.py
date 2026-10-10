"""Perfil de atmósfera por altura sobre el suelo: temperatura, humedad, presión y densidad."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

G = 9.80665
RD = 287.05  # constante del aire seco, J/(kg K)

UMBRAL_NUBE_HR = 95.0      # % de humedad relativa a partir del cual se considera nube
ESPESOR_MIN_NUBE_M = 30.0  # para no confundir una medición suelta con una capa de nubes
TOPE_NUBES_M = 3000.0      # solo se buscan nubes bajas y medias (las que más pesan en el infrarrojo)


def presion_saturacion_hpa(t_c):
    """Fórmula de Magnus (sobre agua)."""
    t_c = np.asarray(t_c, dtype=float)
    return 6.112 * np.exp(17.62 * t_c / (243.12 + t_c))


@dataclass
class Atmosfera:
    nombre: str
    z_m: np.ndarray       # altura sobre el suelo, grilla de 1 m
    temp_c: np.ndarray
    pres_pa: np.ndarray
    rocio_c: np.ndarray   # punto de rocío
    _cache: dict = field(default_factory=dict, init=False, repr=False, compare=False)

    def temperatura(self, z):
        return np.interp(z, self.z_m, self.temp_c)

    def presion(self, z):
        return np.exp(np.interp(z, self.z_m, np.log(self.pres_pa)))

    def densidad(self, z):
        return self.presion(z) / (RD * (self.temperatura(z) + 273.15))

    def punto_rocio(self, z):
        return np.interp(z, self.z_m, self.rocio_c)

    def presion_vapor_hpa(self, z):
        return presion_saturacion_hpa(self.punto_rocio(z))

    def humedad_relativa(self, z):
        return 100 * self.presion_vapor_hpa(z) / presion_saturacion_hpa(self.temperatura(z))

    def base_nubes(self) -> float | None:
        """Altura de la primera capa saturada (nube) hasta TOPE_NUBES_M, o None si está despejado."""
        if "base_nubes" in self._cache:
            return self._cache["base_nubes"]
        self._cache["base_nubes"] = self._buscar_nubes()
        return self._cache["base_nubes"]

    def _buscar_nubes(self) -> float | None:
        hr = 100 * presion_saturacion_hpa(self.rocio_c) / presion_saturacion_hpa(self.temp_c)
        humedo = (hr >= UMBRAL_NUBE_HR) & (self.z_m <= TOPE_NUBES_M)
        n = int(ESPESOR_MIN_NUBE_M)
        for i in np.flatnonzero(humedo):
            if humedo[i:i + n].all() and i + n <= len(humedo):
                return float(self.z_m[i])
        return None

    @classmethod
    def desde_temperatura(cls, nombre, z_m, temp_c, p_suelo_pa, rocio_c):
        """Integra la presión hacia arriba con la ecuación hipsométrica."""
        t_k = temp_c + 273.15
        t_medio = (t_k[1:] + t_k[:-1]) / 2
        dz = np.diff(z_m)
        log_p = np.log(p_suelo_pa) - np.concatenate([[0.0], np.cumsum(G * dz / (RD * t_medio))])
        return cls(nombre, z_m, temp_c, np.exp(log_p), rocio_c)


def _grilla(tope_m=TOPE_NUBES_M):
    return np.arange(0.0, tope_m + 1.0, 1.0)


def _rocio(z, t, depresion_c, nubes_base_m):
    """Punto de rocío a `depresion_c` grados por debajo de la temperatura.
    Si hay nubes, desde su base hasta 800 m más arriba el aire queda saturado."""
    rocio = t - depresion_c
    if nubes_base_m is not None:
        capa = (z >= nubes_base_m) & (z <= nubes_base_m + 800)
        rocio = np.where(capa, t, rocio)
    return rocio


def estandar(t_suelo_c=10.0, gradiente_c_km=6.5, p_suelo_hpa=950.0,
             depresion_rocio_c=5.0, nubes_base_m=None) -> Atmosfera:
    """Temperatura que baja con la altura a ritmo constante. Sin sorpresas abajo."""
    z = _grilla()
    t = t_suelo_c - gradiente_c_km / 1000 * z
    nombre = "estándar" + (" nublado" if nubes_base_m is not None else "")
    return Atmosfera.desde_temperatura(nombre, z, t, p_suelo_hpa * 100,
                                       _rocio(z, t, depresion_rocio_c, nubes_base_m))


def con_inversion(t_suelo_c=2.0, salto_c=6.0, espesor_inversion_m=100.0,
                  gradiente_c_km=6.5, p_suelo_hpa=950.0, depresion_rocio_c=5.0,
                  nubes_base_m=None) -> Atmosfera:
    """Inversión pegada al suelo: sube `salto_c` en los primeros metros y
    arriba se comporta normal. Parecida a una mañana fría de invierno."""
    z = _grilla()
    t = (t_suelo_c + salto_c * np.minimum(z / espesor_inversion_m, 1.0)
         - gradiente_c_km / 1000 * np.maximum(z - espesor_inversion_m, 0.0))
    nombre = "inversión" + (" nublado" if nubes_base_m is not None else "")
    return Atmosfera.desde_temperatura(nombre, z, t, p_suelo_hpa * 100,
                                       _rocio(z, t, depresion_rocio_c, nubes_base_m))


def desde_sondeo(s) -> Atmosfera:
    """Usa un sondeo real (cansat.sondeos.Sondeo). Las alturas se toman
    sobre el suelo de la estación del sondeo."""
    tope = float(min(s.agl_m[-1], TOPE_NUBES_M))
    z = _grilla(tope)
    t = s.columna_a("TEMP", z)
    ok = ~np.isnan(s.pres_hpa)
    log_p = np.interp(z, s.agl_m[ok], np.log(s.pres_hpa[ok] * 100))
    if "DWPT" in s.columnas and (~np.isnan(s.columnas["DWPT"])).sum() >= 2:
        rocio = np.minimum(s.columna_a("DWPT", z), t)
    else:
        rocio = t - 5.0  # sin dato de humedad: supuesto
    return Atmosfera(s.etiqueta(), z, t, np.exp(log_p), rocio)
