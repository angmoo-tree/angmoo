"""Materialize and validate this run's selection before any conditional work."""
import json
import os
from pathlib import Path
from impact import read_plan


def main() -> int:
    path = Path(".ci/impact.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(os.environ["CI_IMPACT_PLAN"], encoding="utf-8")
    plan = read_plan(path)
    print(json.dumps({"source_sha": plan["source_sha"], "selection_sha256": plan["selection_sha256"], "profile": plan["effective"]["backend"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
