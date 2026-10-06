"""Non-annoying proactive interruption policy with persistence and deduplication."""
from __future__ import annotations
import hashlib, os, sqlite3, time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

@dataclass(frozen=True)
class InterruptionDecision:
    allowed: bool; reason: str

class InterruptionManager:
    def __init__(self, path: str|Path, max_per_hour:int=3, quiet_start:int=22, quiet_end:int=7):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.max_per_hour=max(0,int(max_per_hour)); self.quiet_start=quiet_start%24; self.quiet_end=quiet_end%24
        with sqlite3.connect(str(self.path)) as c:
            c.executescript("""CREATE TABLE IF NOT EXISTS proactive_events(
              id INTEGER PRIMARY KEY, key TEXT NOT NULL, text_hash TEXT NOT NULL, priority TEXT NOT NULL,
              announced_at REAL NOT NULL); CREATE INDEX IF NOT EXISTS idx_proactive_time ON proactive_events(announced_at);""")
    @classmethod
    def from_env(cls,path):
        def num(k,d):
            try:return int(os.getenv(k,str(d)))
            except ValueError:return d
        return cls(path,num("PROACTIVE_MAX_PER_HOUR",3),num("PROACTIVE_QUIET_START",22),num("PROACTIVE_QUIET_END",7))
    def _quiet(self,now):
        h=datetime.fromtimestamp(now).hour
        return self.quiet_start<=h or h<self.quiet_end if self.quiet_start>self.quiet_end else self.quiet_start<=h<self.quiet_end
    def decide(self,key,text,priority="normal",dedupe_hours=12,now=None):
        now=time.time() if now is None else now; priority=priority.lower(); digest=hashlib.sha256(text.encode()).hexdigest()
        if priority not in {"low","normal","high","critical"}:priority="normal"
        if self._quiet(now) and priority!="critical": return InterruptionDecision(False,"quiet_hours")
        with sqlite3.connect(str(self.path)) as c:
            duplicate=c.execute("SELECT 1 FROM proactive_events WHERE (key=? OR text_hash=?) AND announced_at>? LIMIT 1",
              (key,digest,now-max(0,dedupe_hours)*3600)).fetchone()
            if duplicate:return InterruptionDecision(False,"duplicate")
            count=c.execute("SELECT COUNT(*) FROM proactive_events WHERE announced_at>?",(now-3600,)).fetchone()[0]
        if priority not in {"high","critical"} and count>=self.max_per_hour:return InterruptionDecision(False,"hourly_budget")
        return InterruptionDecision(True,"allowed")
    def record(self,key,text,priority="normal",now=None):
        now=time.time() if now is None else now; digest=hashlib.sha256(text.encode()).hexdigest()
        with sqlite3.connect(str(self.path)) as c:
            c.execute("INSERT INTO proactive_events(key,text_hash,priority,announced_at) VALUES(?,?,?,?)",(key,digest,priority,now))
            c.execute("DELETE FROM proactive_events WHERE announced_at<?",(now-30*86400,))
    def allow_and_record(self,key,text,priority="normal",dedupe_hours=12,now=None):
        d=self.decide(key,text,priority,dedupe_hours,now)
        if d.allowed:self.record(key,text,priority,now)
        return d
