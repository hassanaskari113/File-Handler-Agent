"""Central configuration. Reads .env (API key + the ONE working folder)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

API_KEY = (
    (os.getenv("API_KEY") or os.getenv("GROQ_API_KEY") or "")
    .strip()
    .strip('"')
    .strip("'")
)
MODEL = os.getenv(
    "MODEL", "openai/gpt-oss-120b"
).strip()  # tested model: groq:openai/gpt-oss-120b
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "2000"))

_raw_dir = os.getenv("WORK_DIR", "").strip().strip('"').strip("'")
WORK_DIR = os.path.realpath(os.path.expanduser(_raw_dir)) if _raw_dir else ""


def problems() -> list[str]:
    """Return a list of human-readable configuration problems (empty = all good)."""
    issues = []
    if not API_KEY or "PASTE" in API_KEY.upper() or API_KEY.upper().startswith("YOUR_"):
        issues.append("`API_KEY` is missing in `.env` (paste your Groq API key).")
    if (
        not WORK_DIR
        or "PASTE" in _raw_dir.upper()
        or not os.path.isabs(os.path.expanduser(_raw_dir))
    ):
        issues.append(
            "`WORK_DIR` is missing in `.env` (paste the FULL path of your working folder)."
        )
        return issues
    base = os.path.realpath(str(BASE_DIR))
    # The working folder must not be (or contain) the project itself, otherwise the
    # agent could touch its own source code / API key.
    if WORK_DIR == base or base.startswith(WORK_DIR + os.sep):
        issues.append(
            "`WORK_DIR` must not be the project folder or one of its parents."
        )
    if not issues:
        try:
            os.makedirs(WORK_DIR, exist_ok=True)
        except OSError as e:
            issues.append(f"Cannot create `WORK_DIR` ({e}).")
    return issues
