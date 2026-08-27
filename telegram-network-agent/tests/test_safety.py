import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReadOnlySafetyTests(unittest.TestCase):
    def test_network_module_has_no_router_write_methods(self):
        source = (ROOT / "network.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_methods = {"set", "add", "remove"}
        forbidden_commands = {
            "/system/reboot",
            "system/reboot",
            "/ip/firewall",
            "/system/shutdown",
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

    def test_api_ssl_is_encrypted(self):
        source = (ROOT / "network.py").read_text(encoding="utf-8")
        self.assertIn("use_ssl=True", source)
        self.assertIn('transport: str = "api_ssl"', source)

    def test_bot_fails_closed_without_allowlist(self):
        source = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertIn("if not ALLOWED_CHATS and not ALLOWED_USERS", source)
        self.assertIn("CHECK_COOLDOWN_SECONDS", source)
        self.assertIn("asyncio.Lock", source)

    def test_only_interface_read_is_used_for_mikrotik(self):
        source = (ROOT / "network.py").read_text(encoding="utf-8")
        self.assertIn('get_resource("/interface")', source)
        self.assertIn("interfaces.get", source)


if __name__ == "__main__":
    unittest.main()
