"""Standalone wrapper around `a4sec summarize` (works without installing the package).

    python scripts/summarize_results.py reports/json/*.json -o reports/summary.md
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a4sec.cli import app  # noqa: E402

if __name__ == "__main__":
    app(args=["summarize", *sys.argv[1:]], prog_name="summarize_results.py")
