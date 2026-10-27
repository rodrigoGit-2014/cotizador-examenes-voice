"""Orquestación: por cada solicitud → llamar → esperar → transcribir → extraer → guardar."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from voice_outbound.domain.models import (
    DatosConsulta,
    EstadoLlamada,
    ResultadoLlamada,
    SolicitudLlamada,
)
from voice_outbound.domain.ports import (
    Extractor,
    RequestSource,
    ResultRepository,
    TranscriptProvider,
    VoiceProvider,
)
from voice_outbound.logging import get_logger
from voice_outbound.services.prompts import ZONA_CHILE, variables_dinamicas

log = get_logger(__name__)

_RESUMEN_POR_ESTADO = {
    EstadoLlamada.NO_CONTESTA: "El centro no contestó la llamada.",
    EstadoLlamada.OCUPADO: "La línea del centro estaba ocupada.",
    EstadoLlamada.FALLIDA: "La llamada no se pudo completar.",
    EstadoLlamada.TIMEOUT: "La llamada superó la duración máxima y se cortó.",
    EstadoLlamada.COMPLETADA: "La llamada se completó pero no hubo conversación registrada.",
}


@dataclass(frozen=True)
class OpcionesCampana:
    max_duracion_seg: float = 600
    pausa_entre_llamadas_seg: float = 5
    intervalo_polling_seg: float = 5
    # Margen sobre max_duracion para el timbrado y la latencia del estado.
    margen_espera_seg: float = 90
    limite: int | None = None


class CampaignRunner:
    def __init__(
        self,
        fuente: RequestSource,
        voz: VoiceProvider,
        transcripciones: TranscriptProvider,
        extractor: Extractor,
        repositorio: ResultRepository,
        opciones: OpcionesCampana | None = None,
        sleep: Callable[[float], None] = time.sleep,
        reloj: Callable[[], float] = time.monotonic,
        ahora: Callable[[], datetime] = lambda: datetime.now(ZONA_CHILE),
    ):
        self._fuente = fuente
        self._voz = voz
        self._transcripciones = transcripciones
        self._extractor = extractor
        self._repo = repositorio
        self._op = opciones or OpcionesCampana()
        self._sleep = sleep
        self._reloj = reloj
        self._ahora = ahora

    def ejecutar(self) -> list[ResultadoLlamada]:
        resultados: list[ResultadoLlamada] = []
        for i, solicitud in enumerate(self._fuente.leer()):
            if self._op.limite is not None and i >= self._op.limite:
                break
            if i > 0 and self._op.pausa_entre_llamadas_seg:
                self._sleep(self._op.pausa_entre_llamadas_seg)
            resultado = self._procesar(solicitud)
            self._repo.guardar(resultado)
            resultados.append(resultado)
            log.info("fila guardada", extra={"ctx": {"centro": solicitud.centro_medico,
                                                     "estado": resultado.estado_llamada}})
        return resultados

    def _procesar(self, solicitud: SolicitudLlamada) -> ResultadoLlamada:
        inicio = self._ahora()
        call_id = ""
        try:
            call_id = self._voz.iniciar(solicitud, variables_dinamicas(solicitud, inicio))
            estado = self._esperar_fin(call_id)
            datos = self._datos(solicitud, call_id, estado)
            return ResultadoLlamada(solicitud, inicio, str(estado), datos, call_id)
        except Exception as e:  # noqa: BLE001 — ninguna fila se pierde
            log.exception("error en la llamada", extra={"ctx": {"centro": solicitud.centro_medico}})
            motivo = f"{type(e).__name__}: {e}"
            return ResultadoLlamada(
                solicitud, inicio, f"error: {motivo}", DatosConsulta(resumen=f"Error: {motivo}"),
                call_id,
            )

    def _esperar_fin(self, call_id: str) -> EstadoLlamada:
        limite = self._reloj() + self._op.max_duracion_seg + self._op.margen_espera_seg
        while True:
            estado = self._voz.estado(call_id)
            if estado is not None:
                return estado
            if self._reloj() >= limite:
                log.warning("timeout, colgando", extra={"ctx": {"call_id": call_id}})
                try:
                    self._voz.colgar(call_id)
                except Exception:  # noqa: BLE001
                    log.exception("no se pudo colgar", extra={"ctx": {"call_id": call_id}})
                return EstadoLlamada.TIMEOUT
            self._sleep(self._op.intervalo_polling_seg)

    def _datos(
        self, solicitud: SolicitudLlamada, call_id: str, estado: EstadoLlamada
    ) -> DatosConsulta:
        if estado in (EstadoLlamada.COMPLETADA, EstadoLlamada.TIMEOUT):
            mensajes = self._transcripciones.obtener(call_id)
            if any(m.rol == "centro" for m in mensajes):
                return self._extractor.extraer(solicitud, mensajes)
        return DatosConsulta(resumen=_RESUMEN_POR_ESTADO[estado])
