"""CLI: PYTHONPATH=. python -m exit_factor_structural_pipeline pilot --max-details 50"""

from __future__ import annotations

import argparse
import json

from exit_factor_structural_pipeline.pipeline import Pilot


def main() -> None:
    parser = argparse.ArgumentParser(description="Iowa structural-signal ingestion pilot")
    sub = parser.add_subparsers(dest="command", required=True)
    pilot = sub.add_parser("pilot")
    pilot.add_argument("--max-details", type=int, default=50)
    args = parser.parse_args()
    if args.command == "pilot":
        report = Pilot(max_details=args.max_details).run()
        print(json.dumps({
            "entities_parsed": report["counts"]["entities_parsed"],
            "filing_changes": report["counts"]["filing_changes"],
            "intersection": report["counts"]["qualified_intersection"],
            "accepted": report["accepted_new_owner_verified"],
            "local_spent_after": report["credits"].get("local_spent_after"),
        }))


if __name__ == "__main__":
    main()
