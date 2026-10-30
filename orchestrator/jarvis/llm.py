"""Capa delgada sobre la API de Claude.

El orquestador depende de esta interfaz, no del SDK directamente: en
pruebas se reemplaza por un modelo falso y, si algún día cambias de
proveedor, solo se toca este archivo.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMError(RuntimeError):
    """Error del proveedor de IA, con un mensaje listo para mostrarle al usuario."""


@dataclass
class LLMResponse:
    content: list[dict[str, Any]]          # bloques normalizados: text | tool_use
    stop_reason: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def text(self) -> str:
        return "\n".join(b["text"] for b in self.content if b["type"] == "text").strip()

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b["type"] == "tool_use"]


class LLM(Protocol):
    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> LLMResponse: ...


class AnthropicLLM:
    def __init__(self, api_key: str, client: Any | None = None) -> None:
        import anthropic

        if not api_key and client is None:
            raise RuntimeError("Falta ANTHROPIC_API_KEY en el .env")
        self._client = client or anthropic.Anthropic(api_key=api_key)

    def complete(self, *, model, system, messages, tools, max_tokens) -> LLMResponse:
        import anthropic

        kwargs: dict[str, Any] = dict(model=model, system=system, messages=messages, max_tokens=max_tokens)
        if tools:
            kwargs["tools"] = tools
        try:
            resp = self._client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise LLMError("Tu ANTHROPIC_API_KEY no es válida. Revisa el archivo .env.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise LLMError("Tu cuenta de Anthropic no tiene permiso para usar este modelo.") from exc
        except anthropic.NotFoundError as exc:
            raise LLMError(f"El modelo '{model}' no existe. Cambia CLAUDE_MODEL en el .env.") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Llegué al límite de uso de la API de Claude. Intenta en un minuto.") from exc
        except anthropic.BadRequestError as exc:
            msg = str(exc)
            if "credit" in msg.lower() or "billing" in msg.lower():
                raise LLMError("Tu cuenta de Anthropic no tiene saldo. Recárgala en console.anthropic.com.") from exc
            raise LLMError(f"La API de Claude rechazó la solicitud: {msg[:200]}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("No pude conectarme con la API de Claude. Revisa tu conexión a internet.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"La API de Claude respondió con error {exc.status_code}. Intenta de nuevo.") from exc
        return LLMResponse(
            content=[_normalize(b) for b in resp.content if b.type in ("text", "tool_use")],
            stop_reason=resp.stop_reason or "end_turn",
            model=resp.model,
            input_tokens=getattr(resp.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(resp.usage, "output_tokens", 0) or 0,
        )


def _normalize(block: Any) -> dict[str, Any]:
    if block.type == "text":
        return {"type": "text", "text": block.text}
    return {"type": "tool_use", "id": block.id, "name": block.name, "input": dict(block.input or {})}


@dataclass
class ScriptedLLM:
    """Modelo falso para pruebas: devuelve respuestas predefinidas en orden."""

    responses: list[LLMResponse]
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(self, **kwargs: Any) -> LLMResponse:
        self.calls.append(copy.deepcopy(kwargs))
        if not self.responses:
            raise AssertionError("ScriptedLLM se quedó sin respuestas")
        return self.responses.pop(0)
