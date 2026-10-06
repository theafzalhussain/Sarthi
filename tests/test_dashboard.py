from __future__ import annotations
import unittest
from pathlib import Path

SOURCE=(Path(__file__).parents[1]/"saarthi"/"web"/"app.py").read_text(encoding="utf-8")
class DashboardContractTests(unittest.TestCase):
 def test_unified_routes_exist(self):
  for route in ("/api/dashboard","/api/dashboard/tasks","/api/dashboard/audit","/api/dashboard/memory","/api/dashboard/undo","/dashboard"):
   self.assertIn(f'@app.get("{route}"',SOURCE)
 def test_dashboard_api_auth_namespace_mein_hai(self):
  self.assertIn('_PROTECTED_API = ("/api/", "/v1/")',SOURCE)
 def test_audit_arguments_browser_ko_nahi_bheje(self):
  section=SOURCE[SOURCE.index('async def dashboard_audit'):SOURCE.index('@app.get("/api/dashboard/memory")')]
  self.assertNotIn('e.arguments',section)
 def test_frontend_xss_escape_karta_hai(self):
  self.assertIn("replace(/[&<>\"']/g",SOURCE)
 def test_dashboard_no_mutation_endpoints(self):
  self.assertNotIn('@app.delete("/api/dashboard',SOURCE)
  self.assertNotIn('@app.post("/api/dashboard',SOURCE)
if __name__=='__main__':unittest.main()
