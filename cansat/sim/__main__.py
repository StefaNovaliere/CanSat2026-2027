"""Simulador, etapa 1: descenso vertical + sensores + misión "los últimos 400 metros".

    python -m cansat.sim                                  # estándar e inversión, 500 vuelos cada uno
    python -m cansat.sim --sondeo data/sondeos/*.csv      # cada sondeo real como atmósfera
    python -m cansat.sim --corridas 2000 --telemetria

Deja gráficos, un CSV por vuelo y un resumen en --salida. Con varios
escenarios también arma una tabla y un gráfico que los comparan.
"""

from __future__ import annotations

import argparse
import csv
import unicodedata
from pathlib import Path

import numpy as np

from .. import sondeos, telemetria
from . import atmosfera, descenso, mision, sensores
from .parametros import INTERNO, TERMISTOR, Barometro, Mision, Vuelo


def _resumir(nombre, atm, des, res, mis: Mision) -> str:
    def ms(x):
        x = np.asarray(x, dtype=float)
        x = x[~np.isnan(x)]
        return f"{np.mean(x):+6.2f} ± {np.std(x):4.2f}"

    lineas = [f"== {nombre} ({len(res)} vuelos) ==",
              f"T real en el suelo: {res[0].t_suelo_real_c:.1f} °C",
              f"{'':22}{'predicción desde arriba':>25}{'últimos metros':>18}{'ya en el suelo':>18}"]
    for clave in res[0].prediccion_c:
        pred = [r.prediccion_c[clave] - r.t_suelo_real_c for r in res]
        med = [r.medicion_suelo_c[clave] - r.t_suelo_real_c for r in res]
        quieto = [r.medicion_aterrizado_c[clave] - r.t_suelo_real_c for r in res]
        lineas.append(f"{clave:22}{ms(pred):>25}{ms(med):>18}{ms(quieto):>18}")
    det = np.mean([r.falla_detectada for r in res]) * 100
    dp = [(r.p_suelo_predicha_pa - r.p_suelo_real_pa) / 100 for r in res]
    lineas += [
        "(errores en °C respecto del valor real: media ± desvío)",
        f"Vuelos donde la predicción de arriba difiere en más de {mis.umbral_falla_modelo_c} °C "
        f"de lo medido ya en el suelo (termistor corregido): {det:.0f} %",
        f"Error al predecir la presión del suelo: {ms(dp)} hPa",
        f"Duración del descenso: {np.mean(des.t_aterrizaje_s):.1f} ± {np.std(des.t_aterrizaje_s):.1f} s, "
        f"velocidad final {np.mean([r.velocidad_final_ms for r in res]):.1f} m/s",
    ]
    if not np.isnan(res[0].indicador_wm2):
        base = atm.base_nubes()
        cielo = "despejado" if base is None else f"nubes a {base:.0f} m"
        lineas += [
            f"Radiómetro ({cielo} según el sondeo): cielo {ms([r.cielo_medido_c for r in res])} °C, "
            f"suelo {ms([r.suelo_medido_c for r in res])} °C",
            f"  indicador de enfriamiento {ms([r.indicador_wm2 for r in res])} W/m² "
            f"(con sensores perfectos {np.mean([r.indicador_ideal_wm2 for r in res]):+.0f}), "
            f"clasificado despejado en {100 * np.mean([r.despejado_detectado for r in res]):.0f} % de los vuelos",
        ]
    return "\n".join(lineas)


def _grafico_ejemplo(nombre, atm, r: mision.Resultado, ruta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    g = r.graficos
    fig, ax = plt.subplots(figsize=(7, 7))
    z_max = g["z"][0]
    zz = np.linspace(0, z_max, 200)
    ax.plot(atm.temperatura(zz), zz, "k", lw=2.5, label="aire (real)")
    estilos = {"termistor crudo": ("tab:orange", 0.35), "termistor corregido": ("tab:red", 1.0),
               "interno crudo": ("tab:blue", 0.35), "interno corregido": ("tab:cyan", 0.6)}
    for clave, (t_s, a, valores, m) in g["series"].items():
        color, alfa = estilos.get(clave, ("gray", 0.5))
        z_real = np.interp(t_s, g["t"], g["z"])
        ax.plot(valores, z_real, color=color, alpha=alfa, lw=1, label=clave)
    t_s, a, valores, m = g["series"]["termistor corregido"]
    ax.scatter(valores[m], np.interp(t_s[m], g["t"], g["z"]), s=6, color="tab:red", zorder=3,
               label="sobrevuelo (datos usados)")
    pend, ordenada = np.polyfit(a[m], valores[m], 1)
    ax.plot(ordenada + pend * zz, zz, "--", color="tab:red", lw=1.2, label="predicción desde arriba")
    ax.plot([r.t_suelo_real_c], [0], "k*", ms=14, label="suelo (real)")
    ax.set_xlabel("Temperatura (°C)")
    ax.set_ylabel("Altura sobre el suelo (m)")
    ax.set_title(f"Un vuelo simulado: {nombre}")
    lo = min(np.nanmin(atm.temperatura(zz)), r.t_suelo_real_c) - 3
    hi = np.nanmax(atm.temperatura(zz)) + 6
    ax.set_xlim(lo, hi)
    ax.set_ylim(0, z_max * 1.02)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def _grafico_errores(todos, ruta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(len(todos), 1, figsize=(8, 4.2 * len(todos)), squeeze=False)
    for ax, (nombre, res) in zip(axes[:, 0], todos):
        datos, etiquetas = [], []
        for clave in res[0].prediccion_c:
            datos.append([r.prediccion_c[clave] - r.t_suelo_real_c for r in res])
            etiquetas.append(f"predicción · {clave}")
        for clave in res[0].medicion_suelo_c:
            datos.append([r.medicion_suelo_c[clave] - r.t_suelo_real_c for r in res])
            etiquetas.append(f"últimos metros · {clave}")
        for clave in res[0].medicion_aterrizado_c:
            datos.append([r.medicion_aterrizado_c[clave] - r.t_suelo_real_c for r in res])
            etiquetas.append(f"ya en el suelo · {clave}")
        ax.boxplot(datos, orientation="horizontal", tick_labels=etiquetas, showfliers=False)
        ax.axvline(0, color="k", lw=0.8)
        ax.set_title(nombre)
        ax.set_xlabel("Error respecto de la temperatura real del suelo (°C)")
        ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


CLAVE = "termistor corregido"


def _fila_comparacion(atm, res, mis: Mision) -> dict:
    pred = np.array([r.prediccion_c[CLAVE] - r.t_suelo_real_c for r in res])
    suelo = np.array([r.medicion_aterrizado_c[CLAVE] - r.t_suelo_real_c for r in res])
    ind = np.array([r.indicador_wm2 for r in res])
    base = atm.base_nubes()
    zz = np.linspace(0, 400, 401)
    return {
        "escenario": atm.nombre,
        "t_suelo_c": round(res[0].t_suelo_real_c, 2),
        "t_400m_c": round(float(atm.temperatura(400.0)), 2),
        "error_prediccion_c": round(float(np.mean(pred)), 2),
        "sd_prediccion_c": round(float(np.std(pred)), 2),
        "error_en_el_suelo_c": round(float(np.mean(suelo)), 2),
        "sd_en_el_suelo_c": round(float(np.std(suelo)), 2),
        "falla_detectada_pct": round(100 * float(np.mean([r.falla_detectada for r in res])), 1),
        "inversion_c": round(float(np.max(atm.temperatura(zz)) - atm.temperatura(0.0)), 2),
        "nubes_base_m": "" if base is None else round(base),
        "indicador_wm2": round(float(np.mean(ind)), 1),
        "sd_indicador_wm2": round(float(np.std(ind)), 1),
        "despejado_detectado_pct": round(100 * float(np.mean([r.despejado_detectado for r in res])), 1),
    }


def _tabla_comparacion(filas, mis: Mision) -> str:
    lineas = [f"== Comparación ({CLAVE}) ==",
              f"{'escenario':26}{'T suelo':>9}{'T 400 m':>9}{'error predicción':>20}"
              f"{'error en el suelo':>20}{'falla detectada':>17}"]
    for f in filas:
        lineas.append(
            f"{f['escenario']:26}{f['t_suelo_c']:9.1f}{f['t_400m_c']:9.1f}"
            f"{f['error_prediccion_c']:+13.1f} ± {f['sd_prediccion_c']:3.1f}"
            f"{f['error_en_el_suelo_c']:+13.1f} ± {f['sd_en_el_suelo_c']:3.1f}"
            f"{f['falla_detectada_pct']:15.0f} %")
    n_falla = sum(f["falla_detectada_pct"] >= 50 for f in filas)
    lineas.append(f"La predicción desde arriba falla por más de {mis.umbral_falla_modelo_c} °C "
                  f"en {n_falla} de {len(filas)} escenarios.")
    lineas += ["", "== Causa: radiómetro infrarrojo ==",
               f"{'escenario':26}{'cielo (sondeo)':>16}{'inversión':>11}{'indicador (W/m²)':>20}{'clasificado despejado':>24}"]
    for f in filas:
        cielo = "despejado" if f["nubes_base_m"] == "" else f"nubes {f['nubes_base_m']} m"
        lineas.append(f"{f['escenario']:26}{cielo:>16}{f['inversion_c']:+9.1f} °C"
                      f"{f['indicador_wm2']:+13.0f} ± {f['sd_indicador_wm2']:<4.0f}"
                      f"{f['despejado_detectado_pct']:20.0f} %")
    aciertos = sum((f["despejado_detectado_pct"] >= 50) == (f["nubes_base_m"] == "") for f in filas)
    lineas.append(f"El radiómetro clasifica bien el cielo en {aciertos} de {len(filas)} escenarios "
                  f"(umbral {mis.umbral_despejado_wm2:.0f} W/m²).")
    return "\n".join(lineas)


def _grafico_causa_efecto(filas, mis: Mision, ruta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    ax.axvline(mis.umbral_despejado_wm2, color="0.5", ls="--", lw=1)
    ax.axhline(0, color="0.8", lw=0.8)
    usados = []
    for despejado, color, etiqueta in ((True, "tab:blue", "cielo despejado (sondeo)"),
                                       (False, "tab:gray", "con nubes bajas o medias (sondeo)")):
        sel = [f for f in filas if (f["nubes_base_m"] == "") == despejado]
        if not sel:
            continue
        ax.errorbar([f["indicador_wm2"] for f in sel], [f["inversion_c"] for f in sel],
                    xerr=[f["sd_indicador_wm2"] for f in sel], fmt="o", color=color, ms=7,
                    capsize=3, label=etiqueta)
        for f in sel:
            # Si hay puntos casi encima de este, la etiqueta se corre para abajo.
            vecinos = sum(1 for o in usados if abs(o[0] - f["indicador_wm2"]) < 6 and abs(o[1] - f["inversion_c"]) < 0.6)
            usados.append((f["indicador_wm2"], f["inversion_c"]))
            nombre = f["escenario"].split()[-2] if f["escenario"][:5].isdigit() else f["escenario"]
            ax.annotate(nombre, (f["indicador_wm2"], f["inversion_c"]), textcoords="offset points",
                        xytext=(6, 5 - 11 * vecinos), fontsize=7.5, color="0.3")
    ax.text(mis.umbral_despejado_wm2, ax.get_ylim()[1], " umbral", va="top", fontsize=8, color="0.4")
    ax.set_xlabel("Indicador de enfriamiento medido por el radiómetro (W/m²)\n← el suelo pierde más calor")
    ax.set_ylabel("Fuerza de la inversión en los primeros 400 m (°C)")
    ax.set_title("Causa (radiación) contra efecto (inversión)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, frameon=False)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _grafico_comparacion(filas, ruta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    y = np.arange(len(filas))[::-1]
    fig, ax = plt.subplots(figsize=(8, 1.0 + 0.55 * len(filas)))
    ax.axvline(0, color="k", lw=0.8)
    ax.errorbar([f["error_prediccion_c"] for f in filas], y + 0.12,
                xerr=[f["sd_prediccion_c"] for f in filas], fmt="o", color="tab:red",
                capsize=3, label="predicción desde arriba (primeros 150 m)")
    ax.errorbar([f["error_en_el_suelo_c"] for f in filas], y - 0.12,
                xerr=[f["sd_en_el_suelo_c"] for f in filas], fmt="s", color="k",
                capsize=3, label="medición ya en el suelo")
    ax.set_yticks(y, [f["escenario"] for f in filas])
    ax.set_xlabel("Error respecto de la temperatura real del suelo (°C)")
    ax.set_title("Termistor corregido, por escenario")
    ax.grid(alpha=0.3, axis="x")
    ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=2, frameon=False)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _guardar_csv(nombre, res, ruta):
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        claves = list(res[0].prediccion_c)
        w.writerow(["escenario", "t_suelo_real_c", "p_suelo_real_pa", "p_suelo_predicha_pa",
                    "falla_detectada", "duracion_s"]
                   + [f"pred {c}" for c in claves] + [f"ultimos metros {c}" for c in claves]
                   + [f"en el suelo {c}" for c in claves])
        for r in res:
            w.writerow([nombre, f"{r.t_suelo_real_c:.3f}", f"{r.p_suelo_real_pa:.1f}",
                        f"{r.p_suelo_predicha_pa:.1f}", int(r.falla_detectada), f"{r.duracion_s:.2f}"]
                       + [f"{r.prediccion_c[c]:.3f}" for c in claves]
                       + [f"{r.medicion_suelo_c[c]:.3f}" for c in claves]
                       + [f"{r.medicion_aterrizado_c[c]:.3f}" for c in claves])


def exportar_telemetria(atm, des, rng, ruta, hz=5.0, perdida=0.05):
    """Genera lo que mandaría la radio en un vuelo, para probar la estación
    terrena sin hardware. Pierde algunos paquetes y mete basura entre medio."""
    t, z, _ = des.corrida(0)
    aire = atm.temperatura(z)
    term, _ = sensores.termometro(t, aire, TERMISTOR, rng)
    inte, _ = sensores.termometro(t, aire, INTERNO, rng)
    baro = sensores.barometro(t, atm.presion(z), Barometro(), rng)
    p0 = float(atm.presion(0.0))
    tiempos = np.arange(0, t[-1] + 3.0, 1.0 / hz)  # 3 s extra ya en el suelo
    salida = bytearray()
    for n, ti in enumerate(tiempos):
        p = float(np.interp(ti, baro.t_s, baro.valor))
        en_el_aire = ti < t[-1]
        paq = telemetria.Paquete(
            team_id=0, time_ms=int(ti * 1000), packet_count=n,
            state=telemetria.Estado.DESCENSO if en_el_aire else telemetria.Estado.ATERRIZADO,
            altitude_m=44330.0 * (1 - (p / p0) ** 0.1903), pressure_pa=p,
            temp_int_c=float(np.interp(ti, inte.t_s, inte.valor)),
            temp_ext_c=float(np.interp(ti, term.t_s, term.valor)),
            battery_mv=4100 - int(ti * 2), lat_e7=-314000000, lon_e7=-641800000,  # coordenadas de ejemplo
            light_up=0, light_down=0,
            flags=telemetria.Flags.GPS_FIX | telemetria.Flags.SD_OK | telemetria.Flags.PARACAIDAS
            | (0 if en_el_aire else telemetria.Flags.BALIZA),
        )
        if rng.random() < perdida:
            continue
        if rng.random() < 0.03:
            salida += rng.integers(0, 256, 5, dtype=np.uint8).tobytes()
        salida += telemetria.a_binario(paq)
    Path(ruta).write_bytes(bytes(salida))
    return len(tiempos)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Simulador CanSat, etapa 1.")
    ap.add_argument("--corridas", type=int, default=500)
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--sondeo", nargs="+", help="uno o más archivos de Wyoming para usar como atmósfera")
    ap.add_argument("--indice", type=int,
                    help="en archivos con varios sondeos, usar solo ese (por defecto, todos)")
    ap.add_argument("--salida", default="salidas/sim")
    ap.add_argument("--telemetria", action="store_true",
                    help="exporta la telemetría de un vuelo para probar la estación terrena")
    args = ap.parse_args(argv)

    if args.sondeo:
        lista = []
        for archivo in args.sondeo:
            leidos = sondeos.leer(archivo)
            lista += [leidos[args.indice]] if args.indice is not None else leidos
        lista.sort(key=lambda s: (s.fecha is None, s.fecha))
        escenarios = [atmosfera.desde_sondeo(s) for s in lista]
    else:
        escenarios = [atmosfera.estandar(), atmosfera.con_inversion()]

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    vuelo, mis = Vuelo(), Mision()
    rng = np.random.default_rng(args.semilla)
    todos, textos, filas = [], [], []

    for atm in escenarios:
        des = descenso.simular(atm, vuelo, args.corridas, rng)
        res = [mision.analizar(atm, des, i, rng, mis, guardar_graficos=(i == 0))
               for i in range(des.corridas)]
        sin_tildes = unicodedata.normalize("NFKD", atm.nombre.lower()).encode("ascii", "ignore").decode()
        slug = "".join(c if c.isalnum() else "_" for c in sin_tildes)
        _grafico_ejemplo(atm.nombre, atm, res[0], salida / f"ejemplo_{slug}.png")
        _guardar_csv(atm.nombre, res, salida / f"vuelos_{slug}.csv")
        texto = _resumir(atm.nombre, atm, des, res, mis)
        print(texto + "\n")
        textos.append(texto)
        todos.append((atm.nombre, res))
        filas.append(_fila_comparacion(atm, res, mis))
        if args.telemetria and len(todos) == 1:
            n = exportar_telemetria(atm, des, rng, salida / "telemetria_simulada.bin")
            print(f"Telemetría simulada: {n} paquetes en {salida / 'telemetria_simulada.bin'}\n")

    if len(todos) <= 3:
        _grafico_errores(todos, salida / "errores.png")
    if len(filas) > 1:
        tabla = _tabla_comparacion(filas, mis)
        print(tabla + "\n")
        textos.append(tabla)
        _grafico_comparacion(filas, salida / "comparacion.png")
        _grafico_causa_efecto(filas, mis, salida / "causa_efecto.png")
        with open(salida / "comparacion.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0]))
            w.writeheader()
            w.writerows(filas)
    (salida / "resumen.txt").write_text("\n\n".join(textos) + "\n", encoding="utf-8")
    print(f"Gráficos y CSV en {salida}/")


if __name__ == "__main__":
    main()
