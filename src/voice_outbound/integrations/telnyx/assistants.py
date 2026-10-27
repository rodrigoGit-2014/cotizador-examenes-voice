"""Crea o actualiza el AI Assistant a partir de `prompts/`."""

from dataclasses import dataclass

from voice_outbound.integrations.telnyx.client import TelnyxClient
from voice_outbound.services.prompts import cargar_prompt

NOMBRE_ASISTENTE = "Consulta de exámenes (saliente)"
VARIABLES_DINAMICAS = {
    "nombre_paciente": "el paciente",
    "examen": "el examen",
    "prevision": "no informada",
    "centro_medico": "el centro médico",
    "ciudad": "Santiago",
    "saludo": "buenos días",
}


@dataclass(frozen=True)
class AsistenteConfigurado:
    assistant_id: str
    texml_app_id: str | None


def _definicion(modelo: str, voz: str, voz_api_key_ref: str | None) -> dict:
    # Proveedores externos (p. ej. ElevenLabs) necesitan la referencia a su clave.
    voz_config = {"voice": voz, **({"api_key_ref": voz_api_key_ref} if voz_api_key_ref else {})}
    return {
        "name": NOMBRE_ASISTENTE,
        "instructions": cargar_prompt("agente_consulta_examen"),
        "model": modelo,
        # Sin saludo: el agente espera que el centro conteste y luego habla.
        "greeting": "",
        "dynamic_variables": VARIABLES_DINAMICAS,
        "enabled_features": ["telephony"],
        "tools": [
            {
                "type": "hangup",
                "hangup": {"description": "Cuelga la llamada cuando la conversación terminó."},
            }
        ],
        "voice_settings": voz_config,
        "transcription": {"model": "deepgram/flux", "language": "es"},
    }


def crear_o_actualizar(
    client: TelnyxClient,
    modelo: str,
    voz: str,
    voz_api_key_ref: str | None = None,
    assistant_id: str | None = None,
) -> AsistenteConfigurado:
    definicion = _definicion(modelo, voz, voz_api_key_ref)
    if assistant_id:
        asistente = client.post(f"/ai/assistants/{assistant_id}", json=definicion)
    else:
        asistente = client.post("/ai/assistants", json=definicion)
    asistente = asistente.get("data", asistente)
    telefonia = asistente.get("telephony_settings") or {}
    return AsistenteConfigurado(
        assistant_id=asistente["id"], texml_app_id=telefonia.get("default_texml_app_id")
    )
