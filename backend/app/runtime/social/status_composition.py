"""Bind the status read to same-session Feed references."""
from app.runtime.social.feed_status import read_feed_status as read
from app.runtime.social.world_feed_queries import WorldFeedQueries

def read_feed_status(db, *, world_character_id):
    return read(db, world_character_id=world_character_id, references=WorldFeedQueries(db))
