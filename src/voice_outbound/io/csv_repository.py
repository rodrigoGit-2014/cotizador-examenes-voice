"""Agrega resultados a `consolidado.csv`, una fila por llamada."""

import csv
from pathlib import Path

from voice_outbound.domain.models import ResultadoLlamada


class CsvResultRepository:
    def __init__(self, ruta: Path):
        self._ruta = ruta

    def guardar(self, resultado: ResultadoLlamada) -> None:
        nuevo = not self._ruta.exists() or self._ruta.stat().st_size == 0
        # BOM solo al crear el archivo, para que Excel lo abra como UTF-8.
        with self._ruta.open("a", encoding="utf-8-sig" if nuevo else "utf-8", newline="") as f:
            escritor = csv.DictWriter(f, fieldnames=ResultadoLlamada.columnas())
            if nuevo:
                escritor.writeheader()
            escritor.writerow(resultado.como_fila())
            f.flush()
