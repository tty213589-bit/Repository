import importlib
import json
import os
import sys
import unittest


class MikroTikBotFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_env = dict(os.environ)
        os.environ.update(
            {
                "ALLOWED_TELEGRAM_CHAT_IDS": "1001,1002",
                "ALLOWED_TELEGRAM_USER_IDS": "9999",
                "MIKROTIK_USERNAME": "shared-readonly-user",
                "MIKROTIK_PASSWORD": "test-only-not-real",
                "ROUTERS_JSON": json.dumps(
                    {
                        "routers": [
                            {
                                "wifi_names": ["KTV-A"],
                                "customer_name": "Test A",
                                "host": "203.0.113.10",
                                "wan_interface": "pppoe-out1",
                                "plan_download_mbps": 100,
                                "plan_upload_mbps": 100,
                                "port": 8729,
                                "verify_tls": False,
                                "allowed_chat_ids": [1001],
                            },
                            {
                                "wifi_names": ["KTV-B"],
                                "customer_name": "Test B",
                                "host": "198.51.100.20",
                                "wan_interface": "pppoe-out1",
                                "plan_download_mbps": 60,
                                "plan_upload_mbps": 60,
                                "port": 8729,
                                "verify_tls": False,
                                "allowed_chat_ids": [1002],
                            },
                        ]
                    }
                ),
            }
        )
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        for name in ("bot", "network", "agent"):
            sys.modules.pop(name, None)
        cls.bot = importlib.import_module("bot")
        cls.network = importlib.import_module("network")

    @classmethod
    def tearDownClass(cls):
        os.environ.clear()
        os.environ.update(cls._old_env)

    def test_two_wifi_names_map_to_different_hosts(self):
        router_a, wifi_a = self.bot.find_router("KTV-A", 1001)
        router_b, wifi_b = self.bot.find_router("KTV-B", 1002)
        self.assertEqual(wifi_a, "KTV-A")
        self.assertEqual(wifi_b, "KTV-B")
        self.assertNotEqual(router_a.host, router_b.host)

    def test_each_customer_chat_only_sees_its_own_wifi(self):
        self.assertIsNotNone(self.bot.find_router("KTV-A", 1001))
        self.assertIsNone(self.bot.find_router("KTV-B", 1001))
        self.assertIsNotNone(self.bot.find_router("KTV-B", 1002))
        self.assertIsNone(self.bot.find_router("KTV-A", 1002))

    def test_wifi_button_menu_is_scoped_per_chat(self):
        menu_a = self.bot.wifi_keyboard(1001)
        menu_b = self.bot.wifi_keyboard(1002)
        text_a = [button.text for row in menu_a.inline_keyboard for button in row]
        text_b = [button.text for row in menu_b.inline_keyboard for button in row]
        self.assertEqual(text_a, ["📶 KTV-A"])
        self.assertEqual(text_b, ["📶 KTV-B"])

    def test_shared_credentials_are_used_without_network_connection(self):
        router_a = self.bot.ROUTERS[0]
        router_b = self.bot.ROUTERS[1]
        client_a = self.network.MikroTikReadOnly(router_a)
        client_b = self.network.MikroTikReadOnly(router_b)
        self.assertEqual(client_a.username, "shared-readonly-user")
        self.assertEqual(client_b.username, "shared-readonly-user")
        self.assertEqual(client_a.password, "test-only-not-real")
        self.assertEqual(client_b.password, "test-only-not-real")
        self.assertEqual(router_a.port, 8729)
        self.assertEqual(router_b.port, 8729)

    def test_plaintext_api_port_is_rejected(self):
        bad = self.network.Router(
            wifi_names=["BAD"],
            customer_name="Bad",
            host="192.0.2.10",
            wan_interface="pppoe-out1",
            plan_download_mbps=10,
            plan_upload_mbps=10,
            port=8728,
            verify_tls=False,
        )
        with self.assertRaises(RuntimeError):
            self.network.MikroTikReadOnly(bad)


if __name__ == "__main__":
    unittest.main()
