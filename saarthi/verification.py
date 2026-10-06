"""Post-action verification contracts for autonomous tool execution.

Tools may return verification evidence in ActionResult.data:
  verified: bool
  verification_message: str
  before_state / after_state: comparable snapshots
  expected / observed: comparable values

The central verifier prevents an LLM from treating "command accepted" as proof
that the real-world outcome happened. Existing tools degrade safely: BASIC mode
marks mutating actions unverified; STRICT mode fails them until evidence exists.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class VerificationMode(str, Enum):
    OFF = "off"
    BASIC = "basic"
    STRICT = "strict"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    FAILED = "verification_failed"
    SKIPPED = "verification_skipped"


# Actions which change external state and therefore need proof where possible.
_MUTATING_TOOLS = frozenset({
    "app_kholo", "app_band_karo", "app_control", "coordinate_pe_tap",
    "text_pe_tap", "text_likho", "field_bharo", "key_dabao", "scroll_karo",
    "media_control", "volume_control", "command_chalao", "python_chalao",
    "file_banao", "file_download_karo", "mail_bhejo", "event_banao",
    "event_hatao", "reminder_set", "reminder_hatao", "login_save_karo",
    "login_hata_do", "skill_chalao", "skill_hata_do", "skill_yaad_kar_le",
    "undo_karo", "ios_shortcut_chalao", "personal_yaad_rakho", "personal_bhool_jao",
    "github_issue_banao", "ghar_action_karo",
})


@dataclass(frozen=True)
class VerificationReport:
    status: VerificationStatus
    message: str
    mutating: bool

    @property
    def passed(self) -> bool:
        return self.status in {VerificationStatus.VERIFIED, VerificationStatus.SKIPPED}


def is_mutating(tool_name: str) -> bool:
    return tool_name in _MUTATING_TOOLS


def _mode(value: str | None) -> VerificationMode:
    try:
        return VerificationMode((value or "basic").strip().lower())
    except ValueError:
        return VerificationMode.BASIC


class ActionVerifier:
    def __init__(self, environment: Mapping[str, str] | None = None):
        env = os.environ if environment is None else environment
        self.mode = _mode(env.get("SAARTHI_VERIFICATION_MODE"))

    def verify(self, tool_name: str, result: Any) -> VerificationReport:
        mutating = is_mutating(tool_name)
        if self.mode == VerificationMode.OFF:
            return VerificationReport(VerificationStatus.SKIPPED, "Verification disabled", mutating)

        if not getattr(result, "ok", False):
            return VerificationReport(
                VerificationStatus.SKIPPED,
                "Action itself failed; outcome verification not applicable",
                mutating,
            )

        data = getattr(result, "data", {}) or {}
        explicit = data.get("verified")
        explicit_message = str(data.get("verification_message") or "").strip()
        if explicit is True:
            return VerificationReport(
                VerificationStatus.VERIFIED,
                explicit_message or "Tool supplied positive outcome evidence",
                mutating,
            )
        if explicit is False:
            return VerificationReport(
                VerificationStatus.FAILED,
                explicit_message or "Tool reported that expected outcome was not observed",
                mutating,
            )

        if "expected" in data and "observed" in data:
            matched = data["expected"] == data["observed"]
            return VerificationReport(
                VerificationStatus.VERIFIED if matched else VerificationStatus.FAILED,
                explicit_message or (
                    "Observed value matches expected value" if matched
                    else f"Expected {data['expected']!r}, observed {data['observed']!r}"
                ),
                mutating,
            )

        if "before_state" in data and "after_state" in data:
            changed = data["before_state"] != data["after_state"]
            return VerificationReport(
                VerificationStatus.VERIFIED if changed else VerificationStatus.FAILED,
                explicit_message or (
                    "State changed after action" if changed
                    else "No state change was observed after action"
                ),
                mutating,
            )

        # Read-only results are evidence themselves. Empty successful reads are
        # still verified because an empty inbox/list/screen can be valid.
        if not mutating:
            return VerificationReport(
                VerificationStatus.VERIFIED,
                "Read-only result returned successfully",
                False,
            )

        return VerificationReport(
            VerificationStatus.UNVERIFIED,
            "Action was accepted but no post-action evidence was supplied",
            True,
        )

    def should_fail(self, report: VerificationReport) -> bool:
        # Explicit contradictory evidence always fails. Missing evidence only
        # becomes fatal in STRICT mode, preserving backwards compatibility.
        return report.status == VerificationStatus.FAILED or (
            self.mode == VerificationMode.STRICT
            and report.status == VerificationStatus.UNVERIFIED
        )
