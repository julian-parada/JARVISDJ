"""Cliente HTTP de la API del asistente en Personal Hub (Laravel)."""

from __future__ import annotations

from typing import Any

import httpx

from jarvis.config import get_settings
from jarvis.tools.base import ToolError


class PersonalHubClient:
    def __init__(self, base_url: str, token: str, transport: httpx.BaseTransport | None = None) -> None:
        if not base_url:
            raise ToolError("Personal Hub no tiene URL configurada.")
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/api/assistant",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=get_settings().http_timeout_seconds,
            transport=transport,
        )

    # --- API pública -----------------------------------------------------
    def summary(self, date: str | None = None) -> dict[str, Any]:
        return self._request("GET", "/summary", params=_clean({"date": date}))

    def list_tasks(self, **filters: Any) -> dict[str, Any]:
        if "overdue" in filters and filters["overdue"] is not None:
            filters["overdue"] = 1 if filters["overdue"] else 0
        return self._request("GET", "/tasks", params=_clean(filters))

    def create_task(self, **data: Any) -> dict[str, Any]:
        return self._request("POST", "/tasks", json=_clean(data))

    def complete_task(self, task_id: int) -> dict[str, Any]:
        return self._request("PATCH", f"/tasks/{int(task_id)}/complete")

    def delete_task(self, task_id: int) -> dict[str, Any]:
        return self._request("DELETE", f"/tasks/{int(task_id)}")

    def list_activities(self, **filters: Any) -> dict[str, Any]:
        return self._request("GET", "/activities", params=_clean(filters))

    def create_activity(self, **data: Any) -> dict[str, Any]:
        return self._request("POST", "/activities", json=_clean(data))

    def list_goals(self, **filters: Any) -> dict[str, Any]:
        return self._request("GET", "/goals", params=_clean(filters))

    def create_goal(self, **data: Any) -> dict[str, Any]:
        return self._request("POST", "/goals", json=_clean(data))

    def update_goal_progress(self, goal_id: int, add: float | None = None, set_to: float | None = None) -> dict[str, Any]:
        return self._request("PATCH", f"/goals/{int(goal_id)}/progress", json=_clean({"add": add, "set": set_to}))

    # --- interno ---------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ToolError("Personal Hub tardó demasiado en responder.") from exc
        except httpx.HTTPError as exc:
            raise ToolError(f"No pude conectar con Personal Hub ({exc.__class__.__name__}).") from exc

        if resp.status_code == 401:
            raise ToolError("El token de Personal Hub no es válido o expiró.")
        if resp.status_code == 403:
            raise ToolError("El token de Personal Hub no tiene permiso para esta acción.")
        if resp.status_code == 404:
            raise ToolError("No encontré ese registro en Personal Hub.")
        if resp.status_code == 422:
            errors = resp.json().get("errors", {})
            detail = "; ".join(f"{k}: {', '.join(v)}" for k, v in errors.items()) or "datos inválidos"
            raise ToolError(f"Personal Hub rechazó los datos: {detail}")
        if resp.status_code == 429:
            raise ToolError("Demasiadas solicitudes a Personal Hub, intenta en un momento.")
        if resp.status_code >= 400:
            raise ToolError(f"Personal Hub respondió con error {resp.status_code}.")

        return resp.json()


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v is not None and v != ""}
