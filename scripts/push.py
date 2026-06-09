#!/usr/bin/env python3
"""Stage, commit, and push dashboard changes to GitHub."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REMOTE = "origin"
BRANCH = "main"
DEFAULT_GIT_NAME = "godf23"
DEFAULT_GIT_EMAIL = "godf23@users.noreply.github.com"


def run(cmd: list[str], *, check: bool = True, env: dict | None = None) -> int:
    print(f"> {' '.join(cmd)}")
    kwargs = {"cwd": ROOT, "text": True}
    if env is not None:
        kwargs["env"] = env
    result = subprocess.run(cmd, **kwargs)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result.returncode


def git_identity_env() -> dict | None:
    """Supply author info for this commit only when git has no global identity."""
    import os

    name = subprocess.run(
        ["git", "config", "user.name"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    email = subprocess.run(
        ["git", "config", "user.email"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if name and email:
        return None

    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", name or DEFAULT_GIT_NAME)
    env.setdefault("GIT_AUTHOR_EMAIL", email or DEFAULT_GIT_EMAIL)
    env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
    env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
    if not name or not email:
        print(f"Using commit identity: {env['GIT_AUTHOR_NAME']} <{env['GIT_AUTHOR_EMAIL']}>")
    return env


def has_changes() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(result.stdout.strip())


def main() -> None:
    message = " ".join(sys.argv[1:]).strip()
    if not message:
        message = input("Commit message: ").strip()
    if not message:
        print("Aborted: commit message required.")
        sys.exit(1)

    if not (ROOT / ".git").is_dir():
        print("Error: not a git repository.")
        sys.exit(1)

    if has_changes():
        run(["git", "add", "-A"])
        run(["git", "commit", "-m", message], env=git_identity_env())
    else:
        print("No local changes to commit.")

    run(["git", "push", "-u", REMOTE, BRANCH])
    print()
    print(f"Pushed to https://github.com/godf23/personal-dashboard ({BRANCH})")
    print("Running dashboards will pick up the update within a few minutes.")


if __name__ == "__main__":
    main()
