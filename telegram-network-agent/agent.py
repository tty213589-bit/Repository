from __future__ import annotations

import os
import re
from dataclasses import dataclass

from openai import AsyncOpenAI


@dataclass
class Complaint:
    wifi_name: str | None
    needs_check: bool


def parse_complaint(text: str, known_wifi_names: list[str]) -> Complaint:
    lower = text.casefold()
    matches = [name for name in known_wifi_names if name.casefold() in lower]
    wifi = max(matches, key=len) if matches else None
    if not wifi:
        match = re.search(r"(?:wifi|wi-fi|ssid)\s*(?:name)?\s*[:=-]?\s*([^,\n]+)", text, re.I)
        wifi = match.group(1).strip() if match else None

    check_words = (
        "slow", "lag", "no internet", "offline", "not working", "disconnect",
        "check internet", "check wifi", "check wi-fi", "internet problem",
        "អ៊ីនធឺណិតយឺត", "យឺត", "អត់អ៊ីនធឺណិត",
    )
    return Complaint(wifi_name=wifi, needs_check=any(word in lower for word in check_words))


def compose_reply(customer: str, wifi: str, traffic: dict) -> str:
    rx = traffic.get("rx_mbps", 0.0)
    tx = traffic.get("tx_mbps", 0.0)
    down = traffic.get("plan_download_mbps", 0.0)
    running = traffic.get("interface_running", False)
    disabled = traffic.get("interface_disabled", False)
    utilization = (rx / down * 100) if down else 0

    if disabled:
        finding = "The Internet interface is disabled. Please contact support."
    elif not running:
        finding = "The Internet interface is not currently running. Please contact support."
    elif utilization >= 80:
        finding = "The connection is currently using a high amount of its download limit."
    elif utilization >= 40:
        finding = "The connection is moderately busy right now."
    else:
        finding = "The MikroTik Internet interface is running and traffic looks normal right now."

    return (
        f"Internet check for {customer} ({wifi})\n"
        f"Download: {rx:.2f} Mbps / Upload: {tx:.2f} Mbps\n"
        f"{finding}\n\n"
        "✅ Safe read-only check. No router settings were changed."
    )


SYSTEM_PROMPT = """You are a friendly Telegram customer-support assistant.

You may answer normal customer questions and friendly small talk naturally, including greetings,
"how are you" messages, basic general questions, and Internet/Wi-Fi support. Keep replies concise,
warm, professional, and easy to understand.

Reply in the same language the customer uses when practical. Do not respond in Thai. If a customer
writes in Thai, reply in simple English instead.

Do not invent business-specific facts that were not provided to you, such as exact prices, stock,
order status, opening hours, warranties, account balances, payment status, or delivery dates. When
such information is unknown, say that the support team can confirm it.

For Internet/Wi-Fi support, you may explain speed, latency, connectivity, routers, customer devices,
and basic safe troubleshooting. Never claim that you performed a live router check unless the bot
actually ran its read-only MikroTik check.

Never request or reveal passwords, MikroTik credentials, API keys, OTP codes, public router IPs,
or private network configuration. Never instruct a customer to factory-reset a router, disable an
interface, edit firewall rules, reboot networking equipment, or make any change that could disconnect
service. If a live Internet status check is needed, tell the customer to use the Wi-Fi buttons in the bot.
"""


def fallback_customer_reply(text: str) -> str:
    lower = text.casefold().strip()

    if lower in {"hi", "hello", "hey", "សួស្តី"}:
        return "Hello 👋 What can we help you with today?"

    if any(phrase in lower for phrase in ("how are you", "how r u", "how are u")):
        return "I'm good, thank you 😊 What brings you here today?"

    if any(word in lower for word in ("password", "wifi password", "wi-fi password", "otp", "api key")):
        return "For security, I can't reveal passwords, OTP codes, API keys, or private account details."

    if any(word in lower for word in ("slow", "lag", "no internet", "offline", "not working")):
        return "I can check the MikroTik connection safely. Please choose your Wi-Fi from the buttons."

    if any(word in lower for word in ("speed", "mbps", "latency", "ping", "wifi", "wi-fi", "internet", "router", "network")):
        return "I can help with that Internet/Wi-Fi question. If you want a live connection check, choose your Wi-Fi from the buttons."

    return "Thanks for your message 😊 How can we help you today?"


async def answer_customer_question(text: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return fallback_customer_reply(text)

    client = AsyncOpenAI(api_key=api_key)
    try:
        response = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            temperature=0.4,
            max_tokens=350,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text[:2000]},
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        return content or fallback_customer_reply(text)
    except Exception:
        return fallback_customer_reply(text)


# Backward-compatible name for older deployments/imports.
answer_internet_question = answer_customer_question
