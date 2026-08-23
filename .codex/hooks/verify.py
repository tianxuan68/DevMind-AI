"""Run the smallest useful checks for Codex lifecycle hooks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NPM = "npm.cmd" if sys.platform == "win32" else "npm"
VENV_BIN = ROOT / (".venv/Scripts" if sys.platform == "win32" else ".venv/bin")
RUFF = VENV_BIN / ("ruff.exe" if sys.platform == "win32" else "ruff")
PYTEST = VENV_BIN / ("pytest.exe" if sys.platform == "win32" else "pytest")
PYTHON_SUFFIXES = {".py", ".pyi"}
FRONTEND_PREFIX = "front/"
CRITICAL = re.compile(r"(^|/)(auth|security|config)(/|$)|(^|/)(Dockerfile|docker-compose\.ya?ml|pyproject\.toml|requirements\.txt|schema\.sql|.*\.ini)$", re.I)
SECRET = re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*[\"'][^\"']{8,}[\"']|\b(?:sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16})\b")


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False
    )


def run(*args: str, env: dict[str, str] | None = None) -> bool:
    print("+", " ".join(args))
    result = subprocess.run(args, cwd=ROOT, text=True, check=False, env=env)
    return result.returncode == 0


def changed_files() -> list[str]:
    result = git("diff", "--name-only", "HEAD")
    return [line for line in result.stdout.splitlines() if line]


def security_check(files: list[str]) -> bool:
    if not any(CRITICAL.search(path) for path in files):
        return True
    print("Running security checks for sensitive changes")
    clean = git("diff", "--check", "HEAD").returncode == 0
    diff = git("diff", "--unified=0", "HEAD").stdout
    leaked = [line for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++") and SECRET.search(line)]
    if leaked:
        print("Potential hard-coded secret in changed lines", file=sys.stderr)
        clean = False
    return clean


def verify(full: bool) -> bool:
    files = changed_files()
    if not files:
        print("No uncommitted changes; verification skipped")
        return True
    ok = security_check(files)
    python_changed = full or any(Path(path).suffix in PYTHON_SUFFIXES or path == "pyproject.toml" for path in files)
    frontend_changed = full or any(path.startswith(FRONTEND_PREFIX) for path in files)
    if python_changed:
        targets = [path for path in files if Path(path).suffix in PYTHON_SUFFIXES]
        lint_targets = ["."] if full else targets
        if lint_targets:
            ok = run(str(RUFF), "check", "--select", "E9", *lint_targets) and ok
        env = {**os.environ, "PYTHONPATH": str(ROOT)}
        # Integration and model tests need external services or local model weights.
        tests = ["tests/unit"]
        ok = run(str(PYTEST), *tests, "-q", env=env) and ok
    if frontend_changed:
        ok = run(NPM, "--prefix", "front", "run", "build") and ok
    return ok


def already_verified() -> bool:
    diff = git("diff", "--binary", "HEAD").stdout.encode()
    digest = hashlib.sha256(diff).hexdigest()
    state = Path(git("rev-parse", "--git-path", "codex-hooks/last-stop").stdout.strip())
    if not state.is_absolute():
        state = ROOT / state
    if state.exists() and state.read_text(encoding="utf-8") == digest:
        print("Changes already verified in this worktree")
        return True
    if verify(full=False):
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(digest, encoding="utf-8")
        return True
    return False


def is_git_commit(payload: dict[str, object]) -> bool:
    return bool(re.search(r"\bgit\b[^\n;&|]*\bcommit\b", json.dumps(payload, ensure_ascii=False)))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}
    mode = sys.argv[1]
    if mode == "precommit":
        if not is_git_commit(payload):
            return 0
        return 0 if verify(full=True) else 2
    return 0 if already_verified() else 2


if __name__ == "__main__":
    raise SystemExit(main())
