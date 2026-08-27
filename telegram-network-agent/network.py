from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field

import routeros_api


@dataclass
class Router:
    wifi_names: list[str]
    customer_name: str
    host: str
    wan_interface: str
    plan_download_mbps: float
    plan_upload_mbps: float
    port: int = 8729
    verify_tls: bool = True
    allowed_chat_ids: list[int] = field(default_factory=list)

    # Backward-compatible fields. Shared cloud credentials are preferred.
    username: str | None = None
    password_env: str | None = None
    transport: str = "api_ssl"
    ruijie_project_id: str | None = None


class MikroTikReadOnly:
    """Encrypted API-SSL MikroTik client that only reads interface state/counters."""

    def __init__(self, router: Router):
        self.router = router
        self.username = os.getenv("MIKROTIK_USERNAME") or router.username
        self.password = os.getenv("MIKROTIK_PASSWORD")
        if not self.password and router.password_env:
            self.password = os.getenv(router.password_env)

        if not self.username:
            raise RuntimeError("MIKROTIK_USERNAME is missing")
        if not self.password:
            raise RuntimeError("MIKROTIK_PASSWORD is missing")
        if (router.transport or "api_ssl").strip().lower() != "api_ssl":
            raise RuntimeError("Only encrypted MikroTik API-SSL is enabled")
        if router.port == 8728:
            raise RuntimeError("Plaintext MikroTik API port 8728 is not allowed")
        if not (1 <= int(router.port) <= 65535):
            raise RuntimeError("Invalid MikroTik API-SSL port")

    @staticmethod
    def _as_bool(value: object) -> bool:
        return str(value).strip().lower() in {"true", "yes", "1", "on"}

    def _sample_sync(self, seconds: float) -> tuple[int, int, int, int, float, bool, bool]:
        pool = routeros_api.RouterOsApiPool(
            self.router.host,
            username=self.username,
            password=self.password,
            port=int(self.router.port),
            plaintext_login=True,
            use_ssl=True,
            ssl_verify=self.router.verify_tls,
            ssl_verify_hostname=self.router.verify_tls,
        )
        pool.socket_timeout = 10.0
        try:
            api = pool.get_api()
            interfaces = api.get_resource("/interface")

            def read_once() -> tuple[int, int, bool, bool]:
                rows = interfaces.get(name=self.router.wan_interface)
                if not rows:
                    raise RuntimeError(f"Interface {self.router.wan_interface!r} not found")
                row = rows[0]
                return (
                    int(row.get("rx-byte", 0)),
                    int(row.get("tx-byte", 0)),
                    self._as_bool(row.get("running", False)),
                    self._as_bool(row.get("disabled", False)),
                )

            rx1, tx1, running1, disabled1 = read_once()
            started = time.monotonic()
            time.sleep(seconds)
            rx2, tx2, running2, disabled2 = read_once()
            elapsed = max(time.monotonic() - started, 0.1)
            return (
                rx1,
                tx1,
                rx2,
                tx2,
                elapsed,
                running1 and running2,
                disabled1 or disabled2,
            )
        finally:
            pool.disconnect()

    async def sample_traffic(self, seconds: float = 2.0) -> dict:
        rx1, tx1, rx2, tx2, elapsed, running, disabled = await asyncio.to_thread(
            self._sample_sync, seconds
        )
        return {
            "rx_mbps": max(0, rx2 - rx1) * 8 / elapsed / 1_000_000,
            "tx_mbps": max(0, tx2 - tx1) * 8 / elapsed / 1_000_000,
            "plan_download_mbps": self.router.plan_download_mbps,
            "plan_upload_mbps": self.router.plan_upload_mbps,
            "interface_running": running,
            "interface_disabled": disabled,
        }

    async def close(self) -> None:
        # API-SSL sessions are created and disconnected inside the worker thread.
        return None
