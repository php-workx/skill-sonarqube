#!/usr/bin/env python3
"""Run skill-creator's quick validator inside the repo's Python environment."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def find_validator() -> Path | None:
    env_path = os.environ.get("SKILL_CREATOR_VALIDATE_SCRIPT", "").strip()
    candidates = [
        Path(env_path) if env_path else None,
        Path.home() / ".agents" / "skills" / "skill-creator" / "scripts" / "quick_validate.py",
        Path.home() / ".codex" / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py",
        Path.home() / ".codex" / "skills" / "skill-creator" / "scripts" / "quick_validate.py",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    return None


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "skill"
    validator = find_validator()
    if validator is None:
        print(
            "error: skill-creator quick_validate.py not found. "
            "Set SKILL_CREATOR_VALIDATE_SCRIPT or install the skill-creator skill locally.",
            file=sys.stderr,
        )
        return 1

    cmd = [sys.executable, str(validator), target]
    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
