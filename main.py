"""Compatibility entrypoint for platforms that run ``uvicorn main:app``."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from resume_matcher.main import app, create_app  # noqa: E402,F401
