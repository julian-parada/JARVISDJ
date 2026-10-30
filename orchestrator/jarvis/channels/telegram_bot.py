"""Canal de Telegram: un solo bot, muchos usuarios (vinculados por código)."""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatAction, ChatType
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from jarvis.accounts import redeem_link_code, unlink_channel, user_for_channel
from jarvis.db import session_scope
from jarvis.orchestrator import Orchestrator

log = logging.getLogger("jarvis.telegram")
CHANNEL = "telegram"
TELEGRAM_LIMIT = 4000

NOT_LINKED = (
    "Hola 👋 Este chat aún no está vinculado a ninguna cuenta.\n\n"
    "Genera un código en tu computador con:\n"
    "`jarvis link-code`\n\n"
    "y envíamelo así: `/vincular CODIGO`"
)


def _user_id_for(chat_id: int) -> int | None:
    with session_scope() as session:
        user = user_for_channel(session, CHANNEL, str(chat_id))
        return user.id if user and user.active else None


def build_application(token: str, orchestrator: Orchestrator) -> Application:
    app = Application.builder().token(token).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if _user_id_for(update.effective_chat.id):
            await update.message.reply_text("Ya estás vinculado. Escríbeme lo que necesites. /nuevo reinicia la conversación.")
        else:
            await update.message.reply_text(NOT_LINKED, parse_mode="Markdown")

    async def vincular(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type != ChatType.PRIVATE:
            await update.message.reply_text("Por seguridad, la vinculación solo funciona en chat privado.")
            return
        if not context.args:
            await update.message.reply_text("Uso: /vincular CODIGO")
            return
        with session_scope() as session:
            user = redeem_link_code(session, context.args[0], CHANNEL, str(update.effective_chat.id))
            name = user.name if user else None
        if name:
            await update.message.reply_text(f"Listo, {name}. Quedaste vinculado. Pregúntame qué tienes pendiente.")
        else:
            await update.message.reply_text("Código inválido o vencido. Genera uno nuevo.")

    async def desvincular(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        with session_scope() as session:
            ok = unlink_channel(session, CHANNEL, str(update.effective_chat.id))
        await update.message.reply_text("Chat desvinculado." if ok else "Este chat no estaba vinculado.")

    async def nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = _user_id_for(update.effective_chat.id)
        if user_id is None:
            await update.message.reply_text(NOT_LINKED, parse_mode="Markdown")
            return
        orchestrator.reset_context(user_id)
        await update.message.reply_text("Conversación reiniciada.")

    async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat.type != ChatType.PRIVATE:
            return
        user_id = _user_id_for(update.effective_chat.id)
        if user_id is None:
            await update.message.reply_text(NOT_LINKED, parse_mode="Markdown")
            return

        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        try:
            # El orquestador es síncrono (HTTP + BD): lo corremos en un hilo para no bloquear el bot.
            reply = await asyncio.to_thread(orchestrator.handle, user_id, update.message.text, CHANNEL)
        except Exception:
            log.exception("Error procesando mensaje de Telegram")
            await update.message.reply_text("Tuve un problema procesando eso. Intenta de nuevo en un momento.")
            return

        for chunk in _chunks(reply.text or "…"):
            await update.message.reply_text(chunk)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("vincular", vincular))
    app.add_handler(CommandHandler("desvincular", desvincular))
    app.add_handler(CommandHandler("nuevo", nuevo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def run_telegram(token: str, orchestrator: Orchestrator) -> None:
    if not token:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en el .env")
    log.info("Bot de Telegram iniciado (long polling)")
    build_application(token, orchestrator).run_polling(allowed_updates=Update.ALL_TYPES)


def _chunks(text: str, size: int = TELEGRAM_LIMIT) -> list[str]:
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]
