"""Modelos del dominio. No dependen de Telnyx ni de CSV."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

NO_INFORMADO = "no informado"
_E164_CHILE = re.compile(r"^\+56\d{8,9}$")


class EstadoLlamada(StrEnum):
    COMPLETADA = "completada"
    NO_CONTESTA = "no contesta"
    OCUPADO = "ocupado"
    FALLIDA = "fallida"
    TIMEOUT = "timeout"


class SolicitudLlamada(BaseModel):
    """Una fila de `llamadas.csv`."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    nombre_paciente: str
    examen: str
    prevision: str
    centro_medico: str
    telefono_centro: str
    ciudad: str

    @field_validator("telefono_centro", mode="before")
    @classmethod
    def _normalizar_telefono(cls, v: str) -> str:
        telefono = re.sub(r"[\s\-()]", "", str(v))
        if not _E164_CHILE.match(telefono):
            raise ValueError(f"teléfono '{v}' no está en formato E.164 chileno (+56…)")
        return telefono

    @field_validator("nombre_paciente", "examen", "prevision", "centro_medico", "ciudad")
    @classmethod
    def _no_vacio(cls, v: str) -> str:
        if not v:
            raise ValueError("no puede estar vacío")
        return v


class DatosConsulta(BaseModel):
    """Lo que el centro informó. Fuente única del esquema del CSV y del JSON de extracción."""

    realiza_examen: str = NO_INFORMADO
    valor: str = NO_INFORMADO
    acepta_prevision: str = NO_INFORMADO
    disponibilidad: str = NO_INFORMADO
    preparacion: str = NO_INFORMADO
    requiere_orden_medica: str = NO_INFORMADO
    derivacion: str = NO_INFORMADO
    resumen: str = NO_INFORMADO

    @field_validator("*", mode="before")
    @classmethod
    def _vacio_es_no_informado(cls, v: object) -> str:
        if v is None or (isinstance(v, str) and not v.strip()):
            return NO_INFORMADO
        return str(v).strip()


@dataclass(frozen=True)
class Mensaje:
    rol: str  # "asistente" | "centro"
    texto: str


@dataclass(frozen=True)
class ResultadoLlamada:
    solicitud: SolicitudLlamada
    fecha_hora: datetime
    estado_llamada: str  # un EstadoLlamada o "error: <motivo>"
    datos: DatosConsulta
    call_id: str = ""

    @staticmethod
    def columnas() -> list[str]:
        return [
            "fecha_hora",
            *SolicitudLlamada.model_fields,
            "estado_llamada",
            *DatosConsulta.model_fields,
            "call_id",
        ]

    def como_fila(self) -> dict[str, str]:
        return {
            "fecha_hora": self.fecha_hora.isoformat(timespec="seconds"),
            **self.solicitud.model_dump(),
            "estado_llamada": self.estado_llamada,
            **self.datos.model_dump(),
            "call_id": self.call_id,
        }
