"""
Skill Tools — "DIKHA DO MODE" ke tools.

Inke through user aur agent skills bana, dekh, chala aur delete kar
sakte hain.

Ye tools ctx.scratch mein recorder aur runner dhoondhte hain — agent
loop unhe wahan rakhta hai.
"""

from __future__ import annotations

from ..devices.base import ActionResult
from .base import Tool, ToolContext


def _get_recorder(ctx: ToolContext):
    """Agent loop recorder ko scratch mein rakhta hai."""
    return ctx.scratch.get("recorder")


def _get_runner(ctx: ToolContext):
    return ctx.scratch.get("skill_runner")


class StartLearningTool(Tool):
    name = "seekhna_shuru_karo"
    description = (
        "Recording ON karo — 'Dikha Do Mode'. Jab user bole 'dekh main "
        "dikha raha hun', 'ye yaad kar le', 'sikha raha hun' — to ye use "
        "kar. Iske baad jo bhi kaam ke steps honge wo record honge, aur "
        "baad mein skill ban jaayegi."
    )
    parameters = {
        "type": "object",
        "properties": {
            "device": {
                "type": "string",
                "description": "Kis device pe seekh raha hai: android ya desktop",
            }
        },
    }

    async def run(
        self, ctx: ToolContext, device: str = "android"
    ) -> ActionResult:
        recorder = _get_recorder(ctx)
        if recorder is None:
            return ActionResult.failure("Recorder available nahi hai")

        recorder.start(device_kind=device)
        return ActionResult.success(
            "Recording ON hai. Ab bata kya karna hai — main karta jaaunga "
            "aur steps yaad rakhta jaaunga. Kaam khatam ho to bol "
            "'yaad kar le' aur naam bata dena."
        )


class SaveSkillTool(Tool):
    name = "skill_yaad_kar_le"
    description = (
        "Recording band karo aur skill save karo. User jab kaam dikha chuke "
        "aur naam bataye — jaise 'isko bijli ka bill bol' — to ye use kar."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Skill ka naam, jaise 'bijli ka bill'",
            },
            "description": {
                "type": "string",
                "description": "Ye skill kya karti hai (chhota description)",
            },
        },
        "required": ["name"],
    }

    async def run(
        self, ctx: ToolContext, name: str, description: str = ""
    ) -> ActionResult:
        recorder = _get_recorder(ctx)
        if recorder is None:
            return ActionResult.failure("Recorder available nahi hai")
        if ctx.skills is None:
            return ActionResult.failure("Skill store available nahi hai")

        if not recorder.recording and recorder.step_count == 0:
            return ActionResult.failure(
                "Recording ON hi nahi thi. Pehle 'seekhna_shuru_karo' chala, "
                "phir kaam kar, phir save kar."
            )

        skill = recorder.finish(name=name, description=description)
        if skill is None:
            return ActionResult.failure(
                "Koi step record nahi hua tha, isliye skill nahi bani. "
                "Recording ON karke kuch kaam karna padega."
            )

        saved = await ctx.skills.save(skill)

        lines = [f"Skill save ho gayi: '{saved.name}' ({len(saved.steps)} steps)"]
        needed = saved.required_params()
        if needed:
            lines.append(f"Agli baar ye batana padega: {', '.join(sorted(needed))}")
        lines.append("")
        lines.append("Steps:")
        for i, step in enumerate(saved.steps, 1):
            lines.append(f"  {i}. {step}")

        return ActionResult.success("\n".join(lines))


class RecordingStatusTool(Tool):
    name = "recording_status"
    description = (
        "Recording ka status aur abhi tak record hue steps dikhao. "
        "Save karne se pehle check karne ke liye."
    )
    parameters = {"type": "object", "properties": {}}

    async def run(self, ctx: ToolContext) -> ActionResult:
        recorder = _get_recorder(ctx)
        if recorder is None:
            return ActionResult.failure("Recorder available nahi hai")
        return ActionResult.success(recorder.preview())


class CancelLearningTool(Tool):
    name = "seekhna_cancel_karo"
    description = "Recording cancel karo, kuch save na karo."
    parameters = {"type": "object", "properties": {}}

    async def run(self, ctx: ToolContext) -> ActionResult:
        recorder = _get_recorder(ctx)
        if recorder is None:
            return ActionResult.failure("Recorder available nahi hai")
        recorder.cancel()
        return ActionResult.success("Recording cancel kar di, kuch save nahi hua.")


class ListSkillsTool(Tool):
    name = "skills_ki_list"
    description = (
        "Kaunse kaam seekhe hue hain wo batao. User pooche 'tu kya kar "
        "sakta hai' to ye use kar."
    )
    parameters = {"type": "object", "properties": {}}

    async def run(self, ctx: ToolContext) -> ActionResult:
        if ctx.skills is None:
            return ActionResult.failure("Skill store available nahi hai")

        skills = await ctx.skills.list_skills()
        if not skills:
            return ActionResult.success(
                "Abhi koi skill nahi seekhi. User ko bol sakta hai: "
                "'ek baar dikha de, main yaad kar lunga'."
            )

        lines = [f"{len(skills)} skills seekhi hui hain:"]
        lines += [f"  - {s.summary()}" for s in skills]
        return ActionResult.success("\n".join(lines))


class RunSkillTool(Tool):
    name = "skill_chalao"
    description = (
        "Seekhi hui skill chalao. Jab user koi jaana-pehchana kaam bole "
        "(jaise 'bijli ka bill bhar de') to pehle ye try kar — zero se "
        "karne se ye tez aur reliable hai. Agar UI badal gaya to main "
        "khud theek kar lunga."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill ka naam"},
            "values": {
                "type": "object",
                "description": (
                    "Skill ko chahiye values, jaise {\"amount\": 2500}"
                ),
            },
        },
        "required": ["name"],
    }
    risky = True  # Poora sequence chal raha hai — user ko pata hona chahiye

    async def run(
        self,
        ctx: ToolContext,
        name: str,
        values: dict | None = None,
    ) -> ActionResult:
        if ctx.skills is None:
            return ActionResult.failure("Skill store available nahi hai")

        runner = _get_runner(ctx)
        if runner is None:
            return ActionResult.failure("Skill runner available nahi hai")

        # Hinglish naam se dhoondo — user exact naam nahi bolta
        matches = await ctx.skills.find(name)
        if not matches:
            available = await ctx.skills.list_skills()
            names = ", ".join(s.name for s in available) or "koi nahi"
            return ActionResult.failure(
                f"'{name}' naam ki skill nahi mili. Available: {names}"
            )

        skill = matches[0]
        result = await runner.run(skill, values or {}, ctx)

        if result.ok:
            return ActionResult.success(result.report(), healed=result.heal_count)
        return ActionResult.failure(result.report(), healed=result.heal_count)


class ExplainSkillTool(Tool):
    name = "skill_dikhao"
    description = (
        "Kisi skill ke steps detail mein dikhao. User pooche 'ye kaise "
        "karta hai' to ye use kar."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill ka naam"}
        },
        "required": ["name"],
    }

    async def run(self, ctx: ToolContext, name: str) -> ActionResult:
        if ctx.skills is None:
            return ActionResult.failure("Skill store available nahi hai")

        matches = await ctx.skills.find(name)
        if not matches:
            return ActionResult.failure(f"'{name}' naam ki skill nahi mili")

        return ActionResult.success(matches[0].explain())


class DeleteSkillTool(Tool):
    name = "skill_hata_do"
    description = "Seekhi hui skill delete karo."
    parameters = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill ka naam"}
        },
        "required": ["name"],
    }
    risky = True

    async def run(self, ctx: ToolContext, name: str) -> ActionResult:
        if ctx.skills is None:
            return ActionResult.failure("Skill store available nahi hai")

        deleted = await ctx.skills.delete(name)
        if deleted:
            return ActionResult.success(f"Skill hata di: {name}")
        return ActionResult.failure(f"'{name}' naam ki skill nahi mili")


class PhoneSeSkillTool(Tool):
    """
    Phone pe record hue actions se skill banao — Phase 4 ka ASLI INAAM.

    User phone pe manually kaam karta hai (app kholta, button dabata),
    phone ka AccessibilityService sab record karta hai, phir ye tool
    wo actions laakar Skill bana deta hai.

    Ye Dikha Do Mode ka NAYA SOURCE hai — ab user ko agent ke through
    kaam nahi karna padta, KHUD phone pe kar sakta hai aur SAARTHI
    yaad kar lega.
    """

    name = "phone_se_seekho"
    description = (
        "Phone pe user ke manually kiye kaam se skill banao. Phone app "
        "mein 'Dikha Do' mode ON hona chahiye. User jab phone pe kaam "
        "dikha chuka ho aur bole 'phone se seekh le' — to ye use kar."
    )
    parameters = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Skill ka naam, jaise 'bijli ka bill'",
            },
            "description": {
                "type": "string",
                "description": "Ye skill kya karti hai (chhota description)",
            },
        },
        "required": ["name"],
    }

    async def run(
        self, ctx: ToolContext, name: str, description: str = ""
    ) -> ActionResult:
        if ctx.skills is None:
            return ActionResult.failure("Skill store available nahi hai")

        # Phone device dhoondo (AccessibilityDevice)
        from ..devices.accessibility import AccessibilityDevice

        phone = None
        for device in ctx.devices.devices.values():
            if isinstance(device, AccessibilityDevice):
                phone = device
                break

        if phone is None:
            return ActionResult.failure(
                "Phone (AccessibilityDevice) registered nahi hai. "
                "SAARTHI_PHONE_URL aur SAARTHI_PHONE_TOKEN .env mein set kar."
            )

        # Phone se recorded actions laao
        result = await phone.get_recorded_actions()
        if not result.ok:
            return result

        actions = result.data.get("actions", [])
        if not actions:
            return ActionResult.failure(
                "Phone pe kuch record nahi hua. Pehle phone app mein "
                "'Dikha Do' mode ON kar, kaam kar, phir ye tool chala."
            )

        # Actions ko SkillStep mein convert karo
        from ..skills.store import Skill, SkillStep, parameterize_steps

        steps: list[SkillStep] = []
        for action_data in actions:
            # target_coords: list -> tuple ya None
            raw_coords = action_data.get("target_coords")
            coords = None
            if isinstance(raw_coords, (list, tuple)) and len(raw_coords) >= 2:
                coords = (int(raw_coords[0]), int(raw_coords[1]))

            steps.append(SkillStep(
                action=action_data.get("action", ""),
                params=action_data.get("params", {}),
                target_text=action_data.get("target_text", ""),
                target_coords=coords,
                notes=action_data.get("notes", ""),
            ))

        # Parameterize — reusable banao
        steps, params = parameterize_steps(steps)

        skill = Skill(
            name=name.strip().lower(),
            description=description or f"Phone se seekhi — {len(steps)} steps",
            device_kind="android",
            steps=steps,
            params=list(dict.fromkeys(params)),
        )

        saved = await ctx.skills.save(skill)

        lines = [f"Skill save ho gayi: '{saved.name}' ({len(saved.steps)} steps)"]
        needed = saved.required_params()
        if needed:
            lines.append(f"Agli baar ye batana padega: {', '.join(sorted(needed))}")
        lines.append("")
        lines.append("Steps:")
        for i, step in enumerate(saved.steps, 1):
            lines.append(f"  {i}. {step}")

        return ActionResult.success("\n".join(lines))


def skill_tools() -> list[Tool]:
    return [
        StartLearningTool(),
        SaveSkillTool(),
        RecordingStatusTool(),
        CancelLearningTool(),
        ListSkillsTool(),
        RunSkillTool(),
        ExplainSkillTool(),
        DeleteSkillTool(),
        PhoneSeSkillTool(),
    ]
