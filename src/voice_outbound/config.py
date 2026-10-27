"""Configuración leída desde variables de entorno y `.env`, validada al arrancar."""

from pathlib import Path

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"
PROMPTS_DIR = PROJECT_ROOT / "prompts"


class ConfigError(RuntimeError):
    """Falta una variable obligatoria o tiene un valor inválido."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    telnyx_api_key: SecretStr = Field(min_length=1)
    telnyx_base_url: str = "https://api.telnyx.com/v2"
    telnyx_assistant_id: str | None = None
    telnyx_texml_app_id: str | None = None
    telnyx_from_number: str | None = None
    telnyx_account_sid: str | None = None

    telnyx_assistant_model: str = "moonshotai/Kimi-K2.6"
    telnyx_assistant_voice: str = "Azure.es-CL-CatalinaNeural"
    telnyx_assistant_voice_api_key_ref: str | None = None
    telnyx_extraction_model: str = "zai-org/GLM-5.3-Flash"

    max_duracion_seg: int = Field(600, gt=0)
    pausa_entre_llamadas_seg: float = Field(5, ge=0)
    intervalo_polling_seg: float = Field(5, gt=0)
    ciudad_default: str = "Santiago"

    @field_validator(
        "telnyx_assistant_id",
        "telnyx_texml_app_id",
        "telnyx_from_number",
        "telnyx_account_sid",
        "telnyx_assistant_voice_api_key_ref",
        mode="before",
    )
    @classmethod
    def _vacio_es_none(cls, v: str | None) -> str | None:
        return v or None

    def requerir_para_llamar(self) -> None:
        faltantes = [
            nombre.upper()
            for nombre in ("telnyx_assistant_id", "telnyx_texml_app_id", "telnyx_from_number")
            if not getattr(self, nombre)
        ]
        if faltantes:
            raise ConfigError(
                f"Faltan variables para llamar: {', '.join(faltantes)}. "
                "Ejecuta `voice-outbound setup-assistant` y revisa `.env`."
            )


def cargar_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as e:
        campos = ", ".join(str(err["loc"][0]).upper() for err in e.errors())
        raise ConfigError(f"Configuración inválida o incompleta: {campos}") from e


def guardar_en_env(valores: dict[str, str], env_file: Path = ENV_FILE) -> None:
    """Actualiza (o agrega) claves en `.env` sin tocar el resto del archivo."""
    lineas = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    pendientes = dict(valores)
    for i, linea in enumerate(lineas):
        clave = linea.split("=", 1)[0].strip()
        if clave in pendientes:
            lineas[i] = f"{clave}={pendientes.pop(clave)}"
    lineas.extend(f"{k}={v}" for k, v in pendientes.items())
    env_file.write_text("\n".join(lineas) + "\n", encoding="utf-8")
