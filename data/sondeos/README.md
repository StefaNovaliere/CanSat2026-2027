# Radiosondeos

Acá van los sondeos de Córdoba Aeropuerto (estación 87344, SACO) bajados de la página de la Universidad de Wyoming (Upper Air Soundings), en formato de texto (TEXT:LIST).

- Un archivo por mes, por ejemplo `87344_2025_06.txt`.
- Bajar todos los horarios disponibles (00Z y 12Z) para comparar noche y mañana. 12Z son las 9 de la mañana nuestras.
- No editar los archivos a mano. Si hace falta limpiar algo, que lo haga el script.

Anotar abajo de dónde y cuándo se bajó cada archivo, que lo vamos a tener que citar en el PDR.

Para analizarlos:

```
python -m cansat.sondeos data/sondeos/*.txt --capa 400 --grafico salidas/sondeos.png --csv salidas/sondeos.csv
```

Ojo: SACO está al lado de la ciudad, no en el lugar de lanzamiento. Sirve como referencia de cómo se comporta la capa cerca del suelo, no como dato exacto del sitio.

## Archivos

| Archivo | Período | Fecha de descarga | Quién |
| --- | --- | --- | --- |
| | | | |
