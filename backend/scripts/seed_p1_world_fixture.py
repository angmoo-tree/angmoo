"""Seed the canonical local P1 World foundation without provider calls."""

from __future__ import annotations

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import SessionLocal
from app.services import world_foundation


def seed() -> str:
    with SessionLocal() as db:
        report = world_foundation.ensure_angmoo_global_foundation(db)
        if not report.seeded or report.world_id is None:
            raise RuntimeError(
                "Create at least one local user before seeding the P1 World fixture."
            )
        db.commit()
        return report.world_id


if __name__ == "__main__":
    print(seed())
