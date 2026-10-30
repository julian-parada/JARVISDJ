"""El cerebro: recibe texto, consulta a Claude, ejecuta herramientas y responde.

Es independiente del canal. Terminal, Telegram y (en Fase 2) voz llaman a
`Orchestrator.handle()` de la misma forma.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from jarvis.config import Settings, get_settings
from jarvis.connectors import configured_providers, make_connector_factory
from jarvis.db import session_scope
from jarvis.llm import LLM, LLMError
from jarvis.models import Message, PendingAction, ToolLog, UsageLog, User, UserSettings
from jarvis.prompts import build_system_prompt
from jarvis.security import SecurityError
from jarvis.timeutil import as_utc, utcnow
from jarvis.tools import Permission, Tool, ToolContext, ToolError, ToolRegistry
from jarvis.tools.system import current_pending

log = logging.getLogger("jarvis.orchestrator")

MAX_RESULT_CHARS = 8000  # tope de lo que se le devuelve al modelo por herramienta


@dataclass
class Reply:
    text: str
    tools_used: list[str] = field(default_factory=list)
    pending_confirmation: str | None = None


class Orchestrator:
    def __init__(self, llm: LLM, registry: ToolRegistry, settings: Settings | None = None) -> None:
        self.llm = llm
        self.registry = registry
        self.settings = settings or get_settings()
        self._locks: dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, user_id: int) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(user_id, threading.Lock())

    # ------------------------------------------------------------------ API
    def handle(self, user_id: int, text: str, channel: str = "cli") -> Reply:
        text = (text or "").strip()
        if not text:
            return Reply(text="")

        # Un turno a la vez por usuario: evita respuestas cruzadas si llegan dos mensajes seguidos.
        with self._lock_for(user_id), session_scope() as session:
            user = session.get(User, user_id)
            if user is None or not user.active:
                return Reply(text="Usuario no encontrado o inactivo.")
            settings = user.settings or self._default_settings(session, user)
            return self._run_turn(session, user, settings, text, channel)

    def reset_context(self, user_id: int) -> None:
        with session_scope() as session:
            user = session.get(User, user_id)
            if user:
                user.context_reset_at = utcnow()

    # -------------------------------------------------------------- interno
    def _run_turn(self, session: Session, user: User, settings: UserSettings, text: str, channel: str) -> Reply:
        turn_id = uuid.uuid4().hex
        model = settings.model or self.settings.claude_model
        tools_used: list[str] = []

        ctx = ToolContext(
            user=user,
            settings=settings,
            session=session,
            channel=channel,
            turn_id=turn_id,
            connector_factory=make_connector_factory(session, user.id),
        )
        ctx.extras["execute_confirmed"] = lambda name, inp: self._execute_confirmed(ctx, name, inp)

        available = self.registry.available_for(settings.enabled_tools, configured_providers(session, user.id))
        tool_defs = [t.definition() for t in available]
        allowed = {t.name for t in available}

        messages = self._history(session, user) + [{"role": "user", "content": text}]
        new_pending: str | None = None
        final_text = ""

        for _ in range(self.settings.max_tool_iterations):
            system = build_system_prompt(user, settings, channel, current_pending(ctx))
            try:
                resp = self.llm.complete(
                    model=model,
                    system=system,
                    messages=messages,
                    tools=tool_defs,
                    max_tokens=self.settings.claude_max_tokens,
                )
            except LLMError as exc:
                # No se guarda en el historial: el turno quedó incompleto.
                log.info("Error de la API de IA: %s", exc)
                return Reply(text=f"⚠️ {exc}", tools_used=tools_used, pending_confirmation=new_pending)
            session.add(UsageLog(
                user_id=user.id, channel=channel, model=resp.model or model,
                input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
            ))

            if resp.stop_reason != "tool_use" or not resp.tool_calls:
                final_text = resp.text
                break

            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for call in resp.tool_calls:
                tools_used.append(call["name"])
                outcome, is_error = self._execute(ctx, call["name"], call["input"], allowed)
                if isinstance(outcome, dict) and outcome.get("status") == "confirmation_required":
                    new_pending = outcome["accion"]
                results.append({
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": _to_text(outcome),
                    "is_error": is_error,
                })
            messages.append({"role": "user", "content": results})
        else:
            final_text = "Me enredé con demasiados pasos en esta solicitud. ¿Puedes decírmelo de forma más concreta?"

        if not final_text:
            final_text = "Listo."

        session.add(Message(user_id=user.id, channel=channel, role="user", content=text))
        session.add(Message(user_id=user.id, channel=channel, role="assistant", content=final_text))
        return Reply(text=final_text, tools_used=tools_used, pending_confirmation=new_pending)

    def _execute(self, ctx: ToolContext, name: str, tool_input: dict[str, Any], allowed: set[str]) -> tuple[Any, bool]:
        tool = self.registry.get(name)
        started = time.monotonic()

        if tool is None or name not in allowed:
            self._log(ctx, name, tool_input, "unknown", "denied", "herramienta no permitida", started)
            return f"La herramienta '{name}' no está disponible.", True

        if tool.permission is Permission.SENSITIVE:
            description = tool.describe_action(tool_input)
            self._create_pending(ctx, tool, tool_input, description)
            self._log(ctx, name, tool_input, tool.permission.value, "needs_confirmation", description, started)
            return {
                "status": "confirmation_required",
                "accion": description,
                "instruccion": "No se ha ejecutado. Pide al usuario que confirme explícitamente.",
            }, False

        return self._run_tool(ctx, tool, tool_input, started)

    def _execute_confirmed(self, ctx: ToolContext, name: str, tool_input: dict[str, Any]) -> Any:
        """Ejecuta una acción sensible ya confirmada por el usuario."""
        tool = self.registry.get(name)
        if tool is None:
            raise ToolError(f"La herramienta '{name}' ya no existe.")
        result, is_error = self._run_tool(ctx, tool, tool_input, time.monotonic())
        if is_error:
            raise ToolError(str(result))
        return result

    def _run_tool(self, ctx: ToolContext, tool: Tool, tool_input: dict[str, Any], started: float) -> tuple[Any, bool]:
        try:
            result = tool.run(ctx, tool_input)
            self._log(ctx, tool.name, tool_input, tool.permission.value, "ok", _to_text(result)[:500], started)
            return result, False
        except (ToolError, SecurityError) as exc:
            self._log(ctx, tool.name, tool_input, tool.permission.value, "error", str(exc), started)
            return str(exc), True
        except Exception as exc:  # error inesperado: se registra completo, al modelo va un mensaje genérico
            log.exception("Fallo inesperado en %s", tool.name)
            self._log(ctx, tool.name, tool_input, tool.permission.value, "error", repr(exc)[:500], started)
            return "Ocurrió un error interno ejecutando la herramienta.", True

    def _create_pending(self, ctx: ToolContext, tool: Tool, tool_input: dict[str, Any], description: str) -> None:
        # Solo una acción pendiente a la vez por usuario.
        for old in ctx.session.scalars(
            select(PendingAction).where(PendingAction.user_id == ctx.user.id, PendingAction.status == "pending")
        ):
            old.status = "cancelled"
        ctx.session.add(PendingAction(
            user_id=ctx.user.id,
            tool_name=tool.name,
            tool_input=tool_input,
            description=description,
            turn_id=ctx.turn_id,
            expires_at=utcnow() + timedelta(minutes=self.settings.pending_action_minutes),
        ))
        ctx.session.flush()

    def _history(self, session: Session, user: User) -> list[dict[str, Any]]:
        cutoff = utcnow() - timedelta(hours=self.settings.history_max_age_hours)
        if user.context_reset_at and as_utc(user.context_reset_at) > cutoff:
            cutoff = as_utc(user.context_reset_at)

        rows = list(session.scalars(
            select(Message)
            .where(Message.user_id == user.id, Message.created_at > cutoff)
            .order_by(Message.id.desc())
            .limit(self.settings.history_messages)
        ))
        rows.reverse()

        # La API exige alternar user/assistant y empezar por user.
        history: list[dict[str, Any]] = []
        for row in rows:
            if not history and row.role != "user":
                continue
            if history and history[-1]["role"] == row.role:
                history[-1]["content"] += "\n" + row.content
            else:
                history.append({"role": row.role, "content": row.content})
        if history and history[-1]["role"] == "user":
            history.pop()  # un mensaje de usuario sin respuesta rompería la alternancia
        return history

    def _log(self, ctx: ToolContext, name: str, tool_input: dict[str, Any], permission: str,
             status: str, summary: str, started: float) -> None:
        ctx.session.add(ToolLog(
            user_id=ctx.user.id,
            channel=ctx.channel,
            tool_name=name,
            tool_input=tool_input,
            permission=permission,
            status=status,
            result_summary=summary,
            duration_ms=int((time.monotonic() - started) * 1000),
        ))

    @staticmethod
    def _default_settings(session: Session, user: User) -> UserSettings:
        settings = UserSettings(user_id=user.id)
        session.add(settings)
        session.flush()
        return settings


def _to_text(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + "… [resultado recortado]"
    return text
