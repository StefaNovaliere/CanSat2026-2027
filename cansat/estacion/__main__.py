"""Estación terrena (esqueleto): lee la telemetría, la muestra y la guarda.

    python -m cansat.estacion --puerto /dev/ttyUSB0          # en Windows: --puerto COM3
    python -m cansat.estacion --archivo salidas/sim/telemetria_simulada.bin

Con --puerto también guarda los bytes crudos, para poder volver a
procesar el vuelo si después cambia el decodificador.
Falta: gráficos en vivo, mapa y envío de comandos.
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

from .receptor import EscritorCSV, Receptor, describir


def _procesar(receptor: Receptor, escritor: EscritorCSV, datos: bytes, silencioso: bool):
    for p in receptor.alimentar(datos):
        escritor.escribir(p)
        if not silencioso:
            print(describir(p))


def desde_archivo(ruta, receptor, escritor, silencioso=False):
    with open(ruta, "rb") as f:
        while bloque := f.read(256):
            _procesar(receptor, escritor, bloque, silencioso)


def desde_puerto(puerto, baudios, receptor, escritor, crudo_ruta):
    import serial  # pyserial, solo hace falta en este modo

    with serial.Serial(puerto, baudios, timeout=0.1) as s, open(crudo_ruta, "ab") as crudo:
        print(f"Escuchando {puerto} a {baudios} baudios. Ctrl+C para cortar.")
        ultimo_flush = time.monotonic()
        try:
            while True:
                datos = s.read(512)
                if datos:
                    crudo.write(datos)
                    _procesar(receptor, escritor, datos, False)
                if time.monotonic() - ultimo_flush > 1.0:
                    crudo.flush()
                    escritor.flush()
                    ultimo_flush = time.monotonic()
        except KeyboardInterrupt:
            print()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Estación terrena del CanSat.")
    origen = ap.add_mutually_exclusive_group(required=True)
    origen.add_argument("--puerto", help="puerto serie de la radio, ej. /dev/ttyUSB0 o COM3")
    origen.add_argument("--archivo", help="archivo con bytes grabados (o simulados)")
    ap.add_argument("--baudios", type=int, default=115200)
    ap.add_argument("--formato", choices=["auto", "binario", "texto"], default="auto")
    ap.add_argument("--salida", help="CSV de salida (por defecto en capturas/)")
    ap.add_argument("--silencioso", action="store_true", help="no imprime cada paquete")
    args = ap.parse_args(argv)

    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    salida = Path(args.salida or f"capturas/telemetria_{marca}.csv")
    receptor = Receptor(args.formato)
    escritor = EscritorCSV(salida)
    try:
        if args.archivo:
            desde_archivo(args.archivo, receptor, escritor, args.silencioso)
        else:
            desde_puerto(args.puerto, args.baudios, receptor, escritor, salida.with_suffix(".bin"))
    finally:
        escritor.cerrar()
    print(receptor.resumen())
    print(f"CSV: {salida}")


if __name__ == "__main__":
    main()
