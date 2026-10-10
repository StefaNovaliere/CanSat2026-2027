"""Lectura y análisis de radiosondeos de la U. de Wyoming.

Uso:
    python -m cansat.sondeos data/sondeos/* --capa 400 --grafico salidas/sondeos.png

Lee dos formatos:
- CSV de la página nueva (un sondeo por archivo, un punto por segundo).
  Si el archivo se llama como lo baja la página, por ejemplo
  "2025061512-87344.csv", de ahí salen la fecha nominal y la estación.
- Tabla TEXT:LIST de la página vieja (columnas de 7 caracteres: PRES HGHT
  TEMP DWPT ...). Un archivo puede tener varios sondeos; cada uno empieza con
  una línea tipo "87344 SACO Cordoba Observations at 12Z 15 Jun 2025". Las
  líneas que empiezan con # se ignoran.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ANCHO_COL = 7
_RE_ENCABEZADO = re.compile(
    r"(?:(\d{5})\s+)?(.*?)\s*Observations at (\d{2})Z (\d{1,2}) (\w{3}) (\d{4})"
)
_MESES = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


@dataclass
class Sondeo:
    estacion: str | None
    fecha: datetime | None
    columnas: dict[str, np.ndarray] = field(repr=False)

    @property
    def alt_m(self) -> np.ndarray:
        return self.columnas["HGHT"]

    @property
    def temp_c(self) -> np.ndarray:
        return self.columnas["TEMP"]

    @property
    def pres_hpa(self) -> np.ndarray:
        return self.columnas["PRES"]

    @property
    def alt_suelo_m(self) -> float:
        return float(self.alt_m[0])

    @property
    def agl_m(self) -> np.ndarray:
        """Altura sobre el suelo de la estación."""
        return self.alt_m - self.alt_m[0]

    def columna_a(self, nombre: str, agl_m) -> np.ndarray:
        """Interpola una columna a alturas sobre el suelo."""
        y = self.columnas[nombre]
        ok = ~np.isnan(y)
        return np.interp(agl_m, self.agl_m[ok], y[ok])

    def etiqueta(self) -> str:
        if self.fecha is None:
            return self.estacion or "sondeo sin fecha"
        return f"{self.estacion or ''} {self.fecha:%Y-%m-%d %HZ}".strip()


def _numero(txt: str) -> float:
    txt = txt.strip()
    if not txt:
        return np.nan
    try:
        return float(txt)
    except ValueError:
        return np.nan


def _fila(linea: str, nombres: list[str]) -> list[float] | None:
    # Primero por ancho fijo, que respeta los campos vacíos.
    valores = [_numero(linea[i * ANCHO_COL:(i + 1) * ANCHO_COL]) for i in range(len(nombres))]
    if not np.isnan(valores[0]) and not np.isnan(valores[1]):
        return valores
    # Si no cuadra el ancho, separado por espacios con todas las columnas.
    partes = linea.split()
    if len(partes) == len(nombres):
        try:
            return [float(p) for p in partes]
        except ValueError:
            return None
    return None


def _cerrar(estacion, fecha, nombres, filas) -> Sondeo | None:
    if not filas:
        return None
    datos = np.array(filas, dtype=float)
    cols = {n: datos[:, i] for i, n in enumerate(nombres)}
    # Los niveles por debajo del suelo vienen sin temperatura: se descartan.
    ok = ~np.isnan(cols["HGHT"]) & ~np.isnan(cols["TEMP"])
    orden = np.argsort(cols["HGHT"][ok])
    cols = {n: v[ok][orden] for n, v in cols.items()}
    if len(cols["HGHT"]) < 2:
        return None
    return Sondeo(estacion, fecha, cols)


def parsear_texto(texto: str) -> list[Sondeo]:
    sondeos: list[Sondeo] = []
    estacion: str | None = None
    fecha: datetime | None = None
    nombres: list[str] | None = None
    filas: list[list[float]] = []
    saltar = 0

    def cerrar():
        nonlocal filas, nombres
        if nombres:
            s = _cerrar(estacion, fecha, nombres, filas)
            if s:
                sondeos.append(s)
        filas, nombres = [], None

    for linea in texto.splitlines():
        limpia = re.sub(r"<[^>]+>", "", linea).rstrip()
        if limpia.lstrip().startswith("#"):
            continue
        m = _RE_ENCABEZADO.search(limpia)
        if m:
            cerrar()
            numero, nombre, hora, dia, mes, anio = m.groups()
            estacion = " ".join(x for x in (numero, nombre.strip()) if x) or None
            fecha = datetime(int(anio), _MESES[mes], int(dia), int(hora), tzinfo=timezone.utc)
            continue
        if "PRES" in limpia and "HGHT" in limpia and "TEMP" in limpia:
            cerrar()
            nombres = limpia.split()
            saltar = 2  # renglón de unidades y renglón de guiones
            continue
        if nombres is None:
            continue
        if saltar:
            saltar -= 1
            continue
        if not limpia.strip() or limpia.lstrip().startswith("-"):
            if filas:
                cerrar()
            continue
        fila = _fila(limpia, nombres)
        if fila is None:
            cerrar()
        else:
            filas.append(fila)
    cerrar()
    return sondeos


# Columnas del CSV de la página nueva -> nombres que usamos acá.
_COLUMNAS_CSV = {
    "pressure_hPa": "PRES",
    "geopotential height_m": "HGHT",
    "temperature_C": "TEMP",
    "dew point temperature_C": "DWPT",
    "relative humidity_%": "RELH",
    "mixing ratio_g/kg": "MIXR",
    "wind direction_degree": "DRCT",
    "wind speed_m/s": "SPED",
    "latitude": "LAT",
    "longitude": "LON",
}
_RE_NOMBRE_CSV = re.compile(r"(\d{4})(\d{2})(\d{2})(\d{2})-(\d{5})")


def parsear_csv(texto: str, nombre_archivo: str = "") -> Sondeo | None:
    filas = list(csv.DictReader(texto.splitlines()))
    if not filas:
        return None
    filas = [{k.strip(): v for k, v in f.items() if k} for f in filas]
    cols = {corto: np.array([_numero(f.get(largo, "")) for f in filas])
            for largo, corto in _COLUMNAS_CSV.items()}

    estacion, fecha = None, None
    m = _RE_NOMBRE_CSV.search(nombre_archivo)
    if m:
        anio, mes, dia, hora, estacion = m.groups()
        fecha = datetime(int(anio), int(mes), int(dia), int(hora), tzinfo=timezone.utc)
    else:
        # Sin nombre estándar: hora sinóptica más cercana al lanzamiento.
        primero = datetime.fromisoformat(filas[0]["time"].strip()).replace(tzinfo=timezone.utc)
        horas = primero.hour + primero.minute / 60
        hora = int(round(horas / 3) * 3) % 24
        fecha = primero.replace(hour=hora, minute=0, second=0)

    ok = ~np.isnan(cols["HGHT"]) & ~np.isnan(cols["TEMP"])
    cols = {k: v[ok] for k, v in cols.items()}
    # Alta resolución: puede repetir alturas. Se queda con la primera de cada una.
    _, primeras = np.unique(cols["HGHT"], return_index=True)
    primeras = np.sort(primeras)
    orden = primeras[np.argsort(cols["HGHT"][primeras], kind="stable")]
    cols = {k: v[orden] for k, v in cols.items()}
    if len(cols["HGHT"]) < 2:
        return None
    return Sondeo(estacion, fecha, cols)


def leer(ruta: str | Path) -> list[Sondeo]:
    ruta = Path(ruta)
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    if texto.lstrip().lower().startswith("time,"):
        s = parsear_csv(texto, ruta.name)
        return [s] if s else []
    return parsear_texto(texto)


@dataclass
class Capa:
    """Resumen de la capa entre el suelo y `espesor_m` metros."""
    t_suelo: float
    t_tope: float
    t_max: float
    agl_t_max: float
    espesor_m: float

    @property
    def delta(self) -> float:
        return self.t_tope - self.t_suelo

    @property
    def gradiente_c_km(self) -> float:
        return self.delta / self.espesor_m * 1000

    def hay_inversion(self, umbral_c: float = 0.5) -> bool:
        return self.t_max - self.t_suelo > umbral_c


def analizar_capa(s: Sondeo, espesor_m: float = 400) -> Capa:
    z = np.linspace(0, espesor_m, int(espesor_m) + 1)
    t = s.columna_a("TEMP", z)
    i = int(np.argmax(t))
    return Capa(float(t[0]), float(t[-1]), float(t[i]), float(z[i]), espesor_m)


def graficar(sondeos: list[Sondeo], ruta: str | Path, espesor_m: float, tope_m: float = 1000):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.5, 7))
    ax.axhspan(0, espesor_m, color="0.92", zorder=0, label=f"caída (0 a {espesor_m:.0f} m)")
    for s in sondeos:
        ok = s.agl_m <= tope_m
        ax.plot(s.temp_c[ok], s.agl_m[ok], marker=".", lw=1.2, label=s.etiqueta())
    ax.set_xlabel("Temperatura (°C)")
    ax.set_ylabel("Altura sobre el suelo (m)")
    ax.set_ylim(0, tope_m)
    ax.grid(alpha=0.3)
    if len(sondeos) <= 16:
        ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.02, 1.0), frameon=False)
    ax.set_title("Perfiles de temperatura")
    fig.tight_layout()
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Analiza radiosondeos de Wyoming (TEXT:LIST).")
    ap.add_argument("archivos", nargs="+")
    ap.add_argument("--capa", type=float, default=400, help="espesor de la capa a analizar, en m")
    ap.add_argument("--umbral", type=float, default=0.5,
                    help="°C por encima del suelo para contar inversión")
    ap.add_argument("--grafico", help="ruta del PNG con los perfiles")
    ap.add_argument("--csv", help="ruta del CSV con el resumen por sondeo")
    args = ap.parse_args(argv)

    sondeos = [s for a in args.archivos for s in leer(a)]
    if not sondeos:
        raise SystemExit("No encontré ningún sondeo en esos archivos.")

    filas = []
    print(f"{'sondeo':34} {'T suelo':>8} {'T tope':>8} {'delta':>7} {'T max':>7} {'a (m)':>6}  inversión")
    for s in sondeos:
        c = analizar_capa(s, args.capa)
        inv = c.hay_inversion(args.umbral)
        print(f"{s.etiqueta():34} {c.t_suelo:8.1f} {c.t_tope:8.1f} {c.delta:+7.1f} "
              f"{c.t_max:7.1f} {c.agl_t_max:6.0f}  {'sí' if inv else 'no'}")
        filas.append({
            "sondeo": s.etiqueta(),
            "fecha_utc": s.fecha.isoformat() if s.fecha else "",
            "t_suelo_c": round(c.t_suelo, 2), "t_tope_c": round(c.t_tope, 2),
            "delta_c": round(c.delta, 2), "t_max_c": round(c.t_max, 2),
            "agl_t_max_m": round(c.agl_t_max), "inversion": inv,
        })

    n_inv = sum(f["inversion"] for f in filas)
    print(f"\n{n_inv} de {len(filas)} sondeos con inversión en los primeros {args.capa:.0f} m")

    if args.csv:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0]))
            w.writeheader()
            w.writerows(filas)
    if args.grafico:
        graficar(sondeos, args.grafico, args.capa)
        print(f"Gráfico: {args.grafico}")


if __name__ == "__main__":
    main()
