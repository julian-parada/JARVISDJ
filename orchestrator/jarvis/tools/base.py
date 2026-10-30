"""Contrato común de todas las herramientas.

Principio 2 del plan: "el cerebro no ejecuta, solicita". El modelo solo ve
nombre, descripción y esquema; la ejecución real pasa siempre por aquí,
con su nivel de permiso.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from jarvis.models import User, UserSettings


class Permission(str, Enum):
    READ = "read"            # se ejecuta sin preguntar
    WRITE = "write"          # se ejecuta e informa
    SENSITIVE = "sensitive"  # requiere confirmación explícita


class ToolError(Exception):
    """Error esperado que se le devuelve al modelo como texto, sin romper el turno."""


@dataclass
class ToolContext:
    user: "User"
    settings: "UserSettings"
    session: "Session"
    channel: str
    turn_id: str
    # Fábrica de conectores: ctx.connector("personal_hub") -> cliente autenticado del usuario
    connector_factory: Callable[[str], Any]
    extras: dict[str, Any] = field(default_factory=dict)

    def connector(self, provider: str) -> Any:
        return self.connector_factory(provider)


class Tool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]
    permission: Permission = Permission.READ
    # Servicio que necesita credenciales del usuario (None = interno)
    provider: str | None = None

    def definition(self) -> dict[str, Any]:
        """Formato que espera la API de Claude."""
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}

    def describe_action(self, tool_input: dict[str, Any]) -> str:
        """Texto que se le muestra al usuario antes de confirmar una acción sensible."""
        return f"{self.name} con {tool_input}"

    @abstractmethod
    def run(self, ctx: ToolContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"Herramienta duplicada: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def available_for(self, enabled: list[str] | None, providers: set[str]) -> list[Tool]:
        """Herramientas que el usuario tiene habilitadas y con credenciales configuradas."""
        tools = []
        for tool in self._tools.values():
            if enabled is not None and tool.name not in enabled and tool.provider is not None:
                continue
            if tool.provider is not None and tool.provider not in providers:
                continue
            tools.append(tool)
        return tools
