"""Parámetros del simulador.

Casi todo es SUPUESTO hasta que lo midamos o lo diga CONAE. Cada vez que
tengamos un dato real (prueba de la heladera, prueba del auto, bases del
certamen) se cambia acá y se anota de dónde salió.

Los campos sd_* son la dispersión (desvío estándar) que se usa en las corridas
Monte Carlo: cada vuelo simulado sortea su propio valor.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Vuelo:
    altura_separacion_m: float = 400.0   # supuesto: el cohete del secundario 2023 llegaba a ~400 m
    sd_altura_separacion_m: float = 20.0
    velocidad_inicial_ms: float = 0.0    # supuesto: se separa cerca del apogeo
    demora_apertura_s: float = 1.0       # desde la separación hasta que empieza a abrir
    sd_demora_apertura_s: float = 0.3
    tiempo_apertura_s: float = 0.5       # lo que tarda en pasar de cerrado a abierto
    masa_kg: float = 0.30                # supuesto: entre los 200 g del secundario y algo más
    sd_masa_kg: float = 0.01
    diametro_lata_m: float = 0.066
    cd_lata: float = 1.0                 # cilindro cayendo de punta, valor de libro
    diametro_paracaidas_m: float = 0.32  # elegido para bajar a ~9-10 m/s
    cd_paracaidas: float = 0.8           # supuesto: se reemplaza con la prueba del auto
    sd_cd_paracaidas: float = 0.08
    dt_s: float = 0.01


@dataclass
class Termometro:
    nombre: str
    tau_s: float                # constante de tiempo (se mide con la prueba de la heladera)
    sd_tau_relativo: float      # cuánto puede diferir el tau real del que usamos para corregir
    ruido_c: float
    sd_error_fijo_c: float      # error que queda después de calibrar en tierra
    resolucion_c: float
    frecuencia_hz: float
    calor_inicial_c: float      # cuánto más caliente que el aire arranca al separarse
    sd_calor_inicial_c: float


# Termistor tipo gota en la cámara de aire, leído con ADS1115. Todo supuesto.
TERMISTOR = Termometro(
    nombre="termistor", tau_s=0.5, sd_tau_relativo=0.15, ruido_c=0.03,
    sd_error_fijo_c=0.1, resolucion_c=0.01, frecuencia_hz=20,
    calor_inicial_c=3.0, sd_calor_inicial_c=1.5,
)

# Sensor dentro de la lata (tipo BME280 sobre la placa). Todo supuesto.
INTERNO = Termometro(
    nombre="interno", tau_s=8.0, sd_tau_relativo=0.2, ruido_c=0.01,
    sd_error_fijo_c=0.3, resolucion_c=0.01, frecuencia_hz=10,
    calor_inicial_c=8.0, sd_calor_inicial_c=3.0,
)


@dataclass
class Barometro:
    ruido_pa: float = 3.0           # supuesto
    sd_error_fijo_pa: float = 50.0  # supuesto
    frecuencia_hz: float = 50


@dataclass
class GPS:
    ruido_m: float = 4.0            # supuesto, en altura
    sd_error_fijo_m: float = 5.0
    frecuencia_hz: float = 5


@dataclass
class Mision:
    estabilizacion_s: float = 3.0         # lo que se descarta después de separarse
    espesor_sobrevuelo_m: float = 150.0   # los primeros metros de caída hacen de "sobrevuelo"
    ventana_suelo_s: float = 0.5          # últimos segundos antes de tocar = "medición abajo" (~4 m)
    ventana_derivada_s: float = 1.0       # suavizado para la corrección de retardo
    umbral_falla_modelo_c: float = 1.5    # diferencia entre predicho y medido para decir que el modelo falló
