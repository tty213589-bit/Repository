from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agent import answer_internet_question, compose_reply, parse_complaint
from network import MikroTikReadOnly, Router

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def ids(name: str) -> set[int]:
    return {int(x.strip()) for x in os.getenv(name, "").split(",") if x.strip()}


def positive_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


ALLOWED_CHATS = ids("ALLOWED_TELEGRAM_CHAT_IDS")
ALLOWED_USERS = ids("ALLOWED_TELEGRAM_USER_IDS")
CHECK_COOLDOWN_SECONDS = positive_int_env("CHECK_COOLDOWN_SECONDS", 15, 10, 300)
ROUTER_LOCKS: dict[str, asyncio.Lock] = {}
LAST_CHECK_AT: dict[str, float] = {}


def load_routers() -> list[Router]:
    routers_json = os.getenv("ROUTERS_JSON", "").strip()
    if routers_json:
        raw = json.loads(routers_json)
    else:
        path = Path(os.getenv("ROUTERS_FILE", "routers.yaml"))
        if not path.exists():
            return []
        raw = yaml.safe_load(path.read_text()) or {}
    return [Router(**item) for item in raw.get("routers", [])]


ROUTERS = load_routers()


def authorized(update: Update) -> bool:
    """Allow anyone inside an approved customer chat, or an explicitly approved user."""
    if not ALLOWED_CHATS and not ALLOWED_USERS:
        return False
    if not update.effective_chat or not update.effective_user:
        return False
    return (
        update.effective_chat.id in ALLOWED_CHATS
        or update.effective_user.id in ALLOWED_USERS
    )


def router_visible_to_chat(router: Router, chat_id: int) -> bool:
    return not router.allowed_chat_ids or chat_id in set(router.allowed_chat_ids)


def find_router(wifi: str, chat_id: int) -> tuple[Router, str] | None:
    value = wifi.casefold().strip()
    for router in ROUTERS:
        if not router_visible_to_chat(router, chat_id):
            continue
        for name in router.wifi_names:
            if value == name.casefold().strip():
                return router, name
    return None


def router_key(router: Router) -> str:
    return f"{router.host}:{router.port}:{router.wan_interface}"


def wifi_keyboard(chat_id: int) -> InlineKeyboardMarkup | None:
    buttons: list[InlineKeyboardButton] = []
    for router_index, router in enumerate(ROUTERS):
        if not router_visible_to_chat(router, chat_id):
            continue
        for wifi_index, wifi in enumerate(router.wifi_names):
            buttons.append(
                InlineKeyboardButton(
                    text=f"📶 {wifi}",
                    callback_data=f"wifi:{router_index}:{wifi_index}",
                )
            )
    if not buttons:
        return None
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)


async def show_wifi_menu(message, chat_id: int) -> None:
    keyboard = wifi_keyboard(chat_id)
    if keyboard is None:
        await message.reply_text("No Wi-Fi service is configured for this chat yet.")
        return
    await message.reply_text(
        "Which Wi-Fi would you like me to check?",
        reply_markup=keyboard,
    )


async def run_router_check(message, router: Router, wifi: str) -> None:
    key = router_key(router)
    lock = ROUTER_LOCKS.setdefault(key, asyncio.Lock())

    if lock.locked():
        await message.reply_text(
            "A safe read-only check is already running for this Wi-Fi. Please wait."
        )
        return

    remaining = CHECK_COOLDOWN_SECONDS - (time.monotonic() - LAST_CHECK_AT.get(key, 0.0))
    if remaining > 0:
        await message.reply_text(
            f"Safety cooldown active. Please wait {int(remaining) + 1} seconds before checking again."
        )
        return

    async with lock:
        LAST_CHECK_AT[key] = time.monotonic()
        await message.reply_text(f"Checking {wifi} safely (read-only)…")
        client: MikroTikReadOnly | None = None
        try:
            client = MikroTikReadOnly(router)
            traffic = await client.sample_traffic()
            await message.reply_text(compose_reply(router.customer_name, wifi, traffic))
        except Exception as exc:
            logging.error("Read-only MikroTik check failed: %s", type(exc).__name__)
            await message.reply_text(
                "I could not complete the safe Internet check right now. "
                "No router settings were changed. Please contact support if the problem continues."
            )
        finally:
            if client is not None:
                await client.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await update.message.reply_text(
        "Hello 👋 I am your Internet/Wi-Fi support bot. I can answer Internet questions "
        "and safely check MikroTik connection status. I cannot reboot, disconnect, or change router settings."
    )
    await show_wifi_menu(update.message, update.effective_chat.id)


async def check_wifi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return

    wifi = " ".join(context.args).strip()
    if not wifi:
        await show_wifi_menu(update.message, update.effective_chat.id)
        return

    found = find_router(wifi, update.effective_chat.id)
    if not found:
        await update.message.reply_text("I cannot find that Wi-Fi name. Please choose from the buttons.")
        await show_wifi_menu(update.message, update.effective_chat.id)
        return

    router, canonical_wifi = found
    await run_router_check(update.message, router, canonical_wifi)


async def routers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await show_wifi_menu(update.message, update.effective_chat.id)


async def wifi_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update) or not update.callback_query:
        return

    query = update.callback_query
    await query.answer()
    if not query.message or not query.data:
        return

    try:
        _, router_index_raw, wifi_index_raw = query.data.split(":", 2)
        router_index = int(router_index_raw)
        wifi_index = int(wifi_index_raw)
        router = ROUTERS[router_index]
        wifi = router.wifi_names[wifi_index]
    except (ValueError, IndexError):
        await query.message.reply_text("That Wi-Fi button is no longer valid. Please try again.")
        return

    if not router_visible_to_chat(router, update.effective_chat.id):
        await query.message.reply_text("That Wi-Fi is not available in this chat.")
        return

    await run_router_check(query.message, router, wifi)


async def natural_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update) or not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    # If the customer typed an exact Wi-Fi name after being asked, check it directly.
    exact = find_router(text, chat_id)
    if exact:
        router, wifi = exact
        await run_router_check(update.message, router, wifi)
        return

    visible_names = [
        name
        for router in ROUTERS
        if router_visible_to_chat(router, chat_id)
        for name in router.wifi_names
    ]
    complaint = parse_complaint(text, visible_names)

    if complaint.needs_check:
        if complaint.wifi_name:
            found = find_router(complaint.wifi_name, chat_id)
            if found:
                router, wifi = found
                await run_router_check(update.message, router, wifi)
                return
        await show_wifi_menu(update.message, chat_id)
        return

    reply = await answer_internet_question(text)
    await update.message.reply_text(reply)


def validate_configuration() -> None:
    if not ALLOWED_CHATS and not ALLOWED_USERS:
        raise RuntimeError("At least one Telegram chat or user allow-list must be configured")
    if not ROUTERS:
        raise RuntimeError("No MikroTik routers are configured")
    if not os.getenv("MIKROTIK_USERNAME", "").strip():
        raise RuntimeError("MIKROTIK_USERNAME is missing")
    if not os.getenv("MIKROTIK_PASSWORD", "").strip():
        raise RuntimeError("MIKROTIK_PASSWORD is missing")

    for router in ROUTERS:
        if not router.host.strip():
            raise RuntimeError("A MikroTik router host is missing")
        if not router.wifi_names:
            raise RuntimeError("A MikroTik router has no Wi-Fi names")
        if router.port == 8728:
            raise RuntimeError("Plaintext MikroTik API port 8728 is not allowed")
        if (router.transport or "api_ssl").strip().lower() != "api_ssl":
            raise RuntimeError("Only encrypted MikroTik API-SSL is allowed")


def main() -> None:
    validate_configuration()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_wifi))
    app.add_handler(CommandHandler("routers", routers))
    app.add_handler(CallbackQueryHandler(wifi_button, pattern=r"^wifi:\d+:\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, natural_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
