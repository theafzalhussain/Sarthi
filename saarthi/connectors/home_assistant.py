"""Home Assistant REST connector with explicit service calls."""
from __future__ import annotations
import re
try: import httpx
except ImportError: httpx=None
from .base import Connector,ConnectorResult
_SAFE=re.compile(r"^[a-z0-9_]+$")
class HomeAssistantConnector(Connector):
 name="home_assistant"
 def __init__(self,url="",token=""):
  self.url=url.rstrip('/'); self.token=token
 @property
 def headers(self):return {"Authorization":f"Bearer {self.token}","Content-Type":"application/json"}
 async def available(self):return (await self.health()).ok
 async def health(self):
  if not httpx or not self.url or not self.token:return ConnectorResult.failure("Home Assistant URL/token configured nahi hai")
  try:
   async with httpx.AsyncClient(timeout=10) as c:r=await c.get(self.url+"/api/",headers=self.headers)
   return ConnectorResult.success("Home Assistant connected") if r.status_code==200 else ConnectorResult.failure(f"Home Assistant HTTP {r.status_code}")
  except Exception as e:return ConnectorResult.failure(f"Home Assistant unavailable: {e}")
 async def states(self):
  try:
   async with httpx.AsyncClient(timeout=15) as c:r=await c.get(self.url+"/api/states",headers=self.headers)
   if r.status_code!=200:return ConnectorResult.failure(f"HTTP {r.status_code}")
   data=r.json(); return ConnectorResult.success(f"{len(data)} entities",states=data)
  except Exception as e:return ConnectorResult.failure(str(e))
 async def call_service(self,domain,service,data):
  if not _SAFE.match(domain) or not _SAFE.match(service):return ConnectorResult.failure("Invalid domain/service")
  try:
   async with httpx.AsyncClient(timeout=20) as c:r=await c.post(f"{self.url}/api/services/{domain}/{service}",headers=self.headers,json=data)
   if r.status_code not in (200,201):return ConnectorResult.failure(f"Home Assistant HTTP {r.status_code}: {r.text[:200]}")
   return ConnectorResult.success(f"Home Assistant {domain}.{service} complete",response=r.json(),verified=True)
  except Exception as e:return ConnectorResult.failure(str(e))
