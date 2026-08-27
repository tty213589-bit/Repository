from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass

import httpx
import routeros_api


@dataclass
class Router:
    wifi_names: list[str]
    customer_name: str
    host: str
    port: int
    username: str
    password_env: str
    verify_tls: bool
    wan_interface: str
    plan_download_mbps: float
    plan_upload_mbps: float
    ruijie_project_id: str | None = None
    transport: str = "api_ssl"


class MikroTikReadOnly:
    """Read-only MikroTik client with API-SSL or REST transport."""

    def __init__(self, router: Router):
        self.router = router
        self.password = os.getenv(router.password_env)
        if not self.password:
            raise RuntimeError(f"Missing environment variable: {router.password_env}")

        transport = (router.transport or "api_ssl").strip().lower()
        if transport not in {"api_ssl", "rest"}:
            raise RuntimeError("Unsupported MikroTik transport")
        self.transport = transport

        self.client: httpx.AsyncClient | None = None
        if self.transport == "rest":
            self.client = httpx.AsyncClient(
                base_url=f"https://{router.host}:{router.port}/rest",
                auth=(router.username, self.password),
                verify=router.verify_tls,
                timeout=httpx.Timeout(12.0, connect=8.0),
                follow_redirects=False,
            )

    async def _read_counter_rest(self) -> tuple[int, int]:
        if self.client is None:
            raise RuntimeError("REST client is not initialized")
        response = await self.client.get(
            "/interface", params={".proplist": "name,rx-byte,tx-byte"}
        )
        response.raise_for_status()
        for item in response.json():
            if item.get("name") == self.router.wan_interface:
                return int(item.get("rx-byte", 0)), int(item.get("tx-byte", 0))
        raise RuntimeError(f"Interface {self.router.wan_interface!r} not found")

    def _sample_api_ssl_sync(self, seconds: float) -> tuple[int, int, int, int, float]:
        pool = routeros_api.RouterOsApiPool(
            self.router.host,
            username=self.router.username,
            password=self.password,
            port=self.router.port,
            plaintext_login=True,
            use_ssl=True,
            ssl_verify=self.router.verify_tls,
            ssl_verify_hostname=self.router.verify_tls,
        )
        pool.socket_timeout = 10.0
        try:
            api = pool.get_api()
            interfaces = api.get_resource("/interface")

            def read_once() -> tuple[int, int]:
                rows = interfaces.get(name=self.router.wan_interface)
                if not rows:
                    raise RuntimeError(f"Interface {self.router.wan_interface!r} not found")
                row = rows[0]
                return int(row.get("rx-byte", 0)), int(row.get("tx-byte", 0))

            rx1, tx1 = read_once()
            started = time.monotonic()
            time.sleep(seconds)
            rx2, tx2 = read_once()
            elapsed = max(time.monotonic() - started, 0.1)
            return rx1, tx1, rx2, tx2, elapsed
        finally:
            pool.disconnect()

    async def sample_traffic(self, seconds: float = 2.0) -> dict:
        if self.transport == "api_ssl":
            rx1, tx1, rx2, tx2, elapsed = await asyncio.to_thread(
                self._sample_api_ssl_sync, seconds
            )
        else:
            rx1, tx1 = await self._read_counter_rest()
            started = time.monotonic()
            await asyncio.sleep(seconds)
            rx2, tx2 = await self._read_counter_rest()
            elapsed = max(time.monotonic() - started, 0.1)

        return {
            "rx_mbps": max(0, rx2 - rx1) * 8 / elapsed / 1_000_000,
            "tx_mbps": max(0, tx2 - tx1) * 8 / elapsed / 1_000_000,
            "plan_download_mbps": self.router.plan_download_mbps,
            "plan_upload_mbps": self.router.plan_upload_mbps,
        }

    async def close(self):
        if self.client is not None:
            await self.client.aclose()


async def ruijie_status(project_id: str | None) -> dict | None:
    base = os.getenv("RUIJIE_BASE_URL", "").rstrip("/")
    app_id, secret = os.getenv("RUIJIE_APP_ID"), os.getenv("RUIJIE_APP_SECRET")
    if not (base and app_id and secret and project_id):
        return None
    path = os.getenv("RUIJIE_STATUS_PATH", "/api/status")
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(12.0, connect=8.0),
        follow_redirects=False,
    ) as client:
        response = await client.get(
            f"{base}{path}",
            params={"project_id": project_id},
            headers={"X-App-Id": app_id, "X-App-Secret": secret},
        )
        response.raise_for_status()
        data = response.json()
        return {"summary": data.get("summary") or data.get("status") or "online"}
