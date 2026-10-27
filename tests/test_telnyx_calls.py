import json

import httpx
import pytest
import respx
from conftest import solicitud

from voice_outbound.domain.models import EstadoLlamada, Mensaje
from voice_outbound.integrations.telnyx.calls import TelnyxVoiceProvider, mapear_estado
from voice_outbound.integrations.telnyx.client import TelnyxClient, TelnyxError
from voice_outbound.integrations.telnyx.conversations import TelnyxTranscriptProvider
from voice_outbound.integrations.telnyx.inference import ExtraccionError, parsear_datos

BASE = "https://api.telnyx.com/v2"
SID = "v3:abc123"
ACC = "org-1"


@pytest.fixture
def cliente():
    c = TelnyxClient("KEY", base_url=BASE, backoff_seg=0)
    yield c
    c.close()


def _voz(cliente):
    return TelnyxVoiceProvider(cliente, "app-1", "assistant-1", "+56200000000", account_sid=ACC)


@pytest.mark.parametrize(
    ("status", "esperado"),
    [
        ("completed", EstadoLlamada.COMPLETADA),
        ("busy", EstadoLlamada.OCUPADO),
        ("no-answer", EstadoLlamada.NO_CONTESTA),
        ("failed", EstadoLlamada.FALLIDA),
        ("canceled", EstadoLlamada.FALLIDA),
        ("ringing", None),
        ("in-progress", None),
        ("queued", None),
        (None, None),
    ],
)
def test_mapear_estado(status, esperado):
    assert mapear_estado(status) == esperado


@respx.mock
def test_iniciar_envia_variables_y_devuelve_call_sid(cliente):
    ruta = respx.post(f"{BASE}/texml/ai_calls/app-1").mock(
        return_value=httpx.Response(200, json={"call_sid": SID, "status": "queued"})
    )

    assert _voz(cliente).iniciar(solicitud(), {"examen": "eco"}) == SID
    cuerpo = json.loads(ruta.calls.last.request.content)
    assert cuerpo["To"] == "+56222222222"
    assert cuerpo["AIAssistantId"] == "assistant-1"
    assert cuerpo["AIAssistantDynamicVariables"] == {"examen": "eco"}
    assert ruta.calls.last.request.headers["Authorization"] == "Bearer KEY"


@respx.mock
def test_iniciar_no_reintenta_post_con_5xx(cliente):
    ruta = respx.post(f"{BASE}/texml/ai_calls/app-1").mock(return_value=httpx.Response(503))

    with pytest.raises(TelnyxError):
        _voz(cliente).iniciar(solicitud(), {})
    assert ruta.call_count == 1


@respx.mock
def test_estado_404_es_en_curso_y_get_reintenta_5xx(cliente):
    url = f"{BASE}/texml/Accounts/{ACC}/Calls/{SID}"
    respx.get(url).mock(
        side_effect=[
            httpx.Response(404, json={"errors": [{"detail": "Resource not found"}]}),
            httpx.Response(502),
            httpx.Response(200, json={"sid": SID, "status": "no-answer"}),
        ]
    )
    voz = _voz(cliente)

    assert voz.estado(SID) is None
    assert voz.estado(SID) == EstadoLlamada.NO_CONTESTA


@respx.mock
def test_account_sid_desde_whoami(cliente):
    respx.get(f"{BASE}/whoami").mock(
        return_value=httpx.Response(200, json={"data": {"organization_id": "org-9"}})
    )
    voz = TelnyxVoiceProvider(cliente, "app-1", "assistant-1", "+56200000000")

    assert voz.account_sid == "org-9"


@respx.mock
def test_transcripcion_pagina_y_ordena(cliente):
    respx.get(f"{BASE}/ai/conversations").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "conv-1"}]})
    )

    def msg(rol, texto, t):
        return {"role": rol, "text": texto, "sent_at": f"2026-10-25T20:40:{t:02d}Z"}

    respx.get(f"{BASE}/ai/conversations/conv-1/messages").mock(
        side_effect=[
            httpx.Response(200, json={
                "data": [msg("tool", '{"ok":1}', 9), msg("assistant", "Gracias", 8),
                         msg("user", "Sí", 5)],
                "meta": {"total_pages": 2},
            }),
            httpx.Response(200, json={"data": [msg("assistant", "", 3), msg("user", "Aló", 1)],
                                      "meta": {"total_pages": 2}}),
        ]
    )

    mensajes = TelnyxTranscriptProvider(cliente, intentos=1).obtener(SID)

    assert mensajes == [Mensaje("centro", "Aló"), Mensaje("centro", "Sí"),
                        Mensaje("asistente", "Gracias")]


def test_parsear_datos_completa_faltantes_y_acepta_fences():
    datos = parsear_datos('```json\n{"valor": "$40.000", "preparacion": "", "otro": 1}\n```')

    assert datos.valor == "$40.000"
    assert datos.preparacion == "no informado"
    assert datos.disponibilidad == "no informado"


def test_parsear_datos_invalido():
    with pytest.raises(ExtraccionError):
        parsear_datos("no es json")
