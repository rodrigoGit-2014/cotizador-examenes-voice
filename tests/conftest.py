from datetime import datetime

import pytest

from voice_outbound.domain.models import DatosConsulta, EstadoLlamada, Mensaje, SolicitudLlamada
from voice_outbound.services.prompts import ZONA_CHILE


def solicitud(**cambios) -> SolicitudLlamada:
    base = {
        "nombre_paciente": "María González",
        "examen": "ecografía abdominal",
        "prevision": "Fonasa",
        "centro_medico": "Clínica Ejemplo",
        "telefono_centro": "+56222222222",
        "ciudad": "Santiago",
    }
    return SolicitudLlamada(**{**base, **cambios})


class FakeSource:
    def __init__(self, solicitudes):
        self.solicitudes = solicitudes

    def leer(self):
        return iter(self.solicitudes)


class FakeVoice:
    """Cada teléfono devuelve una secuencia de estados (None = en curso) o una excepción."""

    def __init__(self, guion: dict[str, list]):
        self.guion = guion
        self.iniciadas: list[tuple[str, dict]] = []
        self.colgadas: list[str] = []

    def iniciar(self, sol, variables):
        accion = self.guion[sol.telefono_centro]
        if isinstance(accion, Exception):
            raise accion
        self.iniciadas.append((sol.telefono_centro, variables))
        return f"call-{sol.telefono_centro}"

    def estado(self, call_id):
        estados = self.guion[call_id.removeprefix("call-")]
        return estados.pop(0) if len(estados) > 1 else estados[0]

    def colgar(self, call_id):
        self.colgadas.append(call_id)


class FakeTranscripts:
    def __init__(self, mensajes: list[Mensaje]):
        self.mensajes = mensajes

    def obtener(self, call_id):
        return self.mensajes


class FakeExtractor:
    def __init__(self):
        self.llamadas = 0

    def extraer(self, sol, mensajes):
        self.llamadas += 1
        return DatosConsulta(realiza_examen="sí", valor="$40.000", resumen="Lo realizan.")


class FakeRepo:
    def __init__(self):
        self.guardados = []

    def guardar(self, resultado):
        self.guardados.append(resultado)


class RelojFalso:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seg):
        self.t += seg


@pytest.fixture
def ahora():
    return datetime(2026, 10, 26, 10, 0, tzinfo=ZONA_CHILE)


__all__ = ["EstadoLlamada", "solicitud"]
