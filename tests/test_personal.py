from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from saarthi.personal import PersonalStore

class PersonalStoreTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory(); self.p=Path(self.t.name)/"p.db"; self.s=PersonalStore(self.p)
 def tearDown(self): self.t.cleanup()
 def test_people_preferences_routines_persist(self):
  self.s.remember("person","Mummy","relation","mother")
  self.s.remember("preference","user","reply_style","short Hinglish")
  self.s.remember("routine","user","wake_time","7 AM")
  r=PersonalStore(self.p)
  self.assertEqual(len(r.search()),3); self.assertEqual(r.get("person","Mummy","relation").value,"mother")
 def test_correction_updates_without_duplicate(self):
  a=self.s.remember("correction","Rahul","identity","office Rahul")
  b=self.s.remember("correction","Rahul","identity","school Rahul")
  self.assertEqual(a.id,b.id); self.assertEqual(self.s.search("Rahul")[0].value,"school Rahul")
 def test_confidence_clamped_and_invalid_rejected(self):
  x=self.s.remember("goal","user","fitness","run 5k",9)
  self.assertEqual(x.confidence,1)
  with self.assertRaises(ValueError): self.s.remember("guess","u","x","y")
 def test_context_grouped(self):
  self.s.remember("project","Sarthi","goal","Power Jarvis")
  c=self.s.context(); self.assertIn("[Project]",c); self.assertIn("Power Jarvis",c)
 def test_forget(self):
  x=self.s.remember("preference","user","tea","less sugar")
  self.assertTrue(self.s.forget(x.id)); self.assertFalse(self.s.forget(x.id))

if __name__=='__main__': unittest.main()
