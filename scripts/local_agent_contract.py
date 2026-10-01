#!/usr/bin/env python3
"""Offline local-agent contract: trajectory v1.1, admission, and observable actions.

No model download, Ollama daemon, GPU, network call, or token.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.local_agent_contract import run_contract  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    del argv
    errors = run_contract()
    if errors:
        print("local-agent-contract FAILED:")
        for error in errors:
            print(error)
        return 1
    print("local-agent-contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
