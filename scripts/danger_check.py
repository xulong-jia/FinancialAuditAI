#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_PATH_PARTS = {
    ".env",
    "local_storage",
    "uploads",
    "reports",
    "node_modules",
    ".venv",
    "venv",
    "secrets",
    "vector_index",
}
FORBIDDEN_SUFFIXES = {".xlsx", ".csv"}
ALLOWLIST = {".env.example", "frontend/package-lock.json"}
BINARY_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".pdf", ".docx"}
SAFE_VALUES = {
    "test-password",
    "admin-password",
    "change-me-local-only",
    "change-me-local-auth-secret",
    "unit-test-placeholder-key",
    "unit-test-azure-key",
}
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_api_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("authorization_bearer", re.compile(r"(?i)\bauthorization\s*[:=]\s*['\"]?bearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    (
        "generic_secret_assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|apikey|secret|token|password)\b[\w.-]*\s*[:=]\s*['\"]([^'\"\s]{12,})['\"]"
        ),
    ),
)


def git_files() -> list[str]:
    tracked = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only"], text=True).splitlines()
    return sorted(set(tracked + staged))


def staged_diff() -> str:
    return subprocess.check_output(["git", "diff", "--cached", "--unified=0", "--no-ext-diff"], text=True)


def forbidden_path_reason(file_name: str) -> str | None:
    if file_name in ALLOWLIST:
        return None
    path = Path(file_name)
    parts = set(path.parts)
    if path.name.startswith(".env") and path.name != ".env.example":
        return f"forbidden path: {file_name}"
    if path.suffix in FORBIDDEN_SUFFIXES or parts & FORBIDDEN_PATH_PARTS:
        return f"forbidden path: {file_name}"
    return None


def scan_text(text: str, file_name: str) -> list[str]:
    failures: list[str] = []
    for name, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            matched = match.group(0)
            value = match.group(2) if name == "generic_secret_assignment" else matched
            lowered = matched.casefold()
            if (
                "password_hash" in lowered
                or "storagekey" in lowered
                or any(safe in value for safe in SAFE_VALUES)
            ):
                continue
            failures.append(f"possible secret in {file_name}: {name}")
            break
    return failures


def scan_file(file_name: str) -> list[str]:
    if file_name in ALLOWLIST:
        return []
    reason = forbidden_path_reason(file_name)
    if reason:
        return [reason]
    path = Path(file_name)
    if not path.is_file() or path.suffix in BINARY_SUFFIXES:
        return []
    return scan_text(path.read_text(errors="ignore"), file_name)


def scan_staged_diff(diff_text: str) -> list[str]:
    added_lines = []
    for line in diff_text.splitlines():
        if line.startswith("+++") or not line.startswith("+"):
            continue
        added_lines.append(line[1:])
    return scan_text("\n".join(added_lines), "staged diff")


def run_check(file_names: list[str], diff_text: str) -> list[str]:
    failures: list[str] = []
    for file_name in file_names:
        failures.extend(scan_file(file_name))
    failures.extend(scan_staged_diff(diff_text))
    return sorted(set(failures))


def main() -> int:
    failures = run_check(git_files(), staged_diff())
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("danger_check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
