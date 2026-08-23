"""
SAARTHI Skills — "DIKHA DO MODE". TERA KILLER FEATURE.

    store.py     -> skills ka database (steps + parameters + stats)
    recorder.py  -> recording: steps capture karna
    runner.py    -> replay + SELF-HEALING (asli innovation)

Flow:
    1. recorder.start()
    2. kaam hota hai, steps capture hote hain
    3. recorder.finish("bijli ka bill") -> Skill
    4. store.save(skill)
    5. Baad mein: runner.run(skill, {"amount": 2500})
    6. UI badal gaya? runner khud theek kar deta hai.

Use:
    from saarthi.skills import SkillStore, SkillRecorder, SkillRunner
"""

from .recorder import RecordedAction, SkillRecorder
from .runner import SkillRunner, SkillRunResult, StepOutcome
from .store import (
    Skill,
    SkillStep,
    SkillStore,
    guess_parameter_name,
    parameterize_steps,
)

__all__ = [
    # Store
    "SkillStore",
    "Skill",
    "SkillStep",
    "parameterize_steps",
    "guess_parameter_name",
    # Recorder
    "SkillRecorder",
    "RecordedAction",
    # Runner
    "SkillRunner",
    "SkillRunResult",
    "StepOutcome",
]
