"""Herramientas de pendientes: tareas, actividades académicas y objetivos.

Funcionan igual con el almacén local o con Personal Hub: ambos exponen
la misma interfaz a través del proveedor lógico "tasks".
"""

from __future__ import annotations

from typing import Any

from jarvis.tools.base import Permission, Tool, ToolContext

PROVIDER = "tasks"

_PRIORITY = {"type": "string", "enum": ["low", "medium", "high"], "description": "Prioridad: low=baja, medium=media, high=alta"}
_DATE = {"type": "string", "description": "Fecha en formato YYYY-MM-DD"}


class _TasksTool(Tool):
    provider = PROVIDER

    def backend(self, ctx: ToolContext):
        return ctx.connector(PROVIDER)


# ------------------------------------------------------------------ resumen
class ResumenDia(_TasksTool):
    name = "resumen_dia"
    description = (
        "Resumen consolidado de un día: tareas que vencen ese día, tareas vencidas, tareas de alta "
        "prioridad abiertas, actividades académicas de los próximos 3 días y objetivos activos. "
        "Úsala para preguntas generales como '¿qué tengo hoy?' o '¿cómo va mi día?'."
    )
    input_schema = {
        "type": "object",
        "properties": {"fecha": {**_DATE, "description": "Día a resumir (YYYY-MM-DD). Si se omite, hoy."}},
    }

    def run(self, ctx: ToolContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.backend(ctx).summary(date=tool_input.get("fecha"))


# ------------------------------------------------------------------- tareas
class ListarTareas(_TasksTool):
    name = "listar_tareas"
    description = (
        "Consulta tareas del usuario con filtros. Úsala también para encontrar el id de una tarea "
        "por su nombre antes de completarla o eliminarla (parámetro 'buscar')."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "estado": {
                "type": "string",
                "enum": ["open", "all", "pending", "in_progress", "completed"],
                "description": "open = no completadas (por defecto)",
            },
            "prioridad": _PRIORITY,
            "desde": {**_DATE, "description": "Fecha límite desde (YYYY-MM-DD)"},
            "hasta": {**_DATE, "description": "Fecha límite hasta (YYYY-MM-DD)"},
            "vencidas": {"type": "boolean", "description": "Solo tareas abiertas con fecha pasada"},
            "buscar": {"type": "string", "description": "Texto a buscar en el título"},
            "limite": {"type": "integer", "minimum": 1, "maximum": 25},
        },
    }

    def run(self, ctx: ToolContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.backend(ctx).list_tasks(
            status=tool_input.get("estado"),
            priority=tool_input.get("prioridad"),
            due_from=tool_input.get("desde"),
            due_to=tool_input.get("hasta"),
            overdue=tool_input.get("vencidas"),
            q=tool_input.get("buscar"),
            limit=tool_input.get("limite"),
        )


class CrearTarea(_TasksTool):
    name = "crear_tarea"
    permission = Permission.WRITE
    description = "Crea una tarea nueva. Convierte fechas relativas ('el viernes') a YYYY-MM-DD usando la fecha actual."
    input_schema = {
        "type": "object",
        "properties": {
            "titulo": {"type": "string", "description": "Título corto y claro"},
            "descripcion": {"type": "string"},
            "prioridad": _PRIORITY,
            "fecha_limite": _DATE,
        },
        "required": ["titulo"],
    }

    def run(self, ctx: ToolContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.backend(ctx).create_task(
            title=tool_input["titulo"],
            description=tool_input.get("descripcion"),
            priority=tool_input.get("prioridad"),
            due_date=tool_input.get("fecha_limite"),
        )


class CompletarTarea(_TasksTool):
    name = "completar_tarea"
    permission = Permission.WRITE
    description = (
        "Marca una tarea como completada usando su id. Si el usuario la nombra por texto, primero "
        "búscala con listar_tareas; si hay varias coincidencias, pregúntale cuál."
    )
    input_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer", "description": "id de la tarea"}},
        "required": ["id"],
    }

    def run(self, ctx: ToolContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.backend(ctx).complete_task(tool_input["id"])


class EliminarTarea(_TasksTool):
    name = "eliminar_tarea"
    permission = Permission.SENSITIVE
    description = (
        "Elimina definitivamente una tarea por su id. Acción sensible: el sistema pedirá confirmación "
        "al usuario. Incluye el título en 'titulo' para que el usuario sepa qué confirma."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "titulo": {"type": "string", "description": "Título de la tarea, para mostrarlo en la confirmación"},
        },
        "required": ["id"],
    }

    def describe_action(self, tool_input: dict[str, Any]) -> str:
        titulo = tool_input.get("titulo")
        return f"eliminar la tarea «{titulo}» (id {tool_input['id']})" if titulo else f"eliminar la tarea con id {tool_input['id']}"

    def run(self, ctx: ToolContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.backend(ctx).delete_task(tool_input["id"])


# -------------------------------------------------------------- actividades
class ListarActividades(_TasksTool):
    name = "listar_actividades"
    description = "Próximas actividades académicas (entregas, parciales, exposiciones)."
    input_schema = {
        "type": "object",
        "properties": {
            "dias": {"type": "integer", "minimum": 1, "maximum": 60, "description": "Ventana en días desde hoy (por defecto 7)"},
            "materia": {"type": "string", "description": "Filtrar por materia"},
        },
    }

    def run(self, ctx: ToolContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.backend(ctx).list_activities(days=tool_input.get("dias"), subject=tool_input.get("materia"))


class CrearActividad(_TasksTool):
    name = "crear_actividad"
    permission = Permission.WRITE
    description = (
        "Registra una actividad académica (parcial, entrega, exposición, quiz). Úsala cuando el usuario "
        "hable de algo de la universidad con fecha; para pendientes generales usa crear_tarea."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "titulo": {"type": "string"},
            "materia": {"type": "string"},
            "tipo": {"type": "string", "enum": ["entrega", "parcial", "exposicion", "quiz", "otro"]},
            "fecha": {"type": "string", "description": "YYYY-MM-DD, o YYYY-MM-DDTHH:MM si se conoce la hora (hora local)"},
            "notas": {"type": "string"},
        },
        "required": ["titulo", "fecha"],
    }

    def run(self, ctx: ToolContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.backend(ctx).create_activity(
            title=tool_input["titulo"],
            due_at=tool_input["fecha"],
            subject=tool_input.get("materia"),
            type=tool_input.get("tipo"),
            notes=tool_input.get("notas"),
        )


# ---------------------------------------------------------------- objetivos
class EstadoObjetivos(_TasksTool):
    name = "estado_objetivos"
    description = "Progreso de los objetivos activos (ahorro, estudio, etc.)."
    input_schema = {
        "type": "object",
        "properties": {"buscar": {"type": "string", "description": "Texto para filtrar por nombre del objetivo"}},
    }

    def run(self, ctx: ToolContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.backend(ctx).list_goals(q=tool_input.get("buscar"))


class CrearObjetivo(_TasksTool):
    name = "crear_objetivo"
    permission = Permission.WRITE
    description = "Crea un objetivo medible, por ejemplo 'ahorrar 500000 COP para diciembre' o 'leer 10 libros'."
    input_schema = {
        "type": "object",
        "properties": {
            "titulo": {"type": "string"},
            "meta": {"type": "number", "description": "Valor a alcanzar"},
            "unidad": {"type": "string", "description": "COP, horas, libros, km... (por defecto COP)"},
            "actual": {"type": "number", "description": "Progreso que ya lleva (por defecto 0)"},
            "fecha_limite": _DATE,
        },
        "required": ["titulo", "meta"],
    }

    def run(self, ctx: ToolContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.backend(ctx).create_goal(
            title=tool_input["titulo"],
            target=tool_input["meta"],
            unit=tool_input.get("unidad"),
            current=tool_input.get("actual"),
            deadline=tool_input.get("fecha_limite"),
        )


class RegistrarAvanceObjetivo(_TasksTool):
    name = "registrar_avance_objetivo"
    permission = Permission.WRITE
    description = (
        "Actualiza el progreso de un objetivo por su id: 'sumar' agrega al valor actual (ej. ahorré 50000), "
        "'nuevo_valor' lo reemplaza. Busca el id con estado_objetivos si hace falta."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "sumar": {"type": "number"},
            "nuevo_valor": {"type": "number"},
        },
        "required": ["id"],
    }

    def run(self, ctx: ToolContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.backend(ctx).update_goal_progress(
            tool_input["id"], add=tool_input.get("sumar"), set_to=tool_input.get("nuevo_valor")
        )


ALL = [
    ResumenDia,
    ListarTareas, CrearTarea, CompletarTarea, EliminarTarea,
    ListarActividades, CrearActividad,
    EstadoObjetivos, CrearObjetivo, RegistrarAvanceObjetivo,
]
