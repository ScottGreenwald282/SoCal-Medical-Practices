"""Previously delivered owners and signals. These names are not new."""

from __future__ import annotations

import csv
from pathlib import Path

from exit_factor_structural_pipeline.match import normalize_name

ROOT = Path(__file__).resolve().parents[1]


def load_blocked_names(root: Path | None = None) -> set[str]:
    base = root or ROOT
    paths = [
        base / "exit_factor_500" / "owner_ready.csv",
        base / "exit_factor_signals_50_new" / "qualified_signals.csv",
        base / "exit_factor_signals_50_new" / "baseline_excluded.tsv",
    ]
    blocked: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        delimiter = "\t" if path.suffix == ".tsv" else ","
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            for row in reader:
                name = (row.get("company") or "").strip()
                key = normalize_name(name)
                if key:
                    blocked.add(key)
    return blocked
