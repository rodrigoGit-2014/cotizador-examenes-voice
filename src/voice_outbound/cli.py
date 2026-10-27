"""CLI y composition root: el único lugar que arma las implementaciones concretas."""

from pathlib import Path
from typing import Annotated

import typer

from voice_outbound import logging as vlog
from voice_outbound.config import ConfigError, Settings, cargar_settings, guardar_en_env
from voice_outbound.integrations.telnyx import assistants
from voice_outbound.integrations.telnyx.calls import TelnyxVoiceProvider
from voice_outbound.integrations.telnyx.client import TelnyxClient, TelnyxError
from voice_outbound.integrations.telnyx.conversations import TelnyxTranscriptProvider
from voice_outbound.integrations.telnyx.inference import TelnyxExtractor
from voice_outbound.io.csv_repository import CsvResultRepository
from voice_outbound.io.csv_source import CsvInvalidoError, CsvRequestSource
from voice_outbound.services.campaign import CampaignRunner, OpcionesCampana
from voice_outbound.services.prompts import variables_dinamicas

app = typer.Typer(no_args_is_help=True, help="Llamadas salientes con agente de voz IA (Telnyx).")


def _settings() -> Settings:
    try:
        return cargar_settings()
    except ConfigError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from e


def _cliente(s: Settings) -> TelnyxClient:
    return TelnyxClient(s.telnyx_api_key.get_secret_value(), base_url=s.telnyx_base_url)


@app.command()
def run(
    csv: Annotated[Path, typer.Option(help="CSV de entrada")] = Path("data/llamadas.csv"),
    salida: Annotated[Path, typer.Option(help="CSV consolidado")] = Path("consolidado.csv"),
    limite: Annotated[int | None, typer.Option(help="Máximo de llamadas")] = None,
    dry_run: Annotated[bool, typer.Option(help="Solo valida el CSV, no llama")] = False,
) -> None:
    """Llama a cada centro del CSV y agrega el resultado al consolidado."""
    vlog.configurar()
    s = _settings()
    fuente = CsvRequestSource(csv, s.ciudad_default)
    try:
        solicitudes = fuente.validar()
    except CsvInvalidoError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from e

    if dry_run:
        for i, sol in enumerate(solicitudes[:limite] if limite else solicitudes, start=1):
            typer.echo(f"[{i}] {sol.telefono_centro} → {variables_dinamicas(sol)}")
        typer.echo(f"CSV válido: {len(solicitudes)} fila(s).")
        return

    try:
        s.requerir_para_llamar()
    except ConfigError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from e

    cliente = _cliente(s)
    try:
        runner = CampaignRunner(
            fuente=fuente,
            voz=TelnyxVoiceProvider(
                cliente,
                texml_app_id=s.telnyx_texml_app_id,
                assistant_id=s.telnyx_assistant_id,
                from_number=s.telnyx_from_number,
                account_sid=s.telnyx_account_sid,
                max_duracion_seg=s.max_duracion_seg,
            ),
            transcripciones=TelnyxTranscriptProvider(cliente),
            extractor=TelnyxExtractor(cliente, s.telnyx_extraction_model),
            repositorio=CsvResultRepository(salida),
            opciones=OpcionesCampana(
                max_duracion_seg=s.max_duracion_seg,
                pausa_entre_llamadas_seg=s.pausa_entre_llamadas_seg,
                intervalo_polling_seg=s.intervalo_polling_seg,
                limite=limite,
            ),
        )
        resultados = runner.ejecutar()
    finally:
        cliente.close()
    typer.echo(f"Listo: {len(resultados)} llamada(s) agregadas a {salida}.")


@app.command("setup-assistant")
def setup_assistant() -> None:
    """Crea (o actualiza, si TELNYX_ASSISTANT_ID existe) el asistente y guarda sus IDs en .env."""
    vlog.configurar()
    s = _settings()
    cliente = _cliente(s)
    try:
        resultado = assistants.crear_o_actualizar(
            cliente,
            s.telnyx_assistant_model,
            s.telnyx_assistant_voice,
            voz_api_key_ref=s.telnyx_assistant_voice_api_key_ref,
            assistant_id=s.telnyx_assistant_id,
        )
    except TelnyxError as e:
        typer.secho(f"No se pudo configurar el asistente: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    finally:
        cliente.close()

    valores = {"TELNYX_ASSISTANT_ID": resultado.assistant_id}
    if resultado.texml_app_id:
        valores["TELNYX_TEXML_APP_ID"] = resultado.texml_app_id
    guardar_en_env(valores)
    typer.echo(f"Asistente: {resultado.assistant_id}")
    typer.echo(f"TeXML App: {resultado.texml_app_id or '(no informada, configúrala en .env)'}")


if __name__ == "__main__":
    app()
