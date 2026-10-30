"""Social keyword discovery using PostgreSQL's GIN full-text index."""
from dataclasses import fields
from sqlalchemy import text
from app.core.search_text import normalize_search_text
from app.domains.runtime.contracts.search import SearchIndexDoctor,SearchIndexQuery
from app.runtime.search.postgresql_store import PostgresSearchStore,bound_filters
from app.runtime.search.sqlite_fts5 import (_PreparedDocument,_prepare_document,_scope_filters,
    _row_to_hit,_lexical_terms,_required_identifier,SqliteFts5Settings)


class PostgresFtsSearchIndex(PostgresSearchStore):
    table='pg_social_documents'
    fields=tuple(f.name for f in fields(_PreparedDocument))

    def __init__(self,engine,*,settings=None,generation=None):
        self.settings=settings or SqliteFts5Settings()
        super().__init__(engine,'sns:'+self.settings.generation,generation=generation)

    def open(self):self._open();return self.doctor()

    def doctor(self):
        d=self._diagnose()
        return SearchIndexDoctor(database_path='postgresql:'+self.table,generation=self.settings.generation,schema_version=1,
            fts5_available=False,integrity_check='projection_verified' if d['healthy'] else 'projection_mismatch',
            document_count=d['count'],indexed_document_count=d['count'],digest=d['digest'],digest_matches=d['digest_matches'],
            healthy=d['healthy'],tokenizer_strategy=self.strategy,provider='postgresql',full_text_available=d['fts_available'])

    def upsert(self,document):
        self._require_open();prepared=_prepare_document(document)
        if prepared is None:return self.remove(document_id=document.document_id)
        with self.engine.begin() as c:self._write(c,prepared);self._refresh(c)

    def remove(self,*,document_id):
        self._require_open()
        with self.engine.begin() as c:
            c.execute(text(f'DELETE FROM {self.table} WHERE namespace=:namespace AND generation=:generation AND document_id=:id'),{**self._scope(c),'id':document_id});self._refresh(c)

    def erase_world(self,world_id,*,limit=100):
        self._require_open()
        with self.engine.begin() as c:
            # Includes retained generations; privacy cleanup is not a tombstone.
            c.execute(text(f'DELETE FROM {self.table} WHERE (namespace,generation,document_id) IN (SELECT namespace,generation,document_id FROM {self.table} WHERE namespace=:n AND world_id=:w LIMIT :l)'),{'n':self.namespace,'w':world_id,'l':limit})
            for g in c.execute(text('SELECT generation FROM pg_search_generations WHERE namespace=:n'),{'n':self.namespace}).scalars():
                digest,count=self._digest(c,g)
                c.execute(text('UPDATE pg_search_generations SET digest=:d,document_count=:c WHERE namespace=:n AND generation=:g'),{'d':digest,'c':count,'n':self.namespace,'g':g})
            return c.execute(text(f'SELECT 1 FROM {self.table} WHERE namespace=:n AND world_id=:w LIMIT 1'),{'n':self.namespace,'w':world_id}).first() is None

    def rebuild(self,documents):
        self._require_open();seen=set();prepared=[]
        for d in documents:
            if d.document_id in seen:raise ValueError('duplicate_search_document')
            seen.add(d.document_id);value=_prepare_document(d)
            if value is not None:prepared.append(value)
        writer=type(self)(self.engine,settings=self.settings,generation=self._new_staging());writer._opened=True
        with self.engine.begin() as c:
            c.execute(text(f'DELETE FROM {self.table} WHERE namespace=:namespace AND generation=:generation'),writer._scope(c))
            for d in prepared:writer._write(c,d)
            writer._refresh(c)
        self._promote(writer)
        return self.doctor()

    def search(self,*,world_id,query,limit):return self.search_scoped(SearchIndexQuery(world_id=world_id,text=query,limit=limit))

    def search_scoped(self,query):
        self._require_open();world=_required_identifier(query.world_id,field_name='world_id')
        if not 1<=query.limit<=100:raise ValueError('search_limit_invalid')
        terms=_lexical_terms(normalize_search_text(query.text,max_chars=1000),query_mode=True)
        if not terms:return ()
        where,values=bound_filters(*_scope_filters(query,world_id=world))
        with self.engine.connect() as c:
            values.update(self._scope(c),q=' '.join(terms),limit=query.limit)
            where+=' AND d.namespace=:namespace AND d.generation=:generation'
            rows=c.execute(text(f"SELECT d.*,-ts_rank_cd(d.terms,plainto_tsquery('simple',:q)) AS rank FROM {self.table} d WHERE {where} AND d.terms @@ plainto_tsquery('simple',:q) ORDER BY rank,d.occurred_at DESC,d.document_id LIMIT :limit"),values).mappings().all()
            if not rows:
                clauses=[]
                for i,term in enumerate(terms):values['term'+str(i)]=term;clauses.append(f'strpos(d.normalized_text,:term{i})>0')
                rows=c.execute(text(f'SELECT d.*,0.0 AS rank FROM {self.table} d WHERE {where} AND '+ ' AND '.join(clauses)+' ORDER BY d.occurred_at DESC,d.document_id LIMIT :limit'),values).mappings().all()
        return tuple(_row_to_hit(row) for row in rows)
