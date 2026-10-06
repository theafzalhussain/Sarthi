"""GitHub connector using the authenticated official gh CLI."""
from __future__ import annotations
import asyncio, json, shutil
from .base import Connector,ConnectorResult

class GitHubConnector(Connector):
 name="github"
 async def _run(self,*args,timeout=30):
  if not shutil.which("gh"): return 127,"","gh CLI install nahi hai"
  try:
   p=await asyncio.create_subprocess_exec("gh",*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
   out,err=await asyncio.wait_for(p.communicate(),timeout)
   return p.returncode,out.decode(errors="replace"),err.decode(errors="replace")
  except asyncio.TimeoutError:
   p.kill(); return 124,"","GitHub request timeout"
 async def available(self):
  code,_,_=await self._run("auth","status",timeout=10); return code==0
 async def health(self):
  code,out,err=await self._run("api","user","--jq",".login",timeout=15)
  return ConnectorResult.success(f"GitHub connected: {out.strip()}",user=out.strip()) if code==0 else ConnectorResult.failure(err.strip() or "GitHub auth unavailable")
 async def list_issues(self,repo,limit=20):
  code,out,err=await self._run("issue","list","--repo",repo,"--limit",str(max(1,min(limit,100))),"--json","number,title,state,url")
  if code:return ConnectorResult.failure(err.strip())
  try:return ConnectorResult.success(f"{len(json.loads(out))} issues",issues=json.loads(out))
  except json.JSONDecodeError:return ConnectorResult.failure("GitHub ka invalid response")
 async def create_issue(self,repo,title,body=""):
  code,out,err=await self._run("issue","create","--repo",repo,"--title",title,"--body",body)
  return ConnectorResult.success(f"GitHub issue created: {out.strip()}",url=out.strip(),verified=bool(out.strip())) if code==0 else ConnectorResult.failure(err.strip())
