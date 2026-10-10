# Radiosondeos

Acá van los sondeos de Córdoba Aeropuerto (estación 87344, SACO) bajados de la página de la Universidad de Wyoming.

- La página nueva da un sondeo por consulta. Se baja en CSV y se deja con el nombre que trae, por ejemplo `2025061512-87344.csv` (fecha, hora UTC y estación): de ahí el script saca la fecha.
- Se baja desde el formulario de la página (weather.uwyo.edu, Upper Air, Soundings): fecha, hora 12Z, estación 87344 y CSV como tipo de salida.
- Córdoba lanza sobre todo a las 12Z, que son las 9 de la mañana nuestras. Si una fecha no tiene datos, ese día no hubo lanzamiento.
- Si la página se cae después de varias consultas seguidas, esperar un rato entre una y otra.
- No editar los archivos a mano. Si hace falta limpiar algo, que lo haga el script.

Anotar abajo de dónde y cuándo se bajó cada archivo, que lo vamos a tener que citar en el PDR.

Para analizarlos:

```
python -m cansat.sondeos data/sondeos/*.csv --capa 400 --grafico salidas/sondeos.png --csv salidas/sondeos.csv
```

Ojo: SACO está al lado de la ciudad, no en el lugar de lanzamiento. Sirve como referencia de cómo se comporta la capa cerca del suelo, no como dato exacto del sitio.

## Archivos

| Archivo | Sondeo | Fecha de descarga | Quién |
| --- | --- | --- | --- |
| `2025060312-87344.csv` | 03/06/2025 12Z (lanzado 11:36 UTC) | 09/10/2026 | |
| `2025060812-87344.csv` | 08/06/2025 12Z (lanzado 11:42 UTC) | 09/10/2026 | |
| `2025061512-87344.csv` | 15/06/2025 12Z (lanzado 11:38 UTC) | 09/10/2026 | |
| `2025062112-87344.csv` | 21/06/2025 12Z (lanzado 11:41 UTC) | 09/10/2026 | |
