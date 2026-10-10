# CanSat 2026-2027 · Ctrl + Espacio

Repo del equipo para el CANSAT Universitario 2026-2027 de CONAE.

## Qué hay

| Carpeta | Qué es |
| --- | --- |
| `firmware/` | Código del ESP32 (PlatformIO). Por ahora el esqueleto de tareas y el paquete de telemetría. |
| `cansat/telemetria.py` | Paquete de telemetría en Python, igual al del firmware. |
| `cansat/estacion/` | Estación terrena: lee la radio o un archivo, decodifica y guarda en CSV. |
| `cansat/sondeos.py` | Lee radiosondeos de Wyoming y busca inversiones cerca del suelo. |
| `cansat/sim/` | Simulador del descenso, los sensores y la misión. |
| `data/sondeos/` | Los sondeos de Córdoba que vayamos bajando. |
| `docs/` | Especificaciones (por ahora, la de telemetría). |
| `tests/` | Tests. |

## Instalar

Python 3.10 o más nuevo.

```
pip install -r requirements.txt
```

Para el firmware hace falta PlatformIO (la extensión de VS Code alcanza).

## Usar

```
# simulador: 500 vuelos con atmósfera estándar y 500 con inversión
python -m cansat.sim --telemetria

# lo mismo con un sondeo real como atmósfera
python -m cansat.sim --sondeo data/sondeos/87344_2025_06.txt --indice 3

# estación terrena con la telemetría simulada (o --puerto COM3 con la radio)
python -m cansat.estacion --archivo salidas/sim/telemetria_simulada.bin

# análisis de sondeos
python -m cansat.sondeos data/sondeos/*.txt --grafico salidas/sondeos.png

# tests (también compila el paquete del firmware con g++ y lo compara con Python)
python -m pytest
```

Las salidas van a `salidas/` y `capturas/`, que no se suben.

## Simulador

Etapa 1: descenso vertical (sin viento todavía), sensores con retardo, ruido y error fijo, y la misión "sobrevuelo vs. aterrizaje": con los primeros 150 m de caída se predice la temperatura y la presión del suelo, y se compara con lo que mide la lata abajo.

Casi todos los números de `cansat/sim/parametros.py` son supuestos. Hay que ir reemplazándolos con lo que midamos (prueba de la heladera para el tiempo de respuesta del termistor, prueba del auto para el Cd del paracaídas) y con lo que digan las bases. Cada vez que se cambie uno, anotar de dónde sale.

Lo que falta: viento y deriva, péndulo del paracaídas, IMU, sensor de luz, y correr el firmware real contra el simulador.

## Telemetría

El formato está en [docs/telemetria.md](docs/telemetria.md). Es un borrador hasta que CONAE diga si hay uno obligatorio.
