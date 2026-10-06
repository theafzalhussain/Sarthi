"""Granular autonomous-action permission policy tests."""
from __future__ import annotations

import unittest

from saarthi.security.permissions import (
    PermissionEngine, PermissionMode, category_for,
)


class PermissionEngineTests(unittest.TestCase):
    def test_default_backwards_compatible_inherit_hai(self):
        decision = PermissionEngine({}).decide("unknown_tool")
        self.assertEqual(decision.mode, PermissionMode.INHERIT)

    def test_category_rule_apply_hota_hai(self):
        engine = PermissionEngine({"SAARTHI_PERMISSION_EMAIL": "block"})
        self.assertEqual(engine.decide("mail_bhejo").mode, PermissionMode.BLOCK)
        self.assertEqual(engine.decide("mail_padho").mode, PermissionMode.BLOCK)
        self.assertNotEqual(engine.decide("file_padho").mode, PermissionMode.BLOCK)

    def test_exact_tool_category_se_jeetta_hai(self):
        engine = PermissionEngine({
            "SAARTHI_PERMISSION_EMAIL": "block",
            "SAARTHI_PERMISSION_TOOL_MAIL_PADHO": "allow",
        })
        self.assertEqual(engine.decide("mail_padho").mode, PermissionMode.ALLOW)
        self.assertEqual(engine.decide("mail_bhejo").mode, PermissionMode.BLOCK)

    def test_ask_safe_action_pe_bhi_confirmation_force_karta_hai(self):
        decision = PermissionEngine({"SAARTHI_PERMISSION_FILES": "ask"}).decide("file_padho")
        self.assertEqual(decision.mode, PermissionMode.ASK)

    def test_aliases_and_invalid_values(self):
        self.assertEqual(
            PermissionEngine({"SAARTHI_PERMISSION_SHELL": "deny"})
            .decide("command_chalao").mode,
            PermissionMode.BLOCK,
        )
        self.assertEqual(
            PermissionEngine({"SAARTHI_PERMISSION_SHELL": "nonsense"})
            .decide("command_chalao").mode,
            PermissionMode.INHERIT,
        )

    def test_important_categories(self):
        expected = {
            "command_chalao": "shell", "file_banao": "files",
            "mail_bhejo": "email", "website_kholo": "browser",
            "text_likho": "device", "yaad_rakho": "memory",
            "skill_chalao": "skills", "event_banao": "calendar",
            "login_save_karo": "credentials", "image_banao": "creative",
        }
        for tool, category in expected.items():
            self.assertEqual(category_for(tool), category, tool)


if __name__ == "__main__":
    unittest.main()
