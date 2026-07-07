#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
from subprocess import check_output
from urllib.parse import urlparse

DEFAULT_AUTH_SECRET = "change-me-local-auth-secret"
DEFAULT_DB_PASSWORDS = {"", "password", "postgres", "change-me-local-only"}
DEV_CORS = {"*", "http://localhost:5173", "http://127.0.0.1:5173"}
FORBIDDEN_TRACKED_PARTS = {".env", "local_storage", "uploads", "reports", "vector_index"}
ALLOWLIST = {".env.example"}


def git_files() -> list[str]:
    tracked = check_output(["git", "ls-files"], text=True).splitlines()
    staged = check_output(["git", "diff", "--cached", "--name-only"], text=True).splitlines()
    return sorted(set(tracked + staged))


def check_environment(env: dict[str, str]) -> list[str]:
    if env.get("ENVIRONMENT") != "production":
        return []

    failures: list[str] = []
    auth_secret = env.get("AUTH_SECRET_KEY", "")
    if not auth_secret or auth_secret == DEFAULT_AUTH_SECRET:
        failures.append("production AUTH_SECRET_KEY must be set and must not use the local default")

    db_url = env.get("DATABASE_URL", "")
    parsed = urlparse(db_url)
    if not db_url or (parsed.password or "") in DEFAULT_DB_PASSWORDS:
        failures.append("production DATABASE_URL must not use an empty or default database password")

    cors = {origin.strip() for origin in env.get("CORS_ORIGINS", "").split(",") if origin.strip()}
    if not cors or cors & DEV_CORS or any("localhost" in origin or "127.0.0.1" in origin for origin in cors):
        failures.append("production CORS_ORIGINS must be explicit non-localhost origins")

    return failures


def check_tracked_paths(file_names: list[str]) -> list[str]:
    failures: list[str] = []
    for file_name in file_names:
        if file_name in ALLOWLIST:
            continue
        path = Path(file_name)
        parts = set(path.parts)
        if path.name.startswith(".env") and path.name != ".env.example":
            failures.append(f"forbidden tracked env file: {file_name}")
        elif parts & FORBIDDEN_TRACKED_PARTS:
            failures.append(f"forbidden tracked runtime artifact: {file_name}")
    return failures


def run_check(env: dict[str, str], file_names: list[str]) -> list[str]:
    return sorted(set(check_environment(env) + check_tracked_paths(file_names)))


def main() -> int:
    failures = run_check(dict(os.environ), git_files())
    if failures:
        print("\n".join(failures))
        return 1
    print("production_safety_check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
