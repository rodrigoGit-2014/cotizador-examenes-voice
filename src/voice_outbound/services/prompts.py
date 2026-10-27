"""Plantillas de prompts y variables dinámicas de cada llamada."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from voice_outbound.config import PROMPTS_DIR
from voice_outbound.domain.models import SolicitudLlamada

ZONA_CHILE = ZoneInfo("America/Santiago")
_VARIABLE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def cargar_prompt(nombre: str) -> str:
    return (PROMPTS_DIR / f"{nombre}.md").read_text(encoding="utf-8")


def render(plantilla: str, variables: dict[str, str]) -> str:
    """Reemplaza `{{variable}}`. Las desconocidas quedan tal cual."""
    return _VARIABLE.sub(lambda m: str(variables.get(m.group(1), m.group(0))), plantilla)


def saludo(ahora: datetime | None = None) -> str:
    hora = (ahora or datetime.now(ZONA_CHILE)).astimezone(ZONA_CHILE).hour
    return "buenos días" if 5 <= hora < 12 else "buenas tardes"


def variables_dinamicas(
    solicitud: SolicitudLlamada, ahora: datetime | None = None
) -> dict[str, str]:
    return {
        "nombre_paciente": solicitud.nombre_paciente,
        "examen": solicitud.examen,
        "prevision": solicitud.prevision,
        "centro_medico": solicitud.centro_medico,
        "ciudad": solicitud.ciudad,
        "saludo": saludo(ahora),
    }
