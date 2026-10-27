import pytest

from voice_outbound.io.csv_source import CsvInvalidoError, CsvRequestSource

CABECERA = "nombre_paciente,examen,prevision,centro_medico,telefono_centro,ciudad\n"


def _fuente(tmp_path, contenido):
    ruta = tmp_path / "llamadas.csv"
    ruta.write_text(contenido, encoding="utf-8")
    return CsvRequestSource(ruta, ciudad_default="Santiago")


def test_lee_filas_normaliza_telefono_y_ciudad_default(tmp_path):
    fuente = _fuente(tmp_path, CABECERA + "Ana,ecografía,Fonasa,Centro A,+56 2 2222 2222,\n\n")

    (sol,) = list(fuente.leer())

    assert sol.telefono_centro == "+56222222222"
    assert sol.ciudad == "Santiago"


def test_columna_ciudad_es_opcional(tmp_path):
    fuente = _fuente(
        tmp_path,
        "nombre_paciente,examen,prevision,centro_medico,telefono_centro\n"
        "Ana,ecografía,Fonasa,Centro A,+56912345678\n",
    )

    assert next(fuente.leer()).ciudad == "Santiago"


def test_reporta_todas_las_filas_invalidas(tmp_path):
    fuente = _fuente(
        tmp_path,
        CABECERA
        + "Ana,ecografía,Fonasa,Centro A,+1312555000,\n"
        + ",ecografía,Fonasa,Centro B,+56222222222,\n",
    )

    with pytest.raises(CsvInvalidoError) as e:
        fuente.validar()
    assert "fila 2: telefono_centro" in str(e.value)
    assert "fila 3: nombre_paciente" in str(e.value)


def test_columnas_faltantes(tmp_path):
    with pytest.raises(CsvInvalidoError, match="telefono_centro"):
        _fuente(tmp_path, "nombre_paciente,examen,prevision,centro_medico\n").validar()
