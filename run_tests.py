#!/usr/bin/env python3
"""
SAARTHI ke saare tests chalao.

    python run_tests.py              # sab kuch
    python run_tests.py -q           # sirf summary
    python run_tests.py known_bugs   # ek hi file (tests/test_known_bugs.py)

KOI EXTRA INSTALL NAHI CHAHIYE — stdlib `unittest` use hota hai.
Ye jaan-boojh ke hai: ₹0 budget aur purane laptop pe bhi chal jaaye.
(pytest installed ho to `pytest tests/` bhi chalega.)

Ye tests HARDWARE KE BINA chalte hain — mic, phone, browser, ya
internet ki zarurat nahi. Sab fake ho jaata hai. Isliye tu inhe
kabhi bhi chala sakta hai, aur chalane chahiye:

    - Koi bhi code badalne ke BAAD
    - `git pull` ke baad
    - Kuch toota lage to sabse pehle
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    quiet = "-q" in sys.argv or "--quiet" in sys.argv
    verbosity = 1 if quiet else 2

    loader = unittest.TestLoader()

    if args:
        # Ek specific file: "known_bugs" -> tests.test_known_bugs
        name = args[0]
        module = name if name.startswith("tests.") else f"tests.test_{name}"
        try:
            suite = loader.loadTestsFromName(module)
        except Exception as exc:  # noqa: BLE001
            print(f"'{module}' load nahi hua: {exc}\n")
            print("Available:")
            for path in sorted((ROOT / "tests").glob("test_*.py")):
                print(f"  {path.stem.replace('test_', '')}")
            return 2
    else:
        suite = loader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))

    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)

    print()
    if result.wasSuccessful():
        print(f"  SAB PASS — {result.testsRun} tests")
        return 0

    print(
        f"  {len(result.failures)} failures, {len(result.errors)} errors "
        f"({result.testsRun} tests)"
    )
    print("  Test ka naam padh — usme bug ka number likha hai.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
