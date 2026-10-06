from __future__ import annotations
import tempfile,time,unittest
from datetime import datetime
from pathlib import Path
from saarthi.proactive_context import InterruptionManager

def today(hour):
 n=datetime.now(); return n.replace(hour=hour,minute=0,second=0,microsecond=0).timestamp()

class InterruptionManagerTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory(); self.m=InterruptionManager(Path(self.t.name)/"p.db",2,22,7)
 def tearDown(self):self.t.cleanup()
 def test_quiet_hours_suppress_normal_but_not_critical(self):
  self.assertFalse(self.m.decide("a","normal","normal",now=today(23)).allowed)
  self.assertTrue(self.m.decide("b","critical","critical",now=today(23)).allowed)
 def test_duplicate_suppressed_across_restart(self):
  now=today(12); self.assertTrue(self.m.allow_and_record("weather","Rain today",now=now).allowed)
  reopened=InterruptionManager(self.m.path,2,22,7)
  d=reopened.decide("weather","Rain today",now=now+10)
  self.assertFalse(d.allowed); self.assertEqual(d.reason,"duplicate")
 def test_hourly_budget(self):
  now=today(12)
  self.m.record("a","one",now=now); self.m.record("b","two",now=now+1)
  d=self.m.decide("c","three",now=now+2)
  self.assertFalse(d.allowed); self.assertEqual(d.reason,"hourly_budget")
 def test_high_priority_bypasses_budget(self):
  now=today(12); self.m.record("a","one",now=now); self.m.record("b","two",now=now)
  self.assertTrue(self.m.decide("c","important","high",now=now+1).allowed)
 def test_same_text_different_key_dedupes(self):
  now=today(12); self.m.record("x","Drink water",now=now)
  self.assertEqual(self.m.decide("y","Drink water",now=now+1).reason,"duplicate")
 def test_invalid_priority_becomes_normal(self):
  self.assertTrue(self.m.decide("x","hello","nonsense",now=today(12)).allowed)

if __name__=='__main__':unittest.main()
