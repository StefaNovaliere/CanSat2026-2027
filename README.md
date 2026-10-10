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

# lo mismo con cada sondeo real como atmósfera (arma una tabla y un gráfico comparando)
python -m cansat.sim --sondeo data/sondeos/*.csv

# estación terrena con la telemetría simulada (o --puerto COM3 con la radio)
python -m cansat.estacion --archivo salidas/sim/telemetria_simulada.bin

# análisis de sondeos
python -m cansat.sondeos data/sondeos/*.csv --grafico salidas/sondeos.png

# tests (también compila el paquete del firmware con g++ y lo compara con Python)
python -m pytest
```

Las salidas van a `salidas/` y `capturas/`, que no se suben.

## Simulador

Etapa 1: descenso vertical (sin viento todavía), sensores con retardo, ruido y error fijo, y la misión "los últimos 400 metros", inspirada en la atmósfera profunda de Venus (el único perfil que llegó a su superficie, el de VeGa-2, no siguió lo esperado en los últimos kilómetros).

- **Efecto:** con los primeros 150 m de caída se predice la temperatura y la presión del suelo, y se compara con lo que mide la lata en los últimos metros y ya quieta en el suelo.
- **Causa:** dos termómetros infrarrojos, uno mirando al cielo y otro al suelo, como los radiómetros de flujo neto de las sondas de Pioneer Venus. Dan un indicador de cuánto calor pierde el suelo por radiación: con cielo despejado pierde mucho, se enfría y se forma la inversión; con nubes, no.

Con los ocho sondeos de junio (2023 a 2025) que hay en `data/sondeos/`:

- Cinco mañanas despejadas, todas con inversión fuerte (5 a 12 °C en los primeros 400 m). La predicción desde arriba erra la temperatura del suelo entre 5 y 12 °C.
- Tres mañanas con nubes: dos sin inversión, donde la predicción acierta por menos de 1 °C, y una con nubes a unos 1.000 m e inversión débil (3 °C).
- El radiómetro clasifica bien el cielo en los ocho casos: entre −90 y −120 W/m² con cielo despejado y entre −8 y +7 W/m² con nubes, con el bamboleo y el ruido incluidos.
- Bajando, el termistor llega a errar 2 °C porque el cambio cerca del suelo es muy brusco (hasta 0,2 °C por metro). Medido unos segundos después de aterrizar, el error es de décimas.

Limitaciones que hay que tener presentes:

- La relación "cielo despejado → inversión" sale de solo ocho sondeos, y de la ciudad, no del lugar de lanzamiento. El viento también puede impedir la inversión aunque esté despejado.
- Las nubes se detectan en el sondeo por humedad relativa de 95 % o más en al menos 30 m, solo hasta 3.000 m.
- El cielo despejado se calcula con una fórmula de banda ancha (Brutsaert 1975). Un sensor de banda de ventana (8-14 µm) ve el cielo despejado más frío, así que la diferencia real entre despejado y nublado debería ser mayor que la simulada.
- El suelo se toma a la temperatura del aire a 0 m. No se modela el sol entrando en el campo de visión del sensor de arriba, ni que el sol o el suelo calienten la lata una vez abajo.

Casi todos los números de `cansat/sim/parametros.py` son supuestos. Hay que ir reemplazándolos con lo que midamos (prueba de la heladera para el tiempo de respuesta del termistor, prueba del auto para el Cd del paracaídas, el sensor infrarrojo apuntando al cielo una noche despejada y una nublada) y con lo que digan las bases. Cada vez que se cambie uno, anotar de dónde sale.

Lo que falta: viento y deriva, IMU, sol en el campo de visión, sumar los dos sensores infrarrojos al paquete de telemetría, y correr el firmware real contra el simulador.

## Telemetría

El formato está en [docs/telemetria.md](docs/telemetria.md). Es un borrador hasta que CONAE diga si hay uno obligatorio.
