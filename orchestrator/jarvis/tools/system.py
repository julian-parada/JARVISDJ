"""Herramientas internas: confirmar o cancelar acciones sensibles."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from jarvis.models import PendingAction
from jarvis.timeutil import as_utc, utcnow
from jarvis.tools.base import Permission, Tool, ToolContext, ToolError


def current_pending(ctx: ToolContext) -> PendingAction | None:
    action = ctx.session.scalar(
        select(PendingAction)
        .where(PendingAction.user_id == ctx.user.id, PendingAction.status == "pending")
        .order_by(PendingAction.id.desc())
    )
    if action and as_utc(action.expires_at) < utcnow():
        action.status = "expired"
        return None
    return action


class ConfirmarAccion(Tool):
    name = "confirmar_accion"
    permission = Permission.WRITE
    description = (
        "Ejecuta la acción sensible que está esperando confirmación. Úsala SOLO cuando el usuario, "
        "en su mensaje más reciente, confirme de forma explícita (sí, confirmo, hazlo, dale)."
    )
    input_schema = {"type": "object", "properties": {}}

    def run(self, ctx: ToolContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        action = current_pending(ctx)
        if action is None:
            raise ToolError("No hay ninguna acción pendiente de confirmación (o ya expiró).")
        if action.turn_id == ctx.turn_id:
            # Defensa: el modelo no puede pedir y confirmar en el mismo turno.
            raise ToolError("El usuario aún no ha respondido. Pídele que confirme en un mensaje nuevo.")

        executor = ctx.extras["execute_confirmed"]
        result = executor(action.tool_name, action.tool_input)
        action.status = "confirmed"
        return {"accion": action.description, "resultado": result}


class CancelarAccion(Tool):
    name = "cancelar_accion"
    permission = Permission.READ
    description = "Cancela la acción sensible pendiente cuando el usuario dice que no o cambia de idea."
    input_schema = {"type": "object", "properties": {}}

    def run(self, ctx: ToolContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        action = current_pending(ctx)
        if action is None:
            return {"status": "nada_pendiente"}
        action.status = "cancelled"
        return {"status": "cancelada", "accion": action.description}


ALL = [ConfirmarAccion, CancelarAccion]
