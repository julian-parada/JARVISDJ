from jarvis.tools import system, tasks
from jarvis.tools.base import Permission, Tool, ToolContext, ToolError, ToolRegistry


def default_registry() -> ToolRegistry:
    """Registro con todas las herramientas de la Fase 1.

    Para agregar una capacidad nueva (luces, portátil...) se crea un módulo
    con sus herramientas y se registra aquí. El orquestador no cambia.
    """
    registry = ToolRegistry()
    for cls in [*tasks.ALL, *system.ALL]:
        registry.register(cls())
    return registry


__all__ = ["Permission", "Tool", "ToolContext", "ToolError", "ToolRegistry", "default_registry"]
