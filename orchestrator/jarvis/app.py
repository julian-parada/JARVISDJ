"""Arma las piezas: BD, modelo de IA, herramientas y orquestador."""

from __future__ import annotations

import logging

from jarvis.config import get_settings
from jarvis.db import create_all, init_engine
from jarvis.llm import AnthropicLLM
from jarvis.orchestrator import Orchestrator
from jarvis.tools import default_registry


def setup_logging() -> None:
    logging.basicConfig(
        level=get_settings().log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx registra cada request con la URL; no queremos tokens ni ruido en los logs
    logging.getLogger("httpx").setLevel(logging.WARNING)


def build_orchestrator() -> Orchestrator:
    settings = get_settings()
    init_engine(settings.database_url)
    create_all()
    return Orchestrator(llm=AnthropicLLM(settings.anthropic_api_key), registry=default_registry(), settings=settings)
