# MikroTik-only private configuration

Keep every real value below in the cloud provider's encrypted environment variables. Do not commit real router IPs, usernames, passwords, Telegram tokens, or OpenAI keys to GitHub.

## Required private variables

- `TELEGRAM_BOT_TOKEN` — Telegram bot token.
- `ALLOWED_TELEGRAM_CHAT_IDS` — approved customer group/chat IDs, comma-separated.
- `ALLOWED_TELEGRAM_USER_IDS` — optional owner/admin Telegram user IDs for private use.
- `MIKROTIK_USERNAME` — one shared MikroTik username used by all routers.
- `MIKROTIK_PASSWORD` — one shared MikroTik password used by all routers.
- `ROUTERS_JSON` — private Wi-Fi-to-router mapping shown below.
- `CHECK_COOLDOWN_SECONDS` — optional; default 15 seconds.
- `OPENAI_API_KEY` — optional; enables full Internet-only AI conversation.
- `OPENAI_MODEL` — optional; default `gpt-4.1-mini`.

## ROUTERS_JSON shape

Use a different `host` for each router/Wi-Fi while keeping the shared username/password only in `MIKROTIK_USERNAME` and `MIKROTIK_PASSWORD`.

```json
{
  "routers": [
    {
      "wifi_names": ["WIFI-NAME-1"],
      "customer_name": "Customer 1",
      "host": "PUBLIC-IP-OR-DNS-1",
      "port": 8729,
      "verify_tls": true,
      "wan_interface": "pppoe-out1",
      "plan_download_mbps": 60,
      "plan_upload_mbps": 60,
      "allowed_chat_ids": [-1001111111111]
    },
    {
      "wifi_names": ["WIFI-NAME-2"],
      "customer_name": "Customer 2",
      "host": "PUBLIC-IP-OR-DNS-2",
      "port": 8729,
      "verify_tls": true,
      "wan_interface": "pppoe-out1",
      "plan_download_mbps": 60,
      "plan_upload_mbps": 60,
      "allowed_chat_ids": [-1002222222222]
    }
  ]
}
```

If your API-SSL service uses a custom encrypted port, put that custom port in `port`. Plaintext API port 8728 is blocked by the bot.

## Customer flow

1. Customer sends a normal Internet/Wi-Fi question and receives an automatic Internet-only answer.
2. For slow/no-Internet complaints, the bot asks which Wi-Fi to check.
3. The customer taps a Wi-Fi button.
4. The button maps privately to that Wi-Fi's router host/IP.
5. The bot opens an encrypted API-SSL session and reads only the configured interface counters/state.
6. The bot replies with current traffic and interface status. It never shows the router public IP or login credentials.

## Safety rules

- MikroTik checks are read-only.
- No reboot, shutdown, firewall edit, PPP edit, interface enable/disable, or router configuration commands are present.
- One check per router can run at a time.
- A cooldown prevents repeated queries from hammering a live router.
- Only approved Telegram chats/users can use the bot.
- Customer AI replies never receive MikroTik credentials or router IP addresses.
- Ruijie/Reyee is intentionally disabled until explicitly enabled later.
