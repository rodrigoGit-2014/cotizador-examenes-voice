"""Transcripción de la llamada desde las conversaciones del AI Assistant."""

import time

from voice_outbound.domain.models import Mensaje
from voice_outbound.integrations.telnyx.client import TelnyxClient
from voice_outbound.logging import get_logger

log = get_logger(__name__)

_ROLES = {"assistant": "asistente", "user": "centro"}


class TelnyxTranscriptProvider:
    def __init__(self, client: TelnyxClient, intentos: int = 6, espera_seg: float = 5.0):
        self._client = client
        self._intentos = intentos
        self._espera = espera_seg

    def obtener(self, call_id: str) -> list[Mensaje]:
        conversacion_id = self._buscar_conversacion(call_id)
        if not conversacion_id:
            log.warning("sin conversación", extra={"ctx": {"call_id": call_id}})
            return []
        return self._mensajes(conversacion_id)

    def _buscar_conversacion(self, call_id: str) -> str | None:
        # La conversación aparece unos segundos después de colgar.
        for intento in range(self._intentos):
            datos = self._client.get(
                "/ai/conversations", params={"metadata->call_control_id": f"eq.{call_id}"}
            )["data"]
            if datos:
                return datos[0]["id"]
            if intento < self._intentos - 1:
                time.sleep(self._espera)
        return None

    def _mensajes(self, conversacion_id: str) -> list[Mensaje]:
        crudos: list[dict] = []
        pagina = 1
        while True:
            respuesta = self._client.get(
                f"/ai/conversations/{conversacion_id}/messages",
                params={"page[number]": pagina, "page[size]": 100},
            )
            crudos.extend(respuesta["data"])
            total_paginas = (respuesta.get("meta") or {}).get("total_pages", 1)
            if pagina >= total_paginas:
                break
            pagina += 1
        # La API devuelve primero lo más reciente.
        crudos.sort(key=lambda m: m.get("sent_at") or m.get("created_at") or "")
        return [
            Mensaje(rol=_ROLES[m["role"]], texto=m["text"].strip())
            for m in crudos
            if m.get("role") in _ROLES and (m.get("text") or "").strip()
        ]
