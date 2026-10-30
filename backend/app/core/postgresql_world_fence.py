"""Short PostgreSQL shared-row fence against accepted World deletion."""
from sqlalchemy import text

def fence_world(connection,world):
    connection.execute(text('SELECT id FROM worlds WHERE id=:world FOR SHARE'),{'world':world})
    if connection.execute(text('SELECT 1 FROM world_deletion_requests WHERE world_id=:world'),{'world':world}).first():
        raise ValueError('world_deleting')
