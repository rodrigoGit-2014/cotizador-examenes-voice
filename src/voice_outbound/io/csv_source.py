"""Lee y valida `llamadas.csv`."""

import csv
from collections.abc import Iterator
from pathlib import Path

from pydantic import ValidationError

from voice_outbound.domain.models import SolicitudLlamada

COLUMNAS_OBLIGATORIAS = (
    "nombre_paciente", "examen", "prevision", "centro_medico", "telefono_centro",
)


class CsvInvalidoError(ValueError):
    pass


class CsvRequestSource:
    def __init__(self, ruta: Path, ciudad_default: str):
        self._ruta = ruta
        self._ciudad_default = ciudad_default

    def leer(self) -> Iterator[SolicitudLlamada]:
        """Valida el archivo completo antes de entregar la primera fila."""
        return iter(self.validar())

    def validar(self) -> list[SolicitudLlamada]:
        if not self._ruta.exists():
            raise CsvInvalidoError(f"No existe el archivo {self._ruta}")
        with self._ruta.open(encoding="utf-8-sig", newline="") as f:
            lector = csv.DictReader(f)
            faltantes = [c for c in COLUMNAS_OBLIGATORIAS if c not in (lector.fieldnames or [])]
            if faltantes:
                raise CsvInvalidoError(f"Faltan columnas en {self._ruta}: {', '.join(faltantes)}")
            solicitudes, errores = [], []
            for n, fila in enumerate(lector, start=2):
                if not any((v or "").strip() for v in fila.values()):
                    continue
                datos = {k: (v or "").strip() for k, v in fila.items() if k}
                datos["ciudad"] = datos.get("ciudad") or self._ciudad_default
                try:
                    solicitudes.append(SolicitudLlamada.model_validate(datos))
                except ValidationError as e:
                    detalle = "; ".join(f"{err['loc'][0]}: {err['msg']}" for err in e.errors())
                    errores.append(f"fila {n}: {detalle}")
        if errores:
            raise CsvInvalidoError("CSV inválido:\n  " + "\n  ".join(errores))
        return solicitudes
