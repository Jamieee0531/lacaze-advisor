"""Convenience entry point: uv run python scripts/run_cases.py [batch options]."""

import sys

from lacaze.interfaces.cli import main

if __name__ == "__main__":
    sys.argv.insert(1, "batch")
    main()
