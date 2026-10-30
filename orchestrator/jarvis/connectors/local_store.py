"""Almacén local de tareas, actividades y objetivos.

Tiene exactamente la misma interfaz y el mismo formato de respuesta que
`PersonalHubClient`, así las herramientas no saben (ni les importa) cuál
de los dos está detrás. Se usa cuando el usuario no ha conectado Personal Hub.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jarvis.models import LocalActivity, LocalGoal, LocalTask
from jarvis.timeutil import as_utc, utcnow
from jarvis.tools.base import ToolError

MAX_RESULTS = 25
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class LocalStore:
    def __init__(self, session: Session, user_id: int, tz_name: str) -> None:
        self.s = session
        self.user_id = user_id
        self.tz = ZoneInfo(tz_name)

    # ================================================================ tareas
    def list_tasks(self, status: str | None = None, priority: str | None = None, due_from: str | None = None,
                   due_to: str | None = None, overdue: bool | None = None, q: str | None = None,
                   limit: int | None = None) -> dict[str, Any]:
        query = select(LocalTask).where(LocalTask.user_id == self.user_id)
        status = status or "open"
        if status == "open":
            query = query.where(LocalTask.status != "completed")
        elif status != "all":
            query = query.where(LocalTask.status == status)
        if priority:
            query = query.where(LocalTask.priority == priority)
        if due_from:
            query = query.where(LocalTask.due_date >= _parse_date(due_from))
        if due_to:
            query = query.where(LocalTask.due_date <= _parse_date(due_to))
        if overdue:
            query = query.where(LocalTask.status != "completed", LocalTask.due_date < self._today())
        if q:
            query = query.where(func.lower(LocalTask.title).contains(q.lower()))

        query = query.order_by(LocalTask.due_date.is_(None), LocalTask.due_date, LocalTask.id)
        query = query.limit(min(limit or MAX_RESULTS, MAX_RESULTS))
        tasks = [self._task(t) for t in self.s.scalars(query)]
        return {"count": len(tasks), "tasks": tasks}

    def create_task(self, title: str, description: str | None = None, priority: str | None = None,
                    due_date: str | None = None) -> dict[str, Any]:
        if not title or not title.strip():
            raise ToolError("La tarea necesita un título.")
        task = LocalTask(
            user_id=self.user_id,
            title=title.strip(),
            description=description,
            priority=_valid_priority(priority),
            due_date=_parse_date(due_date) if due_date else None,
        )
        self.s.add(task)
        self.s.flush()
        return {"task": self._task(task)}

    def complete_task(self, task_id: int) -> dict[str, Any]:
        task = self._get(LocalTask, task_id)
        task.status = "completed"
        task.completed_at = utcnow()
        self.s.flush()
        return {"task": self._task(task)}

    def delete_task(self, task_id: int) -> dict[str, Any]:
        task = self._get(LocalTask, task_id)
        data = self._task(task)
        self.s.delete(task)
        self.s.flush()
        return {"deleted": data}

    # ============================================================ actividades
    def list_activities(self, days: int | None = None, subject: str | None = None) -> dict[str, Any]:
        start = datetime.combine(self._today(), time.min, self.tz)
        end = datetime.combine(self._today() + timedelta(days=days or 7), time.max, self.tz)
        return self._activities_between(start, end, subject)

    def create_activity(self, title: str, due_at: str, subject: str | None = None, type: str | None = None,
                        notes: str | None = None) -> dict[str, Any]:
        activity = LocalActivity(
            user_id=self.user_id,
            title=title.strip(),
            subject=subject,
            type=type or "entrega",
            due_at=self._parse_local_datetime(due_at),
            notes=notes,
        )
        self.s.add(activity)
        self.s.flush()
        return {"activity": self._activity(activity)}

    # ============================================================= objetivos
    def list_goals(self, q: str | None = None) -> dict[str, Any]:
        query = select(LocalGoal).where(LocalGoal.user_id == self.user_id, LocalGoal.active.is_(True))
        if q:
            query = query.where(func.lower(LocalGoal.title).contains(q.lower()))
        goals = [self._goal(g) for g in self.s.scalars(query.order_by(LocalGoal.deadline.is_(None), LocalGoal.deadline))]
        return {"count": len(goals), "goals": goals}

    def create_goal(self, title: str, target: float, unit: str | None = None, current: float | None = None,
                    deadline: str | None = None) -> dict[str, Any]:
        if target is None or float(target) <= 0:
            raise ToolError("La meta del objetivo debe ser mayor que cero.")
        goal = LocalGoal(
            user_id=self.user_id,
            title=title.strip(),
            target_value=float(target),
            current_value=float(current or 0),
            unit=unit or "COP",
            deadline=_parse_date(deadline) if deadline else None,
        )
        self.s.add(goal)
        self.s.flush()
        return {"goal": self._goal(goal)}

    def update_goal_progress(self, goal_id: int, add: float | None = None, set_to: float | None = None) -> dict[str, Any]:
        goal = self._get(LocalGoal, goal_id)
        if set_to is not None:
            goal.current_value = float(set_to)
        elif add is not None:
            goal.current_value = float(goal.current_value) + float(add)
        else:
            raise ToolError("Indica cuánto sumar o el nuevo valor del objetivo.")
        self.s.flush()
        return {"goal": self._goal(goal)}

    # =============================================================== resumen
    def summary(self, date: str | None = None) -> dict[str, Any]:
        day = _parse_date(date) if date else self._today()
        iso = day.isoformat()
        start = datetime.combine(day, time.min, self.tz)
        high = self.list_tasks(priority="high", limit=5)["tasks"]
        return {
            "date": iso,
            "weekday": _DIAS[day.weekday()],
            "tasks_due_today": self.list_tasks(due_from=iso, due_to=iso)["tasks"],
            "tasks_overdue": self.list_tasks(overdue=True)["tasks"],
            "tasks_high_priority_open": high,
            "activities_next_3_days": self._activities_between(
                start, datetime.combine(day + timedelta(days=3), time.max, self.tz))["activities"],
            "active_goals": self.list_goals()["goals"][:5],
        }

    # =============================================================== interno
    def _today(self) -> date:
        return datetime.now(self.tz).date()

    def _get(self, model, obj_id: int):
        obj = self.s.get(model, int(obj_id))
        if obj is None or obj.user_id != self.user_id:
            raise ToolError("No encontré ese registro.")
        return obj

    def _activities_between(self, start: datetime, end: datetime, subject: str | None = None) -> dict[str, Any]:
        query = select(LocalActivity).where(
            LocalActivity.user_id == self.user_id,
            LocalActivity.done.is_(False),
            LocalActivity.due_at >= as_utc(start),
            LocalActivity.due_at <= as_utc(end),
        )
        if subject:
            query = query.where(func.lower(LocalActivity.subject).contains(subject.lower()))
        items = [self._activity(a) for a in self.s.scalars(query.order_by(LocalActivity.due_at).limit(MAX_RESULTS))]
        return {"count": len(items), "activities": items}

    def _parse_local_datetime(self, value: str) -> datetime:
        """'2026-11-03' -> ese día 23:59 hora local; '2026-11-03T14:00' -> esa hora local. Se guarda en UTC."""
        try:
            if len(value.strip()) <= 10:
                local = datetime.combine(_parse_date(value), time(23, 59), self.tz)
            else:
                parsed = datetime.fromisoformat(value.strip().replace(" ", "T"))
                local = parsed if parsed.tzinfo else parsed.replace(tzinfo=self.tz)
        except ValueError as exc:
            raise ToolError(f"Fecha inválida: {value}. Usa YYYY-MM-DD o YYYY-MM-DDTHH:MM.") from exc
        return as_utc(local)

    def _task(self, t: LocalTask) -> dict[str, Any]:
        return {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "status": t.status,
            "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "overdue": bool(t.due_date and t.status != "completed" and t.due_date < self._today()),
        }

    def _activity(self, a: LocalActivity) -> dict[str, Any]:
        return {
            "id": a.id,
            "title": a.title,
            "subject": a.subject,
            "type": a.type,
            "due_at": as_utc(a.due_at).astimezone(self.tz).isoformat(timespec="minutes"),
            "notes": a.notes,
        }

    @staticmethod
    def _goal(g: LocalGoal) -> dict[str, Any]:
        target = float(g.target_value)
        current = float(g.current_value)
        return {
            "id": g.id,
            "title": g.title,
            "current": current,
            "target": target,
            "unit": g.unit,
            "progress_percent": round(min(100.0, current / target * 100), 1) if target > 0 else 0.0,
            "deadline": g.deadline.isoformat() if g.deadline else None,
        }


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError as exc:
        raise ToolError(f"Fecha inválida: {value}. Usa el formato YYYY-MM-DD.") from exc


def _valid_priority(value: str | None) -> str:
    value = (value or "medium").lower()
    if value not in _PRIORITY_ORDER:
        raise ToolError("La prioridad debe ser low, medium o high.")
    return value
