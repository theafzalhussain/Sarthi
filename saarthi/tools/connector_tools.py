"""External connector tools. Mutations remain confirmation-protected."""
from __future__ import annotations
from ..devices.base import ActionResult
from .base import Tool,ToolContext

def result(r):
 return ActionResult.success(r.message,**r.data) if r.ok else ActionResult.failure(r.message)
class ConnectorsStatusTool(Tool):
 name="connectors_status"; description="Check GitHub and Home Assistant connection health."
 parameters={"type":"object","properties":{}}
 async def run(self,ctx):
  m=ctx.scratch.get("connectors")
  if not m:return ActionResult.failure("Connector manager unavailable")
  health=await m.health_all(); return ActionResult.success("\n".join(f"{n}: {'connected' if r.ok else r.message}" for n,r in health.items()))
class GitHubIssuesTool(Tool):
 name="github_issues_dikhao"; description="List issues from a GitHub repository (owner/repo)."
 parameters={"type":"object","properties":{"repo":{"type":"string"},"limit":{"type":"integer"}},"required":["repo"]}
 async def run(self,ctx,repo,limit=20):return result(await ctx.scratch["connectors"].get("github").list_issues(repo,limit))
class GitHubIssueCreateTool(Tool):
 name="github_issue_banao"; description="Create a GitHub issue. Always show title/repo and ask confirmation first."
 risky=True
 parameters={"type":"object","properties":{"repo":{"type":"string"},"title":{"type":"string"},"body":{"type":"string"}},"required":["repo","title"]}
 async def run(self,ctx,repo,title,body=""):return result(await ctx.scratch["connectors"].get("github").create_issue(repo,title,body))
class HomeStatesTool(Tool):
 name="ghar_devices_dikhao"; description="Read Home Assistant entities and their current state."
 parameters={"type":"object","properties":{}}
 async def run(self,ctx):return result(await ctx.scratch["connectors"].get("home_assistant").states())
class HomeServiceTool(Tool):
 name="ghar_action_karo"; description="Call an explicit Home Assistant service, e.g. light.turn_on. Requires confirmation."
 risky=True
 parameters={"type":"object","properties":{"domain":{"type":"string"},"service":{"type":"string"},"data":{"type":"object"}},"required":["domain","service"]}
 async def run(self,ctx,domain,service,data=None):return result(await ctx.scratch["connectors"].get("home_assistant").call_service(domain,service,data or {}))
def connector_tools():return [ConnectorsStatusTool(),GitHubIssuesTool(),GitHubIssueCreateTool(),HomeStatesTool(),HomeServiceTool()]
