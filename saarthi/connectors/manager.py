from __future__ import annotations
import asyncio,os
from .github import GitHubConnector
from .home_assistant import HomeAssistantConnector
class ConnectorManager:
 def __init__(self):
  self.connectors={"github":GitHubConnector(),"home_assistant":HomeAssistantConnector(os.getenv("HOME_ASSISTANT_URL","") ,os.getenv("HOME_ASSISTANT_TOKEN",""))}
 def get(self,name):return self.connectors.get(name)
 async def health_all(self):
  async def one(n,c):
   try:return n,await c.health()
   except Exception as e:
    from .base import ConnectorResult
    return n,ConnectorResult.failure(str(e))
  return dict(await asyncio.gather(*(one(n,c) for n,c in self.connectors.items())))
