"""Extracción de datos de la transcripción con el LLM de Telnyx (API compatible con OpenAI)."""

import json

from pydantic import ValidationError

from voice_outbound.domain.models import DatosConsulta, Mensaje, SolicitudLlamada
from voice_outbound.integrations.telnyx.client import TelnyxClient
from voice_outbound.logging import get_logger
from voice_outbound.services.prompts import cargar_prompt, render

log = get_logger(__name__)


class ExtraccionError(RuntimeError):
    pass


def formatear_transcripcion(mensajes: list[Mensaje]) -> str:
    return "\n".join(f"{m.rol}: {m.texto}" for m in mensajes)


class TelnyxExtractor:
    def __init__(self, client: TelnyxClient, modelo: str):
        self._client = client
        self._modelo = modelo
        self._plantilla = cargar_prompt("extraccion")

    def extraer(self, solicitud: SolicitudLlamada, mensajes: list[Mensaje]) -> DatosConsulta:
        prompt = render(
            self._plantilla,
            {
                **solicitud.model_dump(),
                "campos": json.dumps(dict.fromkeys(DatosConsulta.model_fields, "string")),
                "transcripcion": formatear_transcripcion(mensajes),
            },
        )
        respuesta = self._client.post(
            "/ai/chat/completions",
            json={
                "model": self._modelo,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0,
                "max_tokens": 2000,
            },
        )
        contenido = respuesta["choices"][0]["message"].get("content") or ""
        return parsear_datos(contenido)


def parsear_datos(contenido: str) -> DatosConsulta:
    texto = contenido.strip()
    # Algunos modelos envuelven el JSON en ```json … ``` aunque se pida json_object.
    if texto.startswith("```"):
        texto = texto.strip("`").removeprefix("json").strip()
    try:
        crudo = json.loads(texto)
        return DatosConsulta.model_validate(
            {k: v for k, v in crudo.items() if k in DatosConsulta.model_fields}
        )
    except (ValueError, AttributeError, ValidationError) as e:
        raise ExtraccionError(f"JSON de extracción inválido: {contenido[:200]!r}") from e
