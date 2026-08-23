"""
Skill Recorder — "DIKHA DO MODE" ka recording hissa.

IMAANDAAR BAAT (ye samajhna zaroori hai):

    Phase 3 (abhi) — jo AB kaam karta hai:
        SAARTHI apne kiye hue successful steps record karta hai.
        Tu bolta hai "recording shuru kar", phir usse batata hai kya
        karna hai. Wo karta hai, steps yaad rakhta hai, skill ban jaati hai.

    Phase 4 (aage) — jo aage aayega:
        Tu KHUD phone pe kaam karega, aur SAARTHI dekhta rahega.
        Iske liye Android app + Accessibility Service chahiye, jo
        on-device user ke taps sun sake. ADB se ye reliably nahi hota.

Dono ka data format SAME hai — isliye jab Phase 4 ka app banega,
ye pura store aur runner waise hi chalega. Kuch dobara nahi likhna padega.
Yahi accha architecture hai.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .store import Skill, SkillStep, parameterize_steps

log = logging.getLogger("saarthi.skills.recorder")


# Ye actions record karne layak hain (inse kaam hota hai)
RECORDABLE_ACTIONS: set[str] = {
    "app_kholo",
    "app_band_karo",
    "text_pe_tap",
    "coordinate_pe_tap",
    "text_likho",
    "key_dabao",
    "scroll_karo",
    "command_chalao",
}

# Ye actions record NAHI karne — ye sirf "dekhne" wale hain.
# Inko skill mein daalne se skill slow aur bekaar ho jaayegi.
SKIP_ACTIONS: set[str] = {
    "screen_padho",
    "screenshot_lo",
    "device_ki_jaankari",
    "apps_ki_list",
    "notifications_padho",
    "internet_pe_dhoondho",
    "website_padho",
    "time_bata",
    "calculate_karo",
    "user_se_pucho",
    "yaad_rakho",
    "yaad_karo",
    "skill_chalao",
    "skill_seekho",
    "skills_ki_list",
}


@dataclass
class RecordedAction:
    """Ek action jo record hua."""

    action: str
    params: dict = field(default_factory=dict)
    target_text: str = ""
    target_coords: tuple[int, int] | None = None
    succeeded: bool = True
    timestamp: float = field(default_factory=time.time)

    def to_step(self) -> SkillStep:
        return SkillStep(
            action=self.action,
            params=dict(self.params),
            target_text=self.target_text,
            target_coords=self.target_coords,
        )


class SkillRecorder:
    """
    Steps record karta hai jab "Dikha Do Mode" ON hai.

    Use:
        recorder = SkillRecorder()
        recorder.start()
        ... agent kaam karta hai, har action record hota hai ...
        skill = recorder.finish("bijli ka bill", "Paytm se bijli ka bill")
        await store.save(skill)
    """

    def __init__(self) -> None:
        self.recording: bool = False
        self.actions: list[RecordedAction] = []
        self.device_kind: str = "android"
        self.started_at: float | None = None

    # ------------------------------------------------------------------
    #  Control
    # ------------------------------------------------------------------

    def start(self, device_kind: str = "android") -> None:
        """Recording shuru karo."""
        self.recording = True
        self.actions = []
        self.device_kind = device_kind
        self.started_at = time.time()
        log.info("Recording shuru (device=%s)", device_kind)

    def cancel(self) -> None:
        """Recording chhod do, kuch save nahi."""
        self.recording = False
        self.actions = []
        self.started_at = None
        log.info("Recording cancel")

    @property
    def step_count(self) -> int:
        """Kitne useful steps record hue."""
        return len(self.actions)

    # ------------------------------------------------------------------
    #  Capture
    # ------------------------------------------------------------------

    def capture(
        self,
        action: str,
        params: dict,
        succeeded: bool = True,
        target_text: str = "",
        target_coords: tuple[int, int] | None = None,
    ) -> bool:
        """
        Ek action record karo.

        Returns: record hua ya nahi

        Ye rules follow karta hai:
          - Recording OFF ho to skip
          - Read-only actions skip (screenshot, search etc.)
          - FAILED actions skip — galat step skill mein nahi jaana chahiye
        """
        if not self.recording:
            return False

        if action in SKIP_ACTIONS:
            return False

        if not succeeded:
            # Fail hua step record karna sabse buri galti hogi —
            # skill hamesha usi jagah tootegi.
            log.debug("Fail hua action skip kiya: %s", action)
            return False

        if action not in RECORDABLE_ACTIONS:
            log.debug("Unknown action skip kiya: %s", action)
            return False

        # text_pe_tap ka 'text' hi uska target hai — self-healing ke liye
        if not target_text and action == "text_pe_tap":
            target_text = str(params.get("text", ""))

        # device param skill mein nahi rakhna — replay ke waqt decide hoga
        clean_params = {k: v for k, v in params.items() if k != "device"}

        self.actions.append(
            RecordedAction(
                action=action,
                params=clean_params,
                target_text=target_text,
                target_coords=target_coords,
                succeeded=succeeded,
            )
        )
        log.debug("Record hua: %s (total %d)", action, len(self.actions))
        return True

    # ------------------------------------------------------------------
    #  Finish
    # ------------------------------------------------------------------

    def finish(
        self,
        name: str,
        description: str = "",
        auto_parameterize: bool = True,
    ) -> Skill | None:
        """
        Recording band karo aur Skill banao.

        Returns None agar kuch record hi nahi hua.
        """
        self.recording = False

        if not self.actions:
            log.warning("Kuch record nahi hua — skill nahi banegi")
            self.started_at = None
            return None

        steps = [action.to_step() for action in self.actions]
        params: list[str] = []

        if auto_parameterize:
            steps, params = parameterize_steps(steps)

        skill = Skill(
            name=name.strip().lower(),
            description=description or f"{len(steps)} steps ka kaam",
            device_kind=self.device_kind,
            steps=steps,
            params=list(dict.fromkeys(params)),  # duplicates hatao, order rakho
        )

        log.info("Skill bani: %s (%d steps)", skill.name, len(steps))

        self.actions = []
        self.started_at = None
        return skill

    # ------------------------------------------------------------------
    #  Preview
    # ------------------------------------------------------------------

    def preview(self) -> str:
        """
        Abhi tak kya record hua — user ko dikhane ke liye.

        Save karne se pehle user dekh sake ki sahi steps hain ya nahi.
        """
        if not self.recording:
            return "Recording ON nahi hai."

        if not self.actions:
            return "Recording ON hai, par abhi koi step record nahi hua."

        lines = [f"Recording ON — {len(self.actions)} steps:"]
        for i, action in enumerate(self.actions, 1):
            step = action.to_step()
            lines.append(f"  {i}. {step}")

        # Parameterize karke dikhao ki reusable version kaisa lagega
        steps, params = parameterize_steps([a.to_step() for a in self.actions])
        if params:
            lines.append("")
            lines.append(
                f"Ye values har baar badal sakti hain: {', '.join(dict.fromkeys(params))}"
            )

        return "\n".join(lines)
