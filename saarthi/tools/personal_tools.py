"""Tools for structured personal intelligence."""
from __future__ import annotations
from ..devices.base import ActionResult
from .base import Tool, ToolContext

class PersonalRememberTool(Tool):
    name="personal_yaad_rakho"
    description=("Remember a structured fact about the user's people, preferences, routines, goals, projects, "
                 "or explicit corrections. Use only for information the user stated, not guesses.")
    parameters={"type":"object","properties":{
      "kind":{"type":"string","enum":["person","preference","routine","goal","project","correction"]},
      "subject":{"type":"string","description":"Person/project/user name"},
      "key":{"type":"string","description":"Relationship or property, e.g. relation, coffee, wake_time"},
      "value":{"type":"string"}},"required":["kind","subject","key","value"]}
    async def run(self,ctx:ToolContext,kind:str,subject:str,key:str,value:str)->ActionResult:
        store=ctx.scratch.get("personal_store")
        if store is None:return ActionResult.failure("Personal intelligence store available nahi hai.")
        try:item=store.remember(kind,subject,key,value,source="user")
        except ValueError as e:return ActionResult.failure(str(e))
        return ActionResult.success(f"Personal memory saved: {item.subject} · {item.key} = {item.value}",verified=True)

class PersonalRecallTool(Tool):
    name="personal_yaad_karo"
    description="Recall people, relationships, preferences, routines, goals or projects from structured personal memory."
    parameters={"type":"object","properties":{"query":{"type":"string"},"kind":{"type":"string"}}}
    async def run(self,ctx:ToolContext,query:str="",kind:str="")->ActionResult:
        store=ctx.scratch.get("personal_store"); items=store.search(query,kind) if store else []
        if not items:return ActionResult.success("Is topic par personal memory nahi mili.")
        return ActionResult.success("\n".join(f"#{x.id} [{x.kind}] {x.subject} · {x.key}: {x.value}" for x in items))

class PersonalForgetTool(Tool):
    name="personal_bhool_jao"
    description="Delete one personal-memory item by ID when the user explicitly asks to forget it."
    risky=True
    parameters={"type":"object","properties":{"item_id":{"type":"integer"}},"required":["item_id"]}
    async def run(self,ctx:ToolContext,item_id:int)->ActionResult:
        store=ctx.scratch.get("personal_store")
        return ActionResult.success("Personal memory delete ho gayi.",verified=True) if store and store.forget(item_id) else ActionResult.failure("Memory item nahi mila.")

def personal_tools(): return [PersonalRememberTool(),PersonalRecallTool(),PersonalForgetTool()]
