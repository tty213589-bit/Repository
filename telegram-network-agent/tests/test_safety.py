import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReadOnlySafetyTests(unittest.TestCase):
    def test_network_module_has_no_router_write_methods(self):
        source = (ROOT / "network.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_methods = {"set", "add", "remove", "call"}
        forbidden_commands = {
            "/system/reboot",
            "system/reboot",
            "/ip/firewall",
            "/system/shutdown",
            "/interface/disable",
            "/interface/enable",
            "/ppp/secret",
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(
                    node.func.attr,
                    forbidden_methods,
                    f"Forbidden RouterOS write-style method found: {node.func.attr}",
                )

        lowered = source.lower()
        for command in forbidden_commands:
            self.assertNotIn(command, lowered)

    def test_api_ssl_is_encrypted_and_plaintext_port_is_blocked(self):
        source = (ROOT / "network.py").read_text(encoding="utf-8")
        self.assertIn("use_ssl=True", source)
        self.assertIn("Plaintext MikroTik API port 8728 is not allowed", source)
        self.assertIn('transport: str = "api_ssl"', source)

    def test_only_interface_read_is_used_for_mikrotik(self):
        source = (ROOT / "network.py").read_text(encoding="utf-8")
        self.assertIn('get_resource("/interface")', source)
        self.assertIn("interfaces.get", source)
        self.assertNotIn("get_resource(\"/system", source)
        self.assertNotIn("get_resource(\"/ip/firewall", source)

    def test_shared_credentials_are_cloud_environment_only(self):
        source = (ROOT / "network.py").read_text(encoding="utf-8")
        self.assertIn('os.getenv("MIKROTIK_USERNAME")', source)
        self.assertIn('os.getenv("MIKROTIK_PASSWORD")', source)
        self.assertNotIn("password: str", source)

    def test_bot_fails_closed_and_rate_limits_router_checks(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("if not ALLOWED_CHATS and not ALLOWED_USERS", source)
        self.assertIn("CHECK_COOLDOWN_SECONDS", source)
        self.assertIn("asyncio.Lock", source)
        self.assertIn("router_visible_to_chat", source)

    def test_wifi_button_flow_exists(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("InlineKeyboardButton", source)
        self.assertIn("CallbackQueryHandler", source)
        self.assertIn('callback_data=f"wifi:', source)

    def test_ruijie_is_disabled_in_active_bot_path(self):
        bot_source = (ROOT / "bot.py").read_text(encoding="utf-8").lower()
        network_source = (ROOT / "network.py").read_text(encoding="utf-8").lower()
        self.assertNotIn("ruijie_status", bot_source)
        self.assertNotIn("ruijie_status", network_source)

    def test_ai_prompt_protects_credentials_and_scope(self):
        source = (ROOT / "agent.py").read_text(encoding="utf-8")
        self.assertIn("Internet/Wi-Fi customer support assistant", source)
        self.assertIn("Never request or reveal passwords", source)
        self.assertIn("public router IPs", source)
        self.assertIn("only help with Internet and Wi-Fi", source)


if __name__ == "__main__":
    unittest.main()
