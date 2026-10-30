"""Configuración del sistema (no del usuario).

Aquí solo van secretos y parámetros de la instalación. Todo lo que es
propio de cada usuario (nombre del asistente, tono, tokens de sus
servicios) vive en la base de datos.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Carpeta del proyecto (donde está pyproject.toml). El .env y la BD viven aquí,
# así `jarvis` funciona igual sin importar desde qué carpeta lo ejecutes.
PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"
DEFAULT_DB = f"sqlite:///{(PROJECT_DIR / 'jarvis.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # El .env del proyecto primero; uno en la carpeta actual (si existe) lo sobrescribe.
        env_file=(str(ENV_FILE), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5-5"
    claude_max_tokens: int = 1024

    database_url: str = DEFAULT_DB

    # Clave maestra para cifrar las credenciales de cada usuario (Fernet).
    # La genera `jarvis setup` (o `jarvis gen-key`).
    jarvis_master_key: str = ""

    telegram_bot_token: str = ""

    history_messages: int = 16          # mensajes previos que se envían como contexto
    history_max_age_hours: int = 12     # pasado este tiempo la conversación arranca limpia
    max_tool_iterations: int = 8        # tope de llamadas a herramientas por turno
    pending_action_minutes: int = 10    # vigencia de una acción esperando confirmación
    http_timeout_seconds: float = 15.0

    log_level: str = "WARNING"


@lru_cache
def get_settings() -> Settings:
    return Settings()
