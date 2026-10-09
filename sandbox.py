"""One-folder sandbox: every tool resolves paths through safe_path()."""

import os

from config import WORK_DIR


class SandboxError(Exception):
    """Raised when a path points outside the working folder."""


def _norm(p: str) -> str:
    return os.path.normcase(os.path.realpath(p))


def is_inside(path: str, root: str = WORK_DIR) -> bool:
    try:
        r = _norm(root)
        return os.path.commonpath([_norm(path), r]) == r
    except ValueError:  # different drives on Windows
        return False


def safe_path(path: str) -> str:
    """Resolve `path` against WORK_DIR. Raises SandboxError if it escapes the folder
    (via '..', absolute paths, drive letters or symlinks)."""
    raw = (
        "."
        if path is None or not str(path).strip()
        else str(path).strip().strip('"').strip("'")
    )
    if "\0" in raw:
        raise SandboxError("Invalid path.")
    full = raw if os.path.isabs(raw) else os.path.join(WORK_DIR, raw)
    real = os.path.realpath(full)
    if not is_inside(real):
        raise SandboxError(f"Access denied: '{raw}' is outside the working folder.")
    return real


def rel(path: str) -> str:
    """Pretty path relative to the working folder."""
    r = os.path.relpath(path, WORK_DIR)
    return "." if r == "." else r.replace("\\", "/")
