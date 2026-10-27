from datetime import UTC, datetime

from conftest import solicitud

from voice_outbound.services.prompts import (
    ZONA_CHILE,
    cargar_prompt,
    render,
    saludo,
    variables_dinamicas,
)


def test_saludo_segun_hora_de_chile():
    assert saludo(datetime(2026, 10, 26, 9, 0, tzinfo=ZONA_CHILE)) == "buenos días"
    assert saludo(datetime(2026, 10, 26, 15, 0, tzinfo=ZONA_CHILE)) == "buenas tardes"
    # 14:00 UTC son las 11:00 en Chile (horario de verano, UTC-3)
    assert saludo(datetime(2026, 10, 26, 14, 0, tzinfo=UTC)) == "buenos días"


def test_render_reemplaza_y_deja_desconocidas():
    assert render("Hola {{ nombre }}, {{otra}}", {"nombre": "Ana"}) == "Hola Ana, {{otra}}"


def test_variables_dinamicas_cubren_el_prompt_del_agente(ahora):
    variables = variables_dinamicas(solicitud(), ahora)
    renderizado = render(cargar_prompt("agente_consulta_examen"), variables)

    assert "{{" not in renderizado
    assert variables["saludo"] == "buenos días"
