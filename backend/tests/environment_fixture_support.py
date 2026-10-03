"""Explicit detected environment for fixtures whose calendar is part of their intent.

Unknown installations intentionally remain en/UTC in product code. Tests that
were written against a Korean local day must now supply that input explicitly.
"""
from app.domains.identity.models_environment import LocalEnvironment


def seed_environment(db, owner_id, timezone="Asia/Seoul", locale="ko-KR"):
    row = db.get(LocalEnvironment, owner_id)
    if row is None:
        row = LocalEnvironment(owner_id=owner_id, installation_id="fixture-installation",
            preferred_language=locale, timezone=timezone, environment_revision=1, timezone_revision=1)
        db.add(row)
    return row
