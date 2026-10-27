"""Interfaces que la orquestación usa. Las implementaciones viven en `integrations/` e `io/`."""

from collections.abc import Iterable
from typing import Protocol

from voice_outbound.domain.models import (
    DatosConsulta,
    EstadoLlamada,
    Mensaje,
    ResultadoLlamada,
    SolicitudLlamada,
)


class VoiceProvider(Protocol):
    def iniciar(self, solicitud: SolicitudLlamada, variables: dict[str, str]) -> str:
        """Inicia la llamada y devuelve su ID."""
        ...

    def estado(self, call_id: str) -> EstadoLlamada | None:
        """Estado final de la llamada, o None si sigue en curso."""
        ...

    def colgar(self, call_id: str) -> None: ...


class TranscriptProvider(Protocol):
    def obtener(self, call_id: str) -> list[Mensaje]:
        """Mensajes en orden cronológico. Lista vacía si no hubo conversación."""
        ...


class Extractor(Protocol):
    def extraer(self, solicitud: SolicitudLlamada, mensajes: list[Mensaje]) -> DatosConsulta: ...


class ResultRepository(Protocol):
    def guardar(self, resultado: ResultadoLlamada) -> None: ...


class RequestSource(Protocol):
    def leer(self) -> Iterable[SolicitudLlamada]: ...
