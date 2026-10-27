"""Llamadas salientes con AI Assistant vía TeXML (`/texml/ai_calls`) y su estado."""

from voice_outbound.domain.models import EstadoLlamada, SolicitudLlamada
from voice_outbound.integrations.telnyx.client import TelnyxClient, TelnyxNotFound
from voice_outbound.logging import get_logger

log = get_logger(__name__)

# Estados TeXML (compatibles con Twilio). Los no listados (queued, initiated, ringing,
# in-progress) significan que la llamada sigue en curso.
_ESTADOS_FINALES = {
    "completed": EstadoLlamada.COMPLETADA,
    "busy": EstadoLlamada.OCUPADO,
    "no-answer": EstadoLlamada.NO_CONTESTA,
    "failed": EstadoLlamada.FALLIDA,
    "canceled": EstadoLlamada.FALLIDA,
}


def mapear_estado(status: str | None) -> EstadoLlamada | None:
    return _ESTADOS_FINALES.get((status or "").lower())


class TelnyxVoiceProvider:
    def __init__(
        self,
        client: TelnyxClient,
        texml_app_id: str,
        assistant_id: str,
        from_number: str,
        account_sid: str | None = None,
        max_duracion_seg: int = 600,
        timeout_timbrado_seg: int = 40,
    ):
        self._client = client
        self._app_id = texml_app_id
        self._assistant_id = assistant_id
        self._from = from_number
        self._account_sid = account_sid
        self._max_duracion = max_duracion_seg
        self._timeout_timbrado = timeout_timbrado_seg

    @property
    def account_sid(self) -> str:
        # El account SID de TeXML es el organization_id de la cuenta.
        if not self._account_sid:
            self._account_sid = self._client.get("/whoami")["data"]["organization_id"]
        return self._account_sid

    def iniciar(self, solicitud: SolicitudLlamada, variables: dict[str, str]) -> str:
        respuesta = self._client.post(
            f"/texml/ai_calls/{self._app_id}",
            json={
                "From": self._from,
                "To": solicitud.telefono_centro,
                "AIAssistantId": self._assistant_id,
                "AIAssistantDynamicVariables": variables,
                "Timeout": self._timeout_timbrado,
                "TimeLimit": self._max_duracion,
            },
        )
        datos = respuesta.get("data", respuesta)
        call_sid = datos.get("call_sid") or datos.get("sid")
        if not call_sid:
            raise ValueError(f"respuesta de ai_calls sin call_sid: {respuesta}")
        log.info("llamada iniciada", extra={"ctx": {"call_sid": call_sid,
                                                    "to": solicitud.telefono_centro}})
        return call_sid

    def estado(self, call_id: str) -> EstadoLlamada | None:
        try:
            llamada = self._client.get(f"/texml/Accounts/{self.account_sid}/Calls/{call_id}")
        except TelnyxNotFound:
            # El endpoint es eventualmente consistente: recién iniciada puede no existir aún.
            return None
        return mapear_estado(llamada.get("status"))

    def colgar(self, call_id: str) -> None:
        self._client.post(
            f"/texml/Accounts/{self.account_sid}/Calls/{call_id}",
            data={"Status": "completed"},
        )
