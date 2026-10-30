"""Atomic PostgreSQL vector generation pointers and migration-budget receipt."""
from sqlalchemy import text
from app.runtime.memory.postgresql_vector import PostgresMemoryVectorIndex
from app.runtime.memory.sqlite_vec1 import MemoryVectorProjectionError


def initialize_state(engine,*,budget_state):
    if budget_state not in {'fresh','migrated-v41'}:raise ValueError('postgresql_budget_receipt_invalid')
    with engine.begin() as c:
        c.exec_driver_sql('''CREATE TABLE IF NOT EXISTS pg_vector_state(singleton boolean PRIMARY KEY CHECK(singleton),
            active text NOT NULL,staging text,previous text,source_budget_state text NOT NULL);''')
        c.execute(text("INSERT INTO pg_vector_state VALUES(true,'v1',NULL,NULL,:state) ON CONFLICT DO NOTHING"),{'state':budget_state})


class PostgresVectorGenerations:
    def __init__(self,engine):self.engine=engine;self.state={}
    def _index(self,generation):return PostgresMemoryVectorIndex(self.engine,generation=generation)
    def open(self):
        with self.engine.connect() as c:
            row=c.execute(text('SELECT active,staging,previous,source_budget_state FROM pg_vector_state WHERE singleton=true')).one()
        if row.source_budget_state not in {'fresh','migrated-v41'}:raise MemoryVectorProjectionError('memory_vector_legacy_budget_missing')
        self.state={'version':1,'active':row.active,'staging':row.staging,'previous':row.previous}
        active=self._index(row.active);active.open()
        staging=self._index(row.staging) if row.staging else None
        if staging:staging.open()
        return active,staging
    def retained(self):
        with self.engine.connect() as c:
            generations=tuple(c.execute(text('SELECT generation FROM pg_memory_vector_generations')).scalars())
        return tuple(self._index(g) for g in generations)
    def promote(self,index):
        with self.engine.begin() as c:
            row=c.execute(text('SELECT active,staging FROM pg_vector_state WHERE singleton=true FOR UPDATE')).one()
            if row.staging!=index.generation:raise MemoryVectorProjectionError('memory_vector_generation_changed')
            c.execute(text('UPDATE pg_vector_state SET previous=active,active=staging,staging=NULL WHERE singleton=true'))
        self.state={'version':1,'active':index.generation,'staging':None,'previous':row.active}
