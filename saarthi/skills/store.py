"""
Skill Store — "DIKHA DO MODE" ka dil. YE TERA KILLER FEATURE HAI.

Idea:
    Tu ek baar kaam karke dikhata hai.
    SAARTHI steps yaad kar leta hai.
    Agli baar bas naam bolna hai — kaam khud ho jaayega.

    Tu:     "dekh, main dikha raha hun"  [kaam karta hai]
    SAARTHI: "samajh gaya. naam kya du?"
    Tu:     "bijli ka bill"
    ...
    Agle mahine:
    Tu:     "bijli ka bill bhar de"
    SAARTHI: "kar diya."

Do cheezein isko special banati hain:

1. PARAMETERIZATION
   Amount har baar badalta hai. Isliye recording ke waqt values ko
   {amount} jaise placeholders mein badal dete hain.

2. SELF-HEALING (ye asli innovation hai)
   Har step do tareeke se store hota hai:
       PRIMARY  -> target_text  ("Recharge" button)
       FALLBACK -> coordinates  (540, 360)

   App ka UI badal jaaye? Coordinates bekaar ho jaate hain, par text
   se element phir mil jaata hai. Aur text bhi badle to LLM screen
   dekh ke naya raasta dhoondh leta hai.

   Normal automation (Tasker/macros) yahin toot jaate hain.
   SAARTHI nahi tootega.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..config import settings as default_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL UNIQUE,
    description   TEXT    DEFAULT '',
    device_kind   TEXT    DEFAULT 'android',
    params        TEXT    DEFAULT '[]',
    created_at    REAL    NOT NULL,
    updated_at    REAL    NOT NULL,
    run_count     INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    last_run      REAL
);

CREATE TABLE IF NOT EXISTS skill_steps (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id      INTEGER NOT NULL,
    position      INTEGER NOT NULL,
    action        TEXT    NOT NULL,
    params        TEXT    DEFAULT '{}',
    target_text   TEXT    DEFAULT '',
    target_coords TEXT,
    notes         TEXT    DEFAULT '',
    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_steps_skill ON skill_steps(skill_id, position);
"""


# ======================================================================
#  Data types
# ======================================================================


@dataclass
class SkillStep:
    """
    Ek step jo skill ke andar hai.

    Dono targets store karte hain — yahi self-healing ka base hai.
    """

    action: str                              # kaunsa tool: app_kholo, text_pe_tap...
    params: dict = field(default_factory=dict)

    # Self-healing ke liye do raaste
    target_text: str = ""                    # PRIMARY: text se dhoondo
    target_coords: tuple[int, int] | None = None  # FALLBACK: coordinates

    notes: str = ""                          # LLM ke liye hint

    def resolve(self, values: dict[str, object]) -> dict:
        """
        Placeholders ko asli values se bharo.

        {"amount": "{amount}"} + {"amount": 2500} -> {"amount": 2500}
        """
        resolved: dict = {}

        for key, value in self.params.items():
            if isinstance(value, str):
                # Poora value ek placeholder hai
                match = re.fullmatch(r"\{(\w+)\}", value.strip())
                if match and match.group(1) in values:
                    resolved[key] = values[match.group(1)]
                    continue

                # Text ke andar placeholders hain
                def replace(m: re.Match) -> str:
                    name = m.group(1)
                    return str(values.get(name, m.group(0)))

                resolved[key] = re.sub(r"\{(\w+)\}", replace, value)
            else:
                resolved[key] = value

        return resolved

    def placeholders(self) -> set[str]:
        """Is step mein kaunse placeholders hain."""
        found: set[str] = set()
        for value in self.params.values():
            if isinstance(value, str):
                found.update(re.findall(r"\{(\w+)\}", value))
        return found

    def __str__(self) -> str:
        parts = [self.action]
        if self.target_text:
            parts.append(f'"{self.target_text}"')
        if self.params:
            args = ", ".join(f"{k}={v}" for k, v in self.params.items())
            parts.append(f"({args})")
        return " ".join(parts)


@dataclass
class Skill:
    """Ek seekha hua kaam."""

    name: str
    description: str = ""
    device_kind: str = "android"
    steps: list[SkillStep] = field(default_factory=list)
    params: list[str] = field(default_factory=list)

    run_count: int = 0
    success_count: int = 0
    last_run: float | None = None

    @property
    def reliability(self) -> float:
        """Kitna bharosemand hai (0.0 se 1.0)."""
        if self.run_count == 0:
            return 0.0
        return self.success_count / self.run_count

    def required_params(self) -> set[str]:
        """Chalane ke liye kaunse values chahiye."""
        needed: set[str] = set()
        for step in self.steps:
            needed |= step.placeholders()
        return needed

    def summary(self) -> str:
        """Ek line ka description — LLM ke prompt ke liye."""
        param_note = ""
        needed = self.required_params()
        if needed:
            param_note = f" (chahiye: {', '.join(sorted(needed))})"

        reliability_note = ""
        if self.run_count > 0:
            reliability_note = (
                f" [{self.success_count}/{self.run_count} baar chala]"
            )

        desc = self.description or f"{len(self.steps)} steps ka kaam"
        return f"{self.name}: {desc}{param_note}{reliability_note}"

    def explain(self) -> str:
        """Poora detail — user ko dikhane ke liye."""
        lines = [f"Skill: {self.name}"]
        if self.description:
            lines.append(f"  Kaam: {self.description}")
        lines.append(f"  Device: {self.device_kind}")

        needed = self.required_params()
        if needed:
            lines.append(f"  Chahiye: {', '.join(sorted(needed))}")

        if self.run_count:
            lines.append(
                f"  Record: {self.success_count} success / {self.run_count} tries"
            )

        lines.append(f"  Steps ({len(self.steps)}):")
        for i, step in enumerate(self.steps, 1):
            lines.append(f"    {i}. {step}")

        return "\n".join(lines)


# ======================================================================
#  Parameterization — recording ko reusable banane ka jaadu
# ======================================================================

# Ye patterns batate hain ki kaunsi value har baar badalti hai
VARIABLE_HINTS: list[tuple[str, str]] = [
    (r"^\d+(?:\.\d+)?$", "amount"),          # Sirf number = amount
    (r"^\+?91\d{10}$", "number"),            # Indian phone number
    (r"^\d{10}$", "number"),
    (r"^[\w.+-]+@[\w-]+\.[\w.]+$", "email"),
    (r"^\d{4}-\d{2}-\d{2}$", "date"),
]


def guess_parameter_name(value: str) -> str | None:
    """
    Ye value variable honi chahiye? To iska naam kya ho?

    >>> guess_parameter_name("2500")
    'amount'
    >>> guess_parameter_name("Recharge")
    None
    """
    cleaned = value.strip()
    if not cleaned:
        return None

    for pattern, name in VARIABLE_HINTS:
        if re.fullmatch(pattern, cleaned):
            return name
    return None


def parameterize_steps(
    steps: list[SkillStep],
) -> tuple[list[SkillStep], list[str]]:
    """
    Recorded steps ko reusable banao.

    Jo values har baar badalti hain unko {placeholder} bana do.

    Ye "ek baar dikhao, hamesha chale" ko sach karta hai — warna skill
    sirf usi ek amount ke liye kaam karti.
    """
    new_steps: list[SkillStep] = []
    found_params: list[str] = []
    counters: dict[str, int] = {}

    for step in steps:
        new_params: dict = {}

        for key, value in step.params.items():
            if not isinstance(value, str):
                new_params[key] = value
                continue

            guessed = guess_parameter_name(value)
            if guessed is None:
                new_params[key] = value
                continue

            # Ek hi type ke do params ho to amount, amount2...
            counters[guessed] = counters.get(guessed, 0) + 1
            param_name = (
                guessed if counters[guessed] == 1 else f"{guessed}{counters[guessed]}"
            )

            new_params[key] = f"{{{param_name}}}"
            found_params.append(param_name)

        new_steps.append(
            SkillStep(
                action=step.action,
                params=new_params,
                target_text=step.target_text,
                target_coords=step.target_coords,
                notes=step.notes,
            )
        )

    return new_steps, found_params


# ======================================================================
#  Store
# ======================================================================


class SkillStore:
    """Seekhi hui skills ka database."""

    def __init__(self, db_path: Path | str | None = None):
        if db_path is None:
            db_path = default_settings.data_dir / "skills.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    async def _run(self, func, *args):
        return await asyncio.to_thread(func, *args)

    # ------------------------------------------------------------------
    #  Save
    # ------------------------------------------------------------------

    def _save_sync(self, skill: Skill, auto_parameterize: bool) -> Skill:
        steps = skill.steps
        params = list(skill.params)

        if auto_parameterize:
            steps, detected = parameterize_steps(steps)
            # Duplicate hataye bina order maintain karo
            for name in detected:
                if name not in params:
                    params.append(name)

        now = time.time()

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO skills
                    (name, description, device_kind, params,
                     created_at, updated_at, run_count, success_count)
                VALUES (?, ?, ?, ?, ?, ?, 0, 0)
                ON CONFLICT(name) DO UPDATE SET
                    description = excluded.description,
                    device_kind = excluded.device_kind,
                    params      = excluded.params,
                    updated_at  = excluded.updated_at
                """,
                (
                    skill.name.strip().lower(),
                    skill.description,
                    skill.device_kind,
                    json.dumps(params),
                    now,
                    now,
                ),
            )

            # Skill id nikaalo (naya ya existing)
            row = conn.execute(
                "SELECT id FROM skills WHERE name = ?",
                (skill.name.strip().lower(),),
            ).fetchone()
            skill_id = row["id"]

            # Purane steps hata ke naye daalo (re-teach support)
            conn.execute("DELETE FROM skill_steps WHERE skill_id = ?", (skill_id,))

            for position, step in enumerate(steps):
                conn.execute(
                    """
                    INSERT INTO skill_steps
                        (skill_id, position, action, params,
                         target_text, target_coords, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        skill_id,
                        position,
                        step.action,
                        json.dumps(step.params, ensure_ascii=False),
                        step.target_text,
                        json.dumps(step.target_coords) if step.target_coords else None,
                        step.notes,
                    ),
                )

        return Skill(
            name=skill.name.strip().lower(),
            description=skill.description,
            device_kind=skill.device_kind,
            steps=steps,
            params=params,
        )

    async def save(self, skill: Skill, auto_parameterize: bool = True) -> Skill:
        """
        Skill save karo.

        auto_parameterize=True ho to values automatically {placeholder}
        ban jaati hain — isse skill reusable ho jaati hai.
        """
        if not skill.name.strip():
            raise ValueError("Skill ka naam khali nahi ho sakta")
        return await self._run(self._save_sync, skill, auto_parameterize)

    # ------------------------------------------------------------------
    #  Load
    # ------------------------------------------------------------------

    def _row_to_skill(self, conn: sqlite3.Connection, row: sqlite3.Row) -> Skill:
        step_rows = conn.execute(
            """
            SELECT action, params, target_text, target_coords, notes
            FROM skill_steps WHERE skill_id = ? ORDER BY position
            """,
            (row["id"],),
        ).fetchall()

        steps: list[SkillStep] = []
        for step_row in step_rows:
            coords = None
            if step_row["target_coords"]:
                try:
                    parsed = json.loads(step_row["target_coords"])
                    if isinstance(parsed, list) and len(parsed) == 2:
                        coords = (int(parsed[0]), int(parsed[1]))
                except (json.JSONDecodeError, ValueError, TypeError):
                    coords = None

            try:
                params = json.loads(step_row["params"] or "{}")
            except json.JSONDecodeError:
                params = {}

            steps.append(
                SkillStep(
                    action=step_row["action"],
                    params=params,
                    target_text=step_row["target_text"] or "",
                    target_coords=coords,
                    notes=step_row["notes"] or "",
                )
            )

        try:
            skill_params = json.loads(row["params"] or "[]")
        except json.JSONDecodeError:
            skill_params = []

        return Skill(
            name=row["name"],
            description=row["description"] or "",
            device_kind=row["device_kind"] or "android",
            steps=steps,
            params=skill_params,
            run_count=row["run_count"] or 0,
            success_count=row["success_count"] or 0,
            last_run=row["last_run"],
        )

    def _get_sync(self, name: str) -> Skill | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM skills WHERE name = ?", (name.strip().lower(),)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_skill(conn, row)

    async def get(self, name: str) -> Skill | None:
        """Naam se skill nikaalo."""
        return await self._run(self._get_sync, name)

    def _find_sync(self, query: str, limit: int) -> list[Skill]:
        cleaned = query.strip().lower()

        with self._connect() as conn:
            # 1. Exact match
            row = conn.execute(
                "SELECT * FROM skills WHERE name = ?", (cleaned,)
            ).fetchone()
            if row is not None:
                return [self._row_to_skill(conn, row)]

            # 2. Substring match — dono taraf
            #    "bijli ka bill bhar de" ke andar "bijli ka bill" hai
            rows = conn.execute(
                """
                SELECT * FROM skills
                WHERE name LIKE ? OR ? LIKE '%' || name || '%'
                   OR description LIKE ?
                ORDER BY
                    CASE WHEN ? LIKE '%' || name || '%' THEN 0 ELSE 1 END,
                    LENGTH(name) DESC,
                    run_count DESC
                LIMIT ?
                """,
                (f"%{cleaned}%", cleaned, f"%{cleaned}%", cleaned, limit),
            ).fetchall()

            return [self._row_to_skill(conn, r) for r in rows]

    async def find(self, query: str, limit: int = 5) -> list[Skill]:
        """
        Hinglish command se skill dhoondo.

        "bijli ka bill bhar de" -> skill "bijli ka bill" mil jaayegi.
        Ye important hai kyunki user hamesha exact naam nahi bolta.
        """
        return await self._run(self._find_sync, query, limit)

    def _list_sync(self, limit: int) -> list[Skill]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM skills ORDER BY run_count DESC, updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_skill(conn, r) for r in rows]

    async def list_skills(self, limit: int = 100) -> list[Skill]:
        """Saari skills."""
        return await self._run(self._list_sync, limit)

    # ------------------------------------------------------------------
    #  Delete & stats
    # ------------------------------------------------------------------

    def _delete_sync(self, name: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM skills WHERE name = ?", (name.strip().lower(),)
            )
            return cursor.rowcount > 0

    async def delete(self, name: str) -> bool:
        """Skill bhool jao."""
        return await self._run(self._delete_sync, name)

    def _mark_run_sync(self, name: str, success: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE skills SET
                    run_count     = run_count + 1,
                    success_count = success_count + ?,
                    last_run      = ?
                WHERE name = ?
                """,
                (1 if success else 0, time.time(), name.strip().lower()),
            )

    async def mark_run(self, name: str, success: bool) -> None:
        """
        Skill chali — record karo.

        Isse pata chalta hai kaunsi skill bharosemand hai aur kaunsi
        toot rahi hai (matlab UI badal gaya, self-healing chahiye).
        """
        await self._run(self._mark_run_sync, name, success)

    # ------------------------------------------------------------------
    #  Context for the LLM
    # ------------------------------------------------------------------

    async def build_context(self, limit: int = 30) -> list[str]:
        """
        System prompt ke liye skills ki list.

        Agent ko pata hona chahiye ki wo kya-kya seekh chuka hai,
        warna wo dobara zero se karega.
        """
        skills = await self.list_skills(limit=limit)
        return [skill.summary() for skill in skills]

    def _stats_sync(self) -> dict[str, int]:
        with self._connect() as conn:
            skills = conn.execute("SELECT COUNT(*) AS n FROM skills").fetchone()["n"]
            steps = conn.execute(
                "SELECT COUNT(*) AS n FROM skill_steps"
            ).fetchone()["n"]
            runs = conn.execute(
                "SELECT COALESCE(SUM(run_count), 0) AS n FROM skills"
            ).fetchone()["n"]
        return {"skills": skills, "steps": steps, "total_runs": runs}

    async def stats(self) -> dict[str, int]:
        return await self._run(self._stats_sync)
