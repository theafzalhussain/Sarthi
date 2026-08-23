"""
Memory Tools — agent ki yaaddasht ke tools.

Inke bina agent har baar zero se shuru karta hai. Inke saath wo
tujhe jaanne lagta hai.
"""

from __future__ import annotations

from ..devices.base import ActionResult
from .base import Tool, ToolContext


class RememberTool(Tool):
    name = "yaad_rakho"
    description = (
        "Koi baat permanently yaad rakho. Jab user kuch bataye jo aage "
        "kaam aayega — jaise contact number, address, preference, ya koi "
        "setting — to turant ye use kar. Bina puche yaad rakhna accha hai."
    )
    parameters = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Chhota naam, jaise 'mummy ka number'",
            },
            "value": {
                "type": "string",
                "description": "Jo yaad rakhna hai",
            },
            "category": {
                "type": "string",
                "description": (
                    "Group: contacts, preferences, addresses, "
                    "accounts, general"
                ),
            },
        },
        "required": ["key", "value"],
    }

    async def run(
        self,
        ctx: ToolContext,
        key: str,
        value: str,
        category: str = "general",
    ) -> ActionResult:
        if ctx.memory is None:
            return ActionResult.failure("Memory available nahi hai")

        # SAFETY: password/OTP kabhi save nahi karna
        sensitive = ("password", "otp", "pin", "cvv", "passcode")
        combined = f"{key} {value}".lower()
        if any(word in combined for word in sensitive):
            return ActionResult.failure(
                "Password/OTP/PIN main save nahi karta — ye security rule hai. "
                "Baaki kuch bhi yaad rakh lunga."
            )

        await ctx.memory.remember(key, value, category)
        return ActionResult.success(f"Yaad rakh liya: {key} = {value}")


class RecallTool(Tool):
    name = "yaad_karo"
    description = (
        "Yaad rakhi hui baat nikaalo. Kuch bhi puchne se pehle ye check kar "
        "— ho sakta hai user ne pehle bata rakha ho."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Kya dhoondhna hai, jaise 'mummy'",
            }
        },
        "required": ["query"],
    }

    async def run(self, ctx: ToolContext, query: str) -> ActionResult:
        if ctx.memory is None:
            return ActionResult.failure("Memory available nahi hai")

        # Exact match pehle
        fact = await ctx.memory.recall(query)
        if fact:
            return ActionResult.success(f"{fact.key}: {fact.value}")

        # Phir search
        facts = await ctx.memory.search_facts(query, limit=8)
        if not facts:
            return ActionResult.success(
                f"'{query}' ke baare mein kuch yaad nahi hai. User se puch le."
            )

        lines = [f"'{query}' se related {len(facts)} baatein:"]
        lines += [f"  - {f.key}: {f.value}" for f in facts]
        return ActionResult.success("\n".join(lines))


class ForgetTool(Tool):
    name = "bhool_jao"
    description = "Yaad rakhi hui baat delete karo."
    parameters = {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Kaunsi baat bhoolni hai"}
        },
        "required": ["key"],
    }
    risky = True  # Data delete ho raha hai — confirmation lo

    async def run(self, ctx: ToolContext, key: str) -> ActionResult:
        if ctx.memory is None:
            return ActionResult.failure("Memory available nahi hai")

        deleted = await ctx.memory.forget(key)
        if deleted:
            return ActionResult.success(f"Bhool gaya: {key}")
        return ActionResult.success(f"'{key}' pehle se yaad nahi tha")


class SearchHistoryTool(Tool):
    name = "purani_baat_dhoondho"
    description = (
        "Purani conversations mein dhoondo. Jab user bole 'wahi kar do jo "
        "pichli baar kiya tha' ya 'phir se wahi' — to ye use kar ke pata "
        "kar pichli baar kya hua tha."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Kya dhoondhna hai"}
        },
        "required": ["query"],
    }

    async def run(self, ctx: ToolContext, query: str) -> ActionResult:
        if ctx.memory is None:
            return ActionResult.failure("Memory available nahi hai")

        turns = await ctx.memory.search_history(query, limit=10)
        if not turns:
            return ActionResult.success(f"'{query}' ke baare mein purani baat nahi mili")

        lines = [f"'{query}' se related {len(turns)} purani baatein:"]
        for turn in turns:
            snippet = turn.content[:200]
            lines.append(f"  [{turn.role}] {snippet}")
        return ActionResult.success("\n".join(lines))


def memory_tools() -> list[Tool]:
    return [
        RememberTool(),
        RecallTool(),
        ForgetTool(),
        SearchHistoryTool(),
    ]
