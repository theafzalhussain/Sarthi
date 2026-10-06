from __future__ import annotations
import tempfile, unittest
from pathlib import Path
from saarthi.conversation_style import infer_style, preferred_reply_length
from saarthi.personal import PersonalStore

class ConversationStyleTests(unittest.TestCase):
 def test_english_user_gets_english(self):
  s=infer_style("Please open Chrome and search for today's weather")
  self.assertEqual(s.language,"english"); self.assertEqual(s.tone,"formal")
  self.assertIn("natural English",s.directive())
 def test_hinglish_bhai_gets_casual_hinglish(self):
  s=infer_style("bhai chrome kholo aur weather dhoondh do")
  self.assertEqual(s.language,"hinglish"); self.assertEqual(s.tone,"casual")
  self.assertIn("Hinglish",s.directive())
 def test_explicit_short_and_detailed(self):
  self.assertEqual(infer_style("short answer please").length,"short")
  self.assertEqual(infer_style("explain step by step in detail").length,"detailed")
 def test_urgent_avoids_preamble(self):
  s=infer_style("bhai abhi jaldi email bhejo")
  self.assertTrue(s.urgency); self.assertIn("act first",s.directive())
 def test_frustration_is_not_argumentative(self):
  s=infer_style("ye baar baar galat ho raha hai, not working")
  self.assertTrue(s.frustrated); self.assertIn("do not argue",s.directive())
 def test_fixed_language_setting_wins(self):
  self.assertEqual(infer_style("bhai kya haal",language_setting="english").language,"english")
 def test_saved_explicit_length_preference(self):
  with tempfile.TemporaryDirectory() as d:
   store=PersonalStore(Path(d)/"p.db")
   store.remember("preference","user","reply_style","short Hinglish replies")
   self.assertEqual(preferred_reply_length(store),"short")
   self.assertEqual(infer_style("tell me about Python",preferred_length=preferred_reply_length(store)).length,"short")

if __name__=='__main__': unittest.main()
