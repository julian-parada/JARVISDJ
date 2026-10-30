"""Comando `jarvis`: instalación, administración y arranque de canales.

Uso diario:
  jarvis setup                 asistente de configuración (la primera vez)
  jarvis chat                  conversar por terminal
  jarvis telegram              arrancar el bot de Telegram
  jarvis estado                revisar que todo esté bien configurado

Administración (--user es opcional si solo hay un usuario):
  jarvis create-user --name Julian
  jarvis set-hub --url http://localhost:8000 --token <token>
  jarvis unset-hub
  jarvis link-code
  jarvis settings --name Jarvis --prompt-extra "Llámame Julian. Sé directo."
  jarvis users | usage | logs
  jarvis gen-key | init-db
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import timedelta

from sqlalchemy import func, select

from jarvis import accounts
from jarvis.config import ENV_FILE, get_settings
from jarvis.db import create_all, init_engine, session_scope
from jarvis.models import Credential, ToolLog, UsageLog, User, UserSettings
from jarvis.security import generate_key
from jarvis.timeutil import utcnow

OK, WARN, FAIL = "[OK]", "[!!]", "[XX]"


# ------------------------------------------------------------------ helpers
def _db() -> None:
    init_engine(get_settings().database_url)
    create_all()


def _resolve_user(session, user_id: int | None) -> User:
    """Si no se pasa --user y solo hay un usuario, se usa ese."""
    if user_id is not None:
        user = session.get(User, user_id)
        if user is None:
            sys.exit(f"No existe el usuario {user_id}. Mira la lista con: jarvis users")
        return user
    users = list(session.scalars(select(User).order_by(User.id).limit(2)))
    if not users:
        sys.exit("Todavía no hay usuarios. Ejecuta primero: jarvis setup")
    if len(users) > 1:
        sys.exit("Hay varios usuarios: indica cuál con --user <id> (mira la lista con: jarvis users)")
    return users[0]


def _ask(prompt: str, default: str | None = None, secret: bool = False) -> str:
    label = f"{prompt} [{default}]: " if default else f"{prompt}: "
    try:
        value = getpass.getpass(label) if secret else input(label)
    except (EOFError, KeyboardInterrupt):
        print("\nCancelado.")
        sys.exit(1)
    return value.strip() or (default or "")


def _yes(prompt: str, default: bool = False) -> bool:
    hint = "S/n" if default else "s/N"
    value = _ask(f"{prompt} ({hint})").lower()
    return default if not value else value in ("s", "si", "sí", "y", "yes")


def _read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _write_env(updates: dict[str, str]) -> None:
    """Actualiza las claves indicadas conservando el resto del archivo."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    pending = dict(updates)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else None
        if key in pending:
            out.append(f"{key}={pending.pop(key)}")
        else:
            out.append(line)
    out.extend(f"{k}={v}" for k, v in pending.items())
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")


def _test_claude() -> tuple[bool, str]:
    from jarvis.llm import AnthropicLLM, LLMError

    s = get_settings()
    try:
        resp = AnthropicLLM(s.anthropic_api_key).complete(
            model=s.claude_model, system="Responde solo: ok", max_tokens=5,
            messages=[{"role": "user", "content": "ping"}], tools=[],
        )
        return True, f"Claude responde ({resp.model})"
    except (LLMError, RuntimeError) as exc:
        return False, str(exc)


def _test_hub(session, user_id: int) -> tuple[bool, str]:
    from jarvis.connectors import make_connector_factory
    from jarvis.tools.base import ToolError

    try:
        make_connector_factory(session, user_id)("personal_hub").summary()
        return True, "Personal Hub responde"
    except Exception as exc:  # noqa: BLE001
        return False, f"Personal Hub: {exc}" if isinstance(exc, ToolError) else f"Personal Hub: {exc!r}"


# ----------------------------------------------------------------- comandos
def cmd_setup(args) -> None:
    print("\n=== Configuración de JARVIS ===\n")
    env = _read_env()
    updates: dict[str, str] = {}

    # 1. Clave maestra (nunca se reemplaza si ya existe: se perderían las credenciales cifradas)
    if not env.get("JARVIS_MASTER_KEY"):
        updates["JARVIS_MASTER_KEY"] = generate_key()
        print(f"{OK} Clave de cifrado generada")
    else:
        print(f"{OK} Clave de cifrado existente")

    # 2. API key de Anthropic
    api_key = args.api_key
    if not api_key:
        current = env.get("ANTHROPIC_API_KEY", "")
        if current and not current.startswith("sk-ant-..."):
            print(f"{OK} API key de Anthropic ya configurada (termina en …{current[-4:]})")
            if not args.yes and _yes("¿Quieres cambiarla?"):
                api_key = _ask("Pega tu API key de Anthropic (no se verá al escribir)", secret=True)
        else:
            print("\nNecesitas una API key de Anthropic: https://console.anthropic.com/settings/keys")
            api_key = _ask("Pega tu API key (no se verá al escribir)", secret=True)
    if api_key:
        if not api_key.startswith("sk-ant-"):
            print(f"{WARN} La key no empieza por 'sk-ant-'. Revisa que la copiaste completa.")
        updates["ANTHROPIC_API_KEY"] = api_key

    # 3. Telegram (opcional)
    tg = args.telegram_token
    if tg is None and not args.yes and not env.get("TELEGRAM_BOT_TOKEN"):
        if _yes("\n¿Quieres configurar Telegram ahora? (puedes hacerlo después)"):
            print("En Telegram habla con @BotFather, envía /newbot y copia el token que te da.")
            tg = _ask("Token del bot", secret=True)
    if tg:
        updates["TELEGRAM_BOT_TOKEN"] = tg

    if updates:
        _write_env(updates)
        get_settings.cache_clear()
    print(f"{OK} Configuración guardada en {ENV_FILE}")

    # 4. Base de datos y usuario
    _db()
    with session_scope() as s:
        user = s.scalar(select(User).order_by(User.id))
        if user is None:
            name = args.name or (_ask("\n¿Cómo te llamas?", default=getpass.getuser()) if not args.yes else "Usuario")
            assistant = args.assistant_name or "Jarvis"
            user = accounts.create_user(s, name=name, assistant_name=assistant)
            print(f"{OK} Usuario creado: {user.name} (id {user.id})")
        else:
            print(f"{OK} Usuario existente: {user.name} (id {user.id})")
        user_id = user.id

    # 5. Personal Hub (opcional)
    with session_scope() as s:
        has_hub = s.scalar(select(Credential).where(Credential.user_id == user_id,
                                                     Credential.provider == "personal_hub")) is not None
    if not has_hub and not args.yes:
        print("\nPor defecto JARVIS guarda tus tareas en su propia base de datos (modo local).")
        if _yes("¿Quieres conectarlo a tu Personal Hub (Laravel) en vez de eso?"):
            url = _ask("URL de Personal Hub", default="http://localhost:8000")
            token = _ask("Token de `php artisan assistant:token` (no se verá)", secret=True)
            with session_scope() as s:
                accounts.set_credential(s, user_id, "personal_hub", token, base_url=url)
                ok, msg = _test_hub(s, user_id)
            print(f"{OK if ok else WARN} {msg}")

    # 6. Probar Claude
    if not args.skip_test:
        print("\nProbando conexión con Claude…")
        ok, msg = _test_claude()
        print(f"{OK if ok else FAIL} {msg}")
        if not ok:
            print("\nCorrige eso y vuelve a ejecutar: jarvis setup")
            sys.exit(1)

    print("\n=== ¡Listo! ===")
    print("  Conversar por terminal:  jarvis chat")
    print("  Revisar configuración:   jarvis estado")
    if get_settings().telegram_bot_token:
        print("  Vincular Telegram:       jarvis link-code   y luego   jarvis telegram")
    print()


def cmd_estado(args) -> None:
    s = get_settings()
    print(f"\nArchivo .env:  {ENV_FILE} {'' if ENV_FILE.exists() else '(NO EXISTE — ejecuta: jarvis setup)'}")
    print(f"Base de datos: {s.database_url}")
    print(f"Modelo:        {s.claude_model}\n")

    print(f"{OK if s.jarvis_master_key else FAIL} Clave de cifrado")
    key_ok = bool(s.anthropic_api_key) and not s.anthropic_api_key.startswith("sk-ant-...")
    print(f"{OK if key_ok else FAIL} API key de Anthropic")
    print(f"{OK if s.telegram_bot_token else WARN} Token de Telegram {'' if s.telegram_bot_token else '(opcional)'}")

    _db()
    with session_scope() as session:
        users = list(session.scalars(select(User).order_by(User.id)))
        print(f"{OK if users else FAIL} Usuarios: {len(users)}")
        for u in users:
            from jarvis.connectors import tasks_backend_name
            from jarvis.models import ChannelLink

            backend = tasks_backend_name(session, u.id)
            links = session.scalar(select(func.count()).select_from(ChannelLink).where(ChannelLink.user_id == u.id))
            print(f"     · {u.id} {u.name}: tareas en {'Personal Hub' if backend == 'personal_hub' else 'modo local'}, "
                  f"Telegram {'vinculado' if links else 'sin vincular'}")
            if backend == "personal_hub" and not args.skip_test:
                ok, msg = _test_hub(session, u.id)
                print(f"       {OK if ok else WARN} {msg}")

    if key_ok and not args.skip_test:
        ok, msg = _test_claude()
        print(f"{OK if ok else FAIL} {msg}")
    print()


def cmd_gen_key(args) -> None:
    print("Agrega esto a tu .env (y guárdalo en un lugar seguro; si lo pierdes, las credenciales no se pueden descifrar):\n")
    print(f"JARVIS_MASTER_KEY={generate_key()}")


def cmd_init_db(args) -> None:
    _db()
    print("Base de datos lista.")


def cmd_create_user(args) -> None:
    _db()
    with session_scope() as s:
        user = accounts.create_user(s, name=args.name, email=args.email, timezone=args.timezone,
                                    assistant_name=args.assistant_name)
        print(f"Usuario creado: id={user.id} · {user.name}")


def cmd_set_hub(args) -> None:
    _db()
    with session_scope() as s:
        user = _resolve_user(s, args.user)
        accounts.set_credential(s, user.id, "personal_hub", args.token, base_url=args.url)
        ok, msg = _test_hub(s, user.id)
    print("Personal Hub configurado (token cifrado en la BD).")
    print(f"{OK if ok else WARN} {msg}")


def cmd_unset_hub(args) -> None:
    _db()
    with session_scope() as s:
        user = _resolve_user(s, args.user)
        removed = accounts.remove_credential(s, user.id, "personal_hub")
    print("Personal Hub desconectado: las tareas vuelven al modo local." if removed else "No estaba conectado.")


def cmd_link_code(args) -> None:
    _db()
    with session_scope() as s:
        user = _resolve_user(s, args.user)
        code = accounts.new_link_code(s, user.id, args.channel)
    print(f"Código: {code}  (vence en {accounts.LINK_CODE_MINUTES} min)")
    print(f"En Telegram envía a tu bot:  /vincular {code}")


def cmd_settings(args) -> None:
    _db()
    with session_scope() as s:
        user = _resolve_user(s, args.user)
        st = user.settings or UserSettings(user_id=user.id)
        s.add(st)
        if args.name is not None:
            st.assistant_name = args.name
        if args.model is not None:
            st.model = args.model or None
        if args.prompt_extra is not None:
            st.prompt_extra = args.prompt_extra or None
        if args.timezone is not None:
            user.timezone = args.timezone
        if args.tools is not None:
            st.enabled_tools = [t.strip() for t in args.tools.split(",") if t.strip()] or None
        s.flush()
        print(f"Asistente: {st.assistant_name}")
        print(f"Modelo:    {st.model or get_settings().claude_model + ' (sistema)'}")
        print(f"Zona:      {user.timezone}")
        print(f"Tools:     {', '.join(st.enabled_tools) if st.enabled_tools else 'todas'}")
        print(f"Prompt+:   {st.prompt_extra or '—'}")


def cmd_users(args) -> None:
    _db()
    with session_scope() as s:
        for u in s.scalars(select(User).order_by(User.id)):
            providers = ", ".join(s.scalars(select(Credential.provider).where(Credential.user_id == u.id))) or "local"
            print(f"{u.id:>3}  {u.name:<20} {u.email or '':<30} servicios: {providers}")


def cmd_usage(args) -> None:
    _db()
    since = utcnow() - timedelta(days=args.days)
    with session_scope() as s:
        user = _resolve_user(s, args.user)
        rows = s.execute(
            select(UsageLog.model, func.count(), func.sum(UsageLog.input_tokens), func.sum(UsageLog.output_tokens))
            .where(UsageLog.user_id == user.id, UsageLog.created_at >= since)
            .group_by(UsageLog.model)
        ).all()
    if not rows:
        print("Sin consumo en ese periodo.")
        return
    print(f"Consumo de los últimos {args.days} días (usuario {user.id}):")
    for model, calls, tin, tout in rows:
        print(f"  {model:<28} llamadas={calls:<5} entrada={tin or 0:<9} salida={tout or 0}")


def cmd_logs(args) -> None:
    _db()
    with session_scope() as s:
        user = _resolve_user(s, args.user)
        rows = list(s.scalars(
            select(ToolLog).where(ToolLog.user_id == user.id).order_by(ToolLog.id.desc()).limit(args.limit)
        ))
    if not rows:
        print("Todavía no se ha ejecutado ninguna herramienta.")
    for r in reversed(rows):
        when = r.created_at.strftime("%Y-%m-%d %H:%M")
        print(f"{when} [{r.channel}] {r.tool_name:<26} {r.status:<18} {r.duration_ms:>5}ms  {r.tool_input}")


def _check_ready() -> None:
    s = get_settings()
    if not s.anthropic_api_key or not s.jarvis_master_key:
        sys.exit("JARVIS no está configurado todavía. Ejecuta primero:  jarvis setup")


def cmd_chat(args) -> None:
    from jarvis.app import build_orchestrator, setup_logging
    from jarvis.channels.terminal import run_terminal

    _check_ready()
    setup_logging()
    orchestrator = build_orchestrator()
    with session_scope() as s:
        user = _resolve_user(s, args.user)
        user_id, name = user.id, user.name
    run_terminal(orchestrator, user_id, name)


def cmd_telegram(args) -> None:
    from jarvis.app import build_orchestrator, setup_logging
    from jarvis.channels.telegram_bot import run_telegram

    _check_ready()
    setup_logging()
    print("Bot de Telegram en marcha. Déjalo abierto; Ctrl+C para detenerlo.")
    run_telegram(get_settings().telegram_bot_token, build_orchestrator())


# ------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jarvis", description="Asistente personal JARVIS",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="comando")

    def user_arg(c):
        c.add_argument("--user", type=int, help="id del usuario (opcional si solo hay uno)")

    c = sub.add_parser("setup", help="Asistente de configuración inicial")
    c.add_argument("--api-key", help="API key de Anthropic (si no, se pregunta)")
    c.add_argument("--telegram-token")
    c.add_argument("--name", help="Tu nombre")
    c.add_argument("--assistant-name")
    c.add_argument("--yes", action="store_true", help="No hacer preguntas opcionales")
    c.add_argument("--skip-test", action="store_true", help="No probar la conexión con Claude")
    c.set_defaults(func=cmd_setup)

    c = sub.add_parser("estado", aliases=["status"], help="Revisa la configuración")
    c.add_argument("--skip-test", action="store_true", help="No hacer llamadas de red")
    c.set_defaults(func=cmd_estado)

    c = sub.add_parser("chat", help="Conversar por terminal")
    user_arg(c)
    c.set_defaults(func=cmd_chat)

    sub.add_parser("telegram", help="Arranca el bot de Telegram").set_defaults(func=cmd_telegram)

    c = sub.add_parser("link-code", help="Código para vincular Telegram")
    user_arg(c)
    c.add_argument("--channel", default="telegram")
    c.set_defaults(func=cmd_link_code)

    c = sub.add_parser("set-hub", help="Conecta Personal Hub (Laravel)")
    user_arg(c)
    c.add_argument("--url", required=True, help="URL base de Laravel, ej. http://localhost:8000")
    c.add_argument("--token", required=True, help="Token de `php artisan assistant:token`")
    c.set_defaults(func=cmd_set_hub)

    c = sub.add_parser("unset-hub", help="Desconecta Personal Hub y vuelve al modo local")
    user_arg(c)
    c.set_defaults(func=cmd_unset_hub)

    c = sub.add_parser("settings", help="Ver o cambiar la personalización del asistente")
    user_arg(c)
    c.add_argument("--name", help="Nombre del asistente")
    c.add_argument("--model", help="Modelo para este usuario ('' = el del sistema)")
    c.add_argument("--prompt-extra", help="Tono y reglas propias ('' para borrar)")
    c.add_argument("--timezone")
    c.add_argument("--tools", help="Lista separada por comas ('' = todas)")
    c.set_defaults(func=cmd_settings)

    c = sub.add_parser("create-user", help="Crea un usuario")
    c.add_argument("--name", required=True)
    c.add_argument("--email")
    c.add_argument("--timezone", default="America/Bogota")
    c.add_argument("--assistant-name", default="Jarvis")
    c.set_defaults(func=cmd_create_user)

    sub.add_parser("users", help="Lista usuarios").set_defaults(func=cmd_users)

    c = sub.add_parser("usage", help="Consumo de tokens")
    user_arg(c)
    c.add_argument("--days", type=int, default=30)
    c.set_defaults(func=cmd_usage)

    c = sub.add_parser("logs", help="Últimas herramientas ejecutadas")
    user_arg(c)
    c.add_argument("--limit", type=int, default=20)
    c.set_defaults(func=cmd_logs)

    sub.add_parser("gen-key", help="Genera una clave maestra de cifrado").set_defaults(func=cmd_gen_key)
    sub.add_parser("init-db", help="Crea las tablas").set_defaults(func=cmd_init_db)
    return p


def main(argv: list[str] | None = None) -> None:
    # Consolas de Windows antiguas: evita errores con tildes y emojis.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
