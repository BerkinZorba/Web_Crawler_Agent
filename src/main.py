"""CLI entry point for the localhost crawler/search demo.

Run from the project root:

  python -m src.main --help
  python -m src.main COMMAND ...

See ``src.cli`` for commands and examples.
"""

from __future__ import annotations

import sys

from src.cli import main

if __name__ == "__main__":
    sys.exit(main())
