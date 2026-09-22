"""Read-only Docker readiness evidence; emits no content or credentials.

Pipe to the backend container with python -; canonical data remains query-only.
"""
import argparse
import hashlib
import json
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from app.runtime.persistence.model_registration import register_models
from app.runtime.social.world_feed_queries import WorldFeedQueries
from app.domains.social.service.world_feed import load_ready_search_profile
from app.domains.social.exceptions import WorldFeedReadinessError
from app.domains.world_characters.service.approved_setup import get_approved_pair
from app.domains.world_characters.policies.approved_setup import approved_pair_matches_world

register_models()
root = Path("/var/lib/angmoo/canonical")
relative = json.loads((root / "current-generation.json").read_text())["relative_path"]
engine = create_engine("sqlite:///" + str(root / relative / "angmoo.sqlite3"))
@event.listens_for(engine, "connect")
def readonly(connection, record):
    connection.execute("PRAGMA query_only=ON")

parser = argparse.ArgumentParser()
parser.add_argument("--characters", nargs="+", required=True)
args = parser.parse_args()
results = []
with Session(engine) as db:
    refs = WorldFeedQueries(db)
    for alias, identity in enumerate(args.characters):
        wc = refs.world_character(identity)
        pair = get_approved_pair(db, identity)
        character = refs.character(wc.character_id)
        world = refs.world(wc.world_id)
        baseline = [wc.character_contract_hash, wc.world_contract_hash]
        for item in pair or ():
            baseline += [item.id, item.character_contract_hash, item.world_contract_hash]
        try:
            load_ready_search_profile(db, references=refs, world_character_id=identity)
            outcome = "ready"
        except WorldFeedReadinessError as error:
            outcome = error.reason_code
        from app.runtime.social.feed_status import read_feed_status
        current = read_feed_status(db, world_character_id=identity)
        attempt = current.last_attempt
        results.append({"last_attempt": ({"result": attempt.result, "candidate_count": attempt.candidate_count,
            "delivered_count": attempt.delivered_count, "delivery_state": attempt.delivery_state} if attempt else None),
            "character": alias, "feed": outcome,
            "common_approved_policy": bool(pair and approved_pair_matches_world(wc, *pair, world_hash=world.contract_hash)),
            "persona_changed": (refs.character_hash(character) != pair[0].character_contract_hash) if pair else None,
            "approved_provenance_digest": hashlib.sha256(json.dumps(baseline).encode()).hexdigest()})
print(json.dumps({"query_only": True, "results": results}))
