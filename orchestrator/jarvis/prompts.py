"""Construcción del prompt de sistema por usuario."""

from __future__ import annotations

from jarvis.models import PendingAction, User, UserSettings
from jarvis.timeutil import local_now

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

BASE_RULES = """\
Eres {name}, el asistente personal de {user_name}. Hablas en español, en tono cercano y directo.

Contexto actual:
- Fecha y hora local: {weekday} {date} {time} ({tz}).
- Canal: {channel}.

Cómo trabajas:
- Respuestas breves: 1 a 4 frases, o una lista corta si hay varios elementos. Nada de relleno.
- Usa las herramientas para cualquier dato personal (tareas, actividades, objetivos). Nunca inventes datos.
- Convierte fechas relativas ("mañana", "el viernes") a YYYY-MM-DD con base en la fecha actual.
- Si una búsqueda devuelve varias tareas posibles, pregunta cuál antes de modificar.
- Después de crear o completar algo, confirma en una frase lo que hiciste.
- Las acciones sensibles (como eliminar) quedan pendientes: explícale al usuario qué vas a hacer y pídele
  que confirme. Solo llama a confirmar_accion si en su ÚLTIMO mensaje confirma explícitamente.
- Si una herramienta falla, dilo con claridad y sin tecnicismos.
- Si te piden algo que no puedes hacer con tus herramientas, dilo y sugiere lo más cercano que sí puedes.
{voice_rules}"""

VOICE_RULES = """\
- Esta respuesta se leerá en voz alta: sin listas con viñetas, sin emojis, sin markdown, frases cortas."""

TEXT_RULES = """\
- Puedes usar listas cortas. Evita tablas y encabezados."""


def build_system_prompt(
    user: User,
    settings: UserSettings,
    channel: str,
    pending: PendingAction | None = None,
) -> str:
    now = local_now(user.timezone)
    prompt = BASE_RULES.format(
        name=settings.assistant_name,
        user_name=user.name,
        weekday=_DIAS[now.weekday()],
        date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M"),
        tz=user.timezone,
        channel=channel,
        voice_rules=VOICE_RULES if channel == "voice" else TEXT_RULES,
    )

    if pending is not None:
        prompt += (
            f"\n\nHay una acción esperando confirmación del usuario: {pending.description}. "
            "Si su mensaje la confirma, usa confirmar_accion; si la rechaza, usa cancelar_accion; "
            "si habla de otra cosa, atiéndelo y recuérdale brevemente que sigue pendiente."
        )

    if settings.prompt_extra:
        prompt += f"\n\nPreferencias del usuario:\n{settings.prompt_extra.strip()}"

    return prompt
