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


SYSTEM_PROMPT = """You are an Internet/Wi-Fi customer support assistant.
You may answer only questions about Internet service, Wi-Fi, network speed, latency,
connectivity, routers, customer devices connecting to Wi-Fi, and basic safe troubleshooting.
For unrelated topics, politely say you can only help with Internet/Wi-Fi service.
Never request or reveal passwords, MikroTik credentials, API keys, OTP codes, public router IPs,
or private network configuration. Never instruct a customer to factory-reset a router, disable
an interface, edit firewall rules, reboot networking equipment, or make any change that could
disconnect service. If a live status check is needed, tell the customer to use the Wi-Fi buttons
in the bot. Keep replies concise, friendly, and easy to understand.
"""


def fallback_internet_reply(text: str) -> str:
    lower = text.casefold().strip()
    if lower in {"hi", "hello", "hey", "សួស្តី"}:
        return "Hello 👋 I can help with your Internet or Wi-Fi service. What problem are you having?"
    if any(word in lower for word in ("password", "wifi password", "wi-fi password")):
        return "For security, I cannot reveal passwords. Please contact authorized support if you need Wi-Fi access help."
    if any(word in lower for word in ("slow", "lag", "no internet", "offline", "not working")):
        return "I can check the MikroTik connection safely. Please choose your Wi-Fi from the buttons."
    if any(word in lower for word in ("speed", "mbps", "latency", "ping", "wifi", "wi-fi", "internet", "router", "network")):
        return "I can help with that Internet/Wi-Fi question. If you want a live connection check, choose your Wi-Fi from the buttons."
    return "I can only help with Internet and Wi-Fi service questions."


async def answer_internet_question(text: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return fallback_internet_reply(text)

    client = AsyncOpenAI(api_key=api_key)
    try:
        response = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            temperature=0.2,
            max_tokens=300,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text[:2000]},
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        return content or fallback_internet_reply(text)
    except Exception:
        return fallback_internet_reply(text)
