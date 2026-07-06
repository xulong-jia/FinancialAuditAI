#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / "backend" / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and os.getenv("FINANCIAL_AUDIT_AI_PROVIDER_READINESS_VENV") != "1":
    os.environ["FINANCIAL_AUDIT_AI_PROVIDER_READINESS_VENV"] = "1"
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

sys.path.insert(0, str(ROOT / "backend"))

from app.services.provider_readiness_service import readiness  # noqa: E402


def main() -> int:
    print(json.dumps(readiness(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
