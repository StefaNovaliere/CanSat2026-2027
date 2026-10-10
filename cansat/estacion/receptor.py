"""Arma paquetes a partir de los bytes que llegan de la radio (o de un archivo).

Acepta paquetes binarios y líneas de texto mezclados con basura. Cuenta
errores de CRC, bytes descartados y paquetes perdidos (saltos en packet_count).
"""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .. import telemetria as t

MAX_LINEA = 512


class Receptor:
    def __init__(self, formato: str = "auto"):
        if formato not in ("auto", "binario", "texto"):
            raise ValueError("formato tiene que ser auto, binario o texto")
        self.formato = formato
        self._buf = bytearray()
        self.validos = 0
        self.errores = 0
        self.descartados = 0
        self.perdidos = 0
        self._ultimo: int | None = None

    def _proximo_inicio(self) -> int:
        candidatos = []
        if self.formato in ("auto", "binario"):
            candidatos.append(self._buf.find(t.SYNC))
        if self.formato in ("auto", "texto"):
            candidatos.append(self._buf.find(b"$"))
        candidatos = [c for c in candidatos if c >= 0]
        return min(candidatos) if candidatos else -1

    def alimentar(self, datos: bytes) -> list[t.Paquete]:
        self._buf += datos
        nuevos: list[t.Paquete] = []
        while self._buf:
            inicio = self._proximo_inicio()
            if inicio < 0:
                # Puede quedar medio sync al final: se guarda el último byte.
                self.descartados += len(self._buf) - 1
                del self._buf[:-1]
                break
            if inicio > 0:
                self.descartados += inicio
                del self._buf[:inicio]

            if self._buf.startswith(t.SYNC):
                if len(self._buf) < t.FRAME_LEN:
                    break
                try:
                    nuevos.append(t.desde_binario(bytes(self._buf[:t.FRAME_LEN])))
                    del self._buf[:t.FRAME_LEN]
                except t.ErrorPaquete:
                    self.errores += 1
                    del self._buf[:1]  # resincronizar
            else:  # empieza con $
                fin = self._buf.find(b"\n")
                if fin < 0:
                    if len(self._buf) > MAX_LINEA:
                        self.errores += 1
                        del self._buf[:1]
                        continue
                    break
                linea = bytes(self._buf[:fin + 1])
                del self._buf[:fin + 1]
                try:
                    nuevos.append(t.desde_texto(linea.decode("ascii", errors="replace")))
                except t.ErrorPaquete:
                    self.errores += 1

        for p in nuevos:
            if self._ultimo is not None and p.packet_count > self._ultimo + 1:
                self.perdidos += p.packet_count - self._ultimo - 1
            self._ultimo = p.packet_count
        self.validos += len(nuevos)
        return nuevos

    def resumen(self) -> str:
        total = self.validos + self.perdidos
        pct = 100 * self.perdidos / total if total else 0.0
        return (f"{self.validos} paquetes válidos, {self.perdidos} perdidos ({pct:.1f} %), "
                f"{self.errores} con error, {self.descartados} bytes descartados")


class EscritorCSV:
    def __init__(self, ruta: str | Path):
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self._f = open(ruta, "w", newline="", encoding="utf-8")
        self._w = csv.DictWriter(self._f, fieldnames=["recibido_utc"] + t.CAMPOS)
        self._w.writeheader()

    def escribir(self, p: t.Paquete):
        fila = {"recibido_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds")}
        fila.update(asdict(p))
        self._w.writerow(fila)

    def flush(self):
        self._f.flush()

    def cerrar(self):
        self._f.close()


def describir(p: t.Paquete) -> str:
    try:
        estado = t.Estado(p.state).name
    except ValueError:
        estado = f"estado {p.state}"
    return (f"#{p.packet_count:<5} t={p.time_ms / 1000:7.1f} s  {estado:10} "
            f"alt={p.altitude_m:7.1f} m  P={p.pressure_pa / 100:7.2f} hPa  "
            f"Text={p.temp_ext_c:6.2f} °C  Tint={p.temp_int_c:6.2f} °C  bat={p.battery_mv / 1000:.2f} V")
