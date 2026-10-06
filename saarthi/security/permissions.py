"""Granular capability permissions for autonomous tool execution.

Policy precedence (most specific wins):
  SAARTHI_PERMISSION_TOOL_<TOOL_NAME>
  SAARTHI_PERMISSION_<CATEGORY>
  SAARTHI_PERMISSION_DEFAULT

Values: inherit, allow, ask, block.  ``inherit`` preserves the tool's existing
risk flag. Hard safety blocks inside tools are never bypassed by this layer.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class PermissionMode(str, Enum):
    INHERIT = "inherit"
    ALLOW = "allow"
    ASK = "ask"
    BLOCK = "block"


# Explicit lists make policy reviewable. Unknown tools safely fall into GENERAL.
_TOOL_CATEGORIES: dict[str, frozenset[str]] = {
    "shell": frozenset({"command_chalao", "python_chalao", "system_status"}),
    "files": frozenset({
        "file_padho", "file_banao", "files_dikhao", "file_kholo",
        "file_download_karo", "pdf_banao", "word_banao", "excel_banao", "ppt_banao",
    }),
    "email": frozenset({"mail_padho", "mail_dhoondho", "mail_bhejo"}),
    "browser": frozenset({
        "website_kholo", "website_padho", "page_padho", "field_bharo",
        "internet_pe_dhoondho", "file_download_karo",
    }),
    "device": frozenset({
        "app_kholo", "app_band_karo", "coordinate_pe_tap", "text_pe_tap",
        "text_likho", "key_dabao", "scroll_karo", "swipe_karo", "back_jao",
        "screenshot_lo", "screen_padho", "screen_vision", "notifications_padho",
        "volume_control", "media_control", "device_ki_jaankari", "phone_wifi_se_jodo",
        "app_control", "apps_ki_list", "ios_shortcut_chalao",
    }),
    "memory": frozenset({
        "yaad_rakho", "yaad_karo", "bhool_jao", "purani_baat_dhoondho",
        "personal_yaad_rakho", "personal_yaad_karo", "personal_bhool_jao",
    }),
    "skills": frozenset({
        "seekhna_shuru_karo", "seekhna_cancel_karo", "recording_status", "skill_chalao",
        "skill_yaad_kar_le", "skills_ki_list", "skill_dikhao", "skill_hata_do",
        "phone_se_seekho",
    }),
    "calendar": frozenset({
        "event_banao", "events_dikhao", "event_hatao", "reminder_set",
        "reminders_dikhao", "reminder_hatao",
    }),
    "credentials": frozenset({
        "login_save_karo", "logins_dikhao", "login_hata_do", "login_karo",
    }),
    "creative": frozenset({"image_banao", "video_banao"}),
    "tasks": frozenset({
        "plan_banao", "plan_update", "plan_dikhao", "task_resume_karo",
        "task_pause_karo", "tasks_dikhao",
    }),
    "undo": frozenset({"undo_karo", "undo_dikhao"}),
}


def _env_name(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def category_for(tool_name: str) -> str:
    for category, names in _TOOL_CATEGORIES.items():
        if tool_name in names:
            return category
    return "general"


def _parse(value: str | None) -> PermissionMode | None:
    if not value:
        return None
    normalized = value.strip().lower()
    aliases = {"deny": "block", "confirm": "ask", "auto": "allow"}
    normalized = aliases.get(normalized, normalized)
    try:
        return PermissionMode(normalized)
    except ValueError:
        return None


@dataclass(frozen=True)
class PermissionDecision:
    mode: PermissionMode
    category: str
    source: str


class PermissionEngine:
    """Immutable permission snapshot created at agent startup."""

    def __init__(self, environment: Mapping[str, str] | None = None):
        self._env = dict(os.environ if environment is None else environment)

    def decide(self, tool_name: str) -> PermissionDecision:
        category = category_for(tool_name)
        tool_key = f"SAARTHI_PERMISSION_TOOL_{_env_name(tool_name)}"
        category_key = f"SAARTHI_PERMISSION_{category.upper()}"

        for key in (tool_key, category_key, "SAARTHI_PERMISSION_DEFAULT"):
            mode = _parse(self._env.get(key))
            if mode is not None:
                return PermissionDecision(mode, category, key)
        return PermissionDecision(PermissionMode.INHERIT, category, "built-in")

    def describe(self, tool_names: list[str]) -> dict[str, PermissionDecision]:
        return {name: self.decide(name) for name in tool_names}
