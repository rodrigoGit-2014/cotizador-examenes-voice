from conftest import (
    FakeExtractor,
    FakeRepo,
    FakeSource,
    FakeTranscripts,
    FakeVoice,
    RelojFalso,
    solicitud,
)

from voice_outbound.domain.models import NO_INFORMADO, EstadoLlamada, Mensaje
from voice_outbound.services.campaign import CampaignRunner, OpcionesCampana

CONVERSACION = [
    Mensaje("centro", "Clínica Ejemplo, buenos días."),
    Mensaje("asistente", "Hola, ¿realizan ecografía abdominal?"),
    Mensaje("centro", "Sí, cuesta 40 mil."),
]


def _runner(solicitudes, voz, mensajes=CONVERSACION, **opciones):
    reloj = RelojFalso()
    repo, extractor = FakeRepo(), FakeExtractor()
    runner = CampaignRunner(
        FakeSource(solicitudes),
        voz,
        FakeTranscripts(mensajes),
        extractor,
        repo,
        OpcionesCampana(intervalo_polling_seg=5, pausa_entre_llamadas_seg=2, **opciones),
        sleep=reloj.sleep,
        reloj=reloj,
    )
    return runner, repo, extractor, reloj


def test_flujo_completo_con_estados_mixtos():
    sols = [
        solicitud(telefono_centro="+56211111111"),
        solicitud(telefono_centro="+56222222222"),
        solicitud(telefono_centro="+56233333333"),
    ]
    voz = FakeVoice({
        "+56211111111": [None, None, EstadoLlamada.COMPLETADA],
        "+56222222222": [EstadoLlamada.NO_CONTESTA],
        "+56233333333": RuntimeError("HTTP 422"),
    })
    runner, repo, extractor, _ = _runner(sols, voz)

    resultados = runner.ejecutar()

    assert [r.estado_llamada for r in resultados] == ["completada", "no contesta",
                                                      "error: RuntimeError: HTTP 422"]
    assert repo.guardados == resultados
    assert resultados[0].datos.valor == "$40.000"
    assert resultados[1].datos.valor == NO_INFORMADO
    assert "no contestó" in resultados[1].datos.resumen
    assert resultados[2].datos.realiza_examen == NO_INFORMADO
    assert extractor.llamadas == 1
    assert voz.iniciadas[0][1]["nombre_paciente"] == "María González"


def test_completada_sin_mensajes_del_centro_no_extrae():
    voz = FakeVoice({"+56222222222": [EstadoLlamada.COMPLETADA]})
    runner, _, extractor, _ = _runner([solicitud()], voz, mensajes=[Mensaje("asistente", "Hola")])

    (resultado,) = runner.ejecutar()

    assert extractor.llamadas == 0
    assert resultado.datos.valor == NO_INFORMADO
    assert "no hubo conversación" in resultado.datos.resumen


def test_timeout_cuelga_y_marca_estado():
    voz = FakeVoice({"+56222222222": [None]})
    runner, _, _, reloj = _runner([solicitud()], voz, max_duracion_seg=60, margen_espera_seg=0)

    (resultado,) = runner.ejecutar()

    assert resultado.estado_llamada == EstadoLlamada.TIMEOUT
    assert voz.colgadas == ["call-+56222222222"]
    assert reloj.t >= 60


def test_limite_y_pausa_entre_llamadas():
    sols = [solicitud(telefono_centro=f"+5621111111{i}") for i in range(3)]
    voz = FakeVoice({s.telefono_centro: [EstadoLlamada.OCUPADO] for s in sols})
    runner, repo, _, reloj = _runner(sols, voz, limite=2)

    runner.ejecutar()

    assert len(repo.guardados) == 2
    assert reloj.t == 2  # una sola pausa entre las dos llamadas
