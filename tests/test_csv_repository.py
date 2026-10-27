import csv

from conftest import solicitud

from voice_outbound.domain.models import DatosConsulta, ResultadoLlamada
from voice_outbound.io.csv_repository import CsvResultRepository


def test_cabecera_una_vez_bom_y_append(tmp_path, ahora):
    ruta = tmp_path / "consolidado.csv"
    repo = CsvResultRepository(ruta)
    for valor in ("$10.000", "$20.000"):
        repo.guardar(ResultadoLlamada(solicitud(), ahora, "completada", DatosConsulta(valor=valor)))

    crudo = ruta.read_bytes()
    assert crudo.startswith(b"\xef\xbb\xbf")
    assert crudo.count(b"\xef\xbb\xbf") == 1
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    assert [f["valor"] for f in filas] == ["$10.000", "$20.000"]
    assert filas[0]["preparacion"] == "no informado"
    assert list(filas[0]) == ResultadoLlamada.columnas()
