"""Commit changes under CAPSULES_DIR. Off unless CAPSULE_GIT_COMMIT is set."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Iterable, List, Optional

from ..shared.config import config

logger = logging.getLogger("capsule.git")

_lock = threading.Lock()
_timer: Optional[threading.Timer] = None
_pending_paths: List[str] = []
_pending_message = "capsule: update"


def _git_bin() -> Optional[str]:
    return shutil.which("git")


def _run_git(args: List[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", config.git_author_name)
    env.setdefault("GIT_AUTHOR_EMAIL", config.git_author_email)
    env.setdefault("GIT_COMMITTER_NAME", config.git_author_name)
    env.setdefault("GIT_COMMITTER_EMAIL", config.git_author_email)
    return subprocess.run(
        [_git_bin() or "git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def repo_root(start: Optional[Path] = None) -> Optional[Path]:
    git = _git_bin()
    if not git:
        return None
    path = Path(start or config.capsules_dir).resolve()
    result = _run_git(["rev-parse", "--show-toplevel"], cwd=path if path.is_dir() else path.parent)
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def ensure_repo(capsules_dir: Optional[Path] = None) -> Optional[Path]:
    directory = Path(capsules_dir or config.capsules_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    root = repo_root(directory)
    if root:
        return root
    if not config.git_init:
        return None
    result = _run_git(["init"], cwd=directory)
    if result.returncode != 0:
        logger.warning("git init failed: %s", result.stderr.strip())
        return None
    return directory


def status() -> dict:
    root = repo_root()
    last = ""
    if root:
        result = _run_git(["log", "-1", "--oneline"], cwd=root)
        if result.returncode == 0:
            last = result.stdout.strip()
    return {
        "enabled": config.git_commit,
        "git": bool(_git_bin()),
        "repo": str(root) if root else None,
        "last_commit": last,
    }


def commit_now(paths: Iterable[str], message: str) -> bool:
    if not config.git_commit:
        return False
    if not _git_bin():
        logger.warning("CAPSULE_GIT_COMMIT is on but git is not on PATH")
        return False
    capsules = config.capsules_dir.resolve()
    root = ensure_repo(capsules)
    if not root:
        logger.warning("CAPSULE_GIT_COMMIT is on but %s is not in a git work tree", capsules)
        return False

    rels: List[str] = []
    for raw in paths:
        path = Path(raw).resolve()
        try:
            path.relative_to(capsules)
        except ValueError:
            continue
        try:
            rels.append(str(path.relative_to(root)))
        except ValueError:
            rels.append(str(path))
    if not rels:
        return False

    add = _run_git(["add", "--", *rels], cwd=root)
    if add.returncode != 0:
        logger.warning("git add failed: %s", add.stderr.strip())
        return False
    staged = _run_git(["diff", "--cached", "--quiet"], cwd=root)
    if staged.returncode == 0:
        return False
    commit = _run_git(["commit", "-m", message], cwd=root)
    if commit.returncode != 0:
        logger.warning("git commit failed: %s", commit.stderr.strip() or commit.stdout.strip())
        return False
    logger.info("git commit: %s", message)
    return True


def schedule_commit(paths: Iterable[str], message: str) -> None:
    if not config.git_commit:
        return
    delay = config.git_debounce
    with _lock:
        global _timer, _pending_message
        _pending_paths.extend(str(p) for p in paths)
        _pending_message = message
        if delay <= 0:
            batch = list(_pending_paths)
            _pending_paths.clear()
            commit_now(batch, message)
            return
        if _timer is not None:
            _timer.cancel()
        _timer = threading.Timer(delay, _flush)
        _timer.daemon = True
        _timer.start()


def _flush() -> None:
    with _lock:
        global _timer
        paths = list(_pending_paths)
        message = _pending_message
        _pending_paths.clear()
        _timer = None
    try:
        commit_now(paths, message)
    except Exception:
        logger.exception("git auto-commit failed")


def flush() -> None:
    """Run a pending debounced commit immediately. Used by tests."""
    if _timer is not None:
        _timer.cancel()
    _flush()
