"""Clientes de servicios externos. Cada conector se crea por usuario con sus credenciales.

Proveedores lógicos:
- "tasks": tareas/actividades/objetivos. Si el usuario conectó Personal Hub se usa
  su API; si no, el almacén local. Siempre está disponible.
"""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from jarvis.connectors.local_store import LocalStore
from jarvis.connectors.personal_hub import PersonalHubClient
from jarvis.models import Credential, User
from jarvis.security import decrypt
from jarvis.tools.base import ToolError

TASKS = "tasks"
ALWAYS_AVAILABLE = {TASKS}

# provider con credencial -> constructor(base_url, secret)
CONNECTOR_BUILDERS: dict[str, Callable[[str | None, str], Any]] = {
    "personal_hub": lambda url, secret: PersonalHubClient(url or "", secret),
}


def configured_providers(session: Session, user_id: int) -> set[str]:
    rows = session.scalars(select(Credential.provider).where(Credential.user_id == user_id))
    return set(rows) | ALWAYS_AVAILABLE


def tasks_backend_name(session: Session, user_id: int) -> str:
    return "personal_hub" if "personal_hub" in configured_providers(session, user_id) else "local"


def make_connector_factory(session: Session, user_id: int) -> Callable[[str], Any]:
    cache: dict[str, Any] = {}

    def build(provider: str) -> Any:
        cred = session.scalar(
            select(Credential).where(Credential.user_id == user_id, Credential.provider == provider)
        )
        if cred is None:
            raise ToolError(f"El servicio '{provider}' no está configurado para este usuario.")
        builder = CONNECTOR_BUILDERS.get(provider)
        if builder is None:
            raise ToolError(f"No hay conector para '{provider}'.")
        return builder(cred.base_url, decrypt(cred.secret_encrypted))

    def factory(provider: str) -> Any:
        if provider in cache:
            return cache[provider]
        if provider == TASKS:
            if tasks_backend_name(session, user_id) == "personal_hub":
                cache[provider] = build("personal_hub")
            else:
                user = session.get(User, user_id)
                cache[provider] = LocalStore(session, user_id, user.timezone if user else "America/Bogota")
        else:
            cache[provider] = build(provider)
        return cache[provider]

    return factory
