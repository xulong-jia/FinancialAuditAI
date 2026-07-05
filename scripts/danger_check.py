#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_PATHS = (
    ".env",
    "local_storage/",
    "uploads/",
    "reports/",
    "node_modules/",
    ".venv/",
    "venv/",
    "secrets/",
    "vector_index/",
)
FORBIDDEN_SUFFIXES = (".xlsx", ".csv")
SECRET_RE = re.compile(r"(?i)(api[_-]?key|secret|token|password)[\w-]*\s*[:=]\s*['\"]([^'\"]+)['\"]")
ALLOWLIST = {".env.example", "frontend/package-lock.json"}


def git_files() -> list[str]:
    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], text=True).splitlines()
    return sorted(set(tracked + staged))


def main() -> int:
    failures: list[str] = []
    for file_name in git_files():
        if file_name in ALLOWLIST:
            continue
        path = Path(file_name)
        if file_name.endswith(FORBIDDEN_SUFFIXES) or any(file_name == item.rstrip("/") or file_name.startswith(item) for item in FORBIDDEN_PATHS):
            failures.append(f"forbidden path: {file_name}")
            continue
        if not path.is_file() or path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".pdf", ".docx"}:
            continue
        text = path.read_text(errors="ignore")
        for match in SECRET_RE.finditer(text):
            name = match.group(1).casefold()
            value = match.group(2)
            matched = match.group(0).casefold()
            if (
                "password_hash" in matched
                or "storagekey" in matched
                or value in {"test-password", "admin-password", "change-me-local-only", "change-me-local-auth-secret"}
            ):
                continue
            failures.append(f"possible secret in {file_name}: {name}")
            break
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("danger_check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
