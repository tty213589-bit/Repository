# Security Policy

## Protect live systems

This project may relate to public websites, Telegram bots, customer support,
MikroTik routers, or Ruijie/Reyee Cloud.

- Do not test this code against any live customer network, bot, group, router,
  device, deployment, or account without the owner's explicit permission.
- Do not attempt to interrupt, reboot, reconfigure, scan, or access customer
  systems.
- Do not publish credentials, tokens, IP addresses, customer information,
  private messages, logs, or configuration files.
- Report suspected vulnerabilities privately to the repository owner through a
  verified private contact channel. Do not include sensitive details in a
  public issue.

## Secrets

Runtime secrets must be supplied through private environment variables or a
local ignored configuration file. Never commit a real `.env` file, Telegram
token, MikroTik password, Ruijie App Secret, API key, session file, or private
certificate.

If a secret is exposed, treat it as compromised and replace or restrict it
before using the affected integration. Never rotate an active production
credential until a tested replacement is ready, to avoid service interruption.

## Supported version

Only the latest version on the default branch is supported.