"""Canal de terminal: la forma más rápida de probar el cerebro."""

from __future__ import annotations

from jarvis.orchestrator import Orchestrator

HELP = "Escribe normal. Comandos: /nuevo (olvidar conversación) · /salir"


def run_terminal(orchestrator: Orchestrator, user_id: int, user_name: str = "tú") -> None:
    print(f"\nJARVIS listo, {user_name}. {HELP}\n")
    while True:
        try:
            text = input("tú › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not text:
            continue
        if text.lower() in ("/salir", "/exit", "/quit", "salir"):
            break
        if text == "/nuevo":
            orchestrator.reset_context(user_id)
            print("jarvis › Conversación reiniciada.\n")
            continue

        print("jarvis › …", end="\r", flush=True)
        try:
            reply = orchestrator.handle(user_id, text, channel="cli")
        except Exception as exc:  # noqa: BLE001 — en terminal mostramos el error y seguimos
            print(f"[error] {exc}\n")
            continue

        print(f"jarvis › {reply.text}")
        if reply.tools_used:
            print(f"         · {', '.join(reply.tools_used)}")
        print()
