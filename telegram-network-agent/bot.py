from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from agent import compose_reply, parse_complaint
from network import MikroTikReadOnly, Router, ruijie_status

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
    if not ALLOWED_CHATS and not ALLOWED_USERS:
        return False
    if not update.effective_chat or not update.effective_user:
        return False
    chat_ok = not ALLOWED_CHATS or update.effective_chat.id in ALLOWED_CHATS
    user_ok = not ALLOWED_USERS or update.effective_user.id in ALLOWED_USERS
    return chat_ok and user_ok


def find_router(wifi: str) -> Router | None:
    value = wifi.casefold().strip()
    for router in ROUTERS:
        if any(value == name.casefold() for name in router.wifi_names):
            return router
    return None


def router_key(router: Router) -> str:
    return f"{router.host}:{router.port}:{router.wan_interface}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        await update.message.reply_text("This bot is restricted to authorized staff.")
        return
    await update.message.reply_text(
        "Send /check followed by the Wi-Fi name. I perform read-only MikroTik "
        "and Ruijie/Reyee checks. I cannot reboot, disconnect, or change settings."
    )


async def check_wifi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        await update.message.reply_text("This network check is restricted to authorized staff.")
        return

    wifi = " ".join(context.args).strip()
    if not wifi:
        await update.message.reply_text("Please use: /check WiFi Name")
        return

    router = find_router(wifi)
    if not router:
        await update.message.reply_text("I cannot find that Wi-Fi name. Please check the spelling.")
        return

    key = router_key(router)
    lock = ROUTER_LOCKS.setdefault(key, asyncio.Lock())

    if lock.locked():
        await update.message.reply_text(
            "A safe read-only check is already running for this router. Please wait."
        )
        return

    remaining = CHECK_COOLDOWN_SECONDS - (time.monotonic() - LAST_CHECK_AT.get(key, 0.0))
    if remaining > 0:
        await update.message.reply_text(
            f"Safety cooldown active. Please wait {int(remaining) + 1} seconds before checking again."
        )
        return

    async with lock:
        LAST_CHECK_AT[key] = time.monotonic()
        await update.message.reply_text("Checking traffic and device status (read-only)…")
        client = MikroTikReadOnly(router)
        try:
            traffic = await client.sample_traffic()
            cloud = await ruijie_status(router.ruijie_project_id)
            await update.message.reply_text(
                compose_reply(router.customer_name, wifi, traffic, cloud)
            )
        except Exception as exc:
            logging.error("Read-only network check failed: %s", type(exc).__name__)
            await update.message.reply_text(
                f"I could not complete the safe read-only check: {type(exc).__name__}."
            )
        finally:
            await client.close()


async def routers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return
    names = [", ".join(r.wifi_names) for r in ROUTERS]
    await update.message.reply_text("Configured Wi-Fi names:\n" + "\n".join(names))


async def natural_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update) or not update.message or not update.message.text:
        return
    complaint = parse_complaint(
        update.message.text, [n for r in ROUTERS for n in r.wifi_names]
    )
    if complaint.is_slow and complaint.wifi_name:
        context.args = complaint.wifi_name.split()
        await check_wifi(update, context)
    elif complaint.is_slow:
        await update.message.reply_text("Please tell me the Wi-Fi name so I can check it.")


def validate_configuration() -> None:
    if not ALLOWED_CHATS and not ALLOWED_USERS:
        raise RuntimeError(
            "At least one Telegram allow-list must be configured before the bot can start"
        )
    if not ROUTERS:
        raise RuntimeError("No routers are configured")
    for router in ROUTERS:
        transport = (router.transport or "api_ssl").strip().lower()
        if transport == "api_ssl" and router.port == 8728:
            raise RuntimeError(
                "Unsafe MikroTik configuration: api_ssl cannot use plaintext API port 8728"
            )
        if transport == "rest" and router.port == 8729:
            raise RuntimeError(
                "Invalid MikroTik configuration: REST cannot use API-SSL port 8729"
            )


def main():
    validate_configuration()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_wifi))
    app.add_handler(CommandHandler("routers", routers))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, natural_message))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
