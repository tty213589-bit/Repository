# Security Notice

Public website code must not contain real passwords, API keys, tokens, router credentials, or other secrets.

Client-side password checks are not security. Admin access must be enforced server-side with authenticated sessions and authorization checks.

If a secret was ever committed publicly, rotate it immediately and remove it from Git history where practical.
