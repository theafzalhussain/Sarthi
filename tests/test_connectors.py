from __future__ import annotations
import asyncio,unittest
from unittest.mock import AsyncMock,patch
from saarthi.connectors.base import ConnectorResult
from saarthi.connectors.manager import ConnectorManager
from saarthi.connectors.home_assistant import HomeAssistantConnector
from saarthi.connectors.github import GitHubConnector

def run(c):return asyncio.run(c)
class ConnectorTests(unittest.TestCase):
 def test_manager_has_standard_connectors(self):
  m=ConnectorManager(); self.assertIn("github",m.connectors); self.assertIn("home_assistant",m.connectors)
 def test_home_assistant_requires_config(self):
  r=run(HomeAssistantConnector().health()); self.assertFalse(r.ok)
 def test_home_assistant_rejects_path_injection(self):
  c=HomeAssistantConnector("http://x","token")
  r=run(c.call_service("light/../../evil","turn_on",{})); self.assertFalse(r.ok)
 def test_github_issue_json_parsed(self):
  c=GitHubConnector(); payload='[{"number":1,"title":"Bug","state":"OPEN","url":"u"}]'
  with patch.object(c,"_run",new=AsyncMock(return_value=(0,payload,""))):
   r=run(c.list_issues("owner/repo")); self.assertTrue(r.ok); self.assertEqual(r.data["issues"][0]["number"],1)
 def test_github_failure_is_structured(self):
  c=GitHubConnector()
  with patch.object(c,"_run",new=AsyncMock(return_value=(1,"","not authenticated"))):
   r=run(c.create_issue("o/r","title")); self.assertFalse(r.ok); self.assertIn("authenticated",r.message)
 def test_connector_result_contract(self):
  self.assertTrue(ConnectorResult.success("ok",x=1).ok); self.assertFalse(ConnectorResult.failure("bad").ok)
if __name__=='__main__':unittest.main()
