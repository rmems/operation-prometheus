"""Shared pytest setup.

Puts ``scripts/`` on ``sys.path`` once so every test module can ``import lib.*``
without repeating the boilerplate. Per-repo override tests (``test_overrides_*.py``)
rely on this: a new extract adds one small file and nothing else.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
