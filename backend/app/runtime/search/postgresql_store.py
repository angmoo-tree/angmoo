"""Transactional generations and GIN full-text storage for local PostgreSQL."""
from dataclasses import asdict
import hashlib,json,uuid
from sqlalchemy import text
from app.runtime.memory.postgresql_vector import fence_world


def bound_filters(filters,parameters):
    values={};index=0
    def bind(_):
        nonlocal index
        key='p'+str(index);values[key]=parameters[index];index+=1
        return ':'+key
    import re
    clause=re.sub(r'\?',bind,' AND '.join(filters))
    assert index==len(parameters)
    return clause,values


class PostgresSearchStore:
    provider='postgresql'
    strategy='PostgreSQL simple + CJK bigram + normalized substring; GIN'
    table=None
    fields=()

    def __init__(self,engine,namespace,*,generation=None):
        if self.table not in {'pg_social_documents','pg_recall_documents'}:
            raise ValueError('postgresql_projection_table_invalid')
        self.engine,self.namespace,self.pinned_generation=engine,namespace,generation
        self._opened=False

    def _open(self):
        with self.engine.begin() as c:
            common_ready=c.execute(text("SELECT to_regclass('pg_search_state') IS NOT NULL AND to_regclass('pg_search_progress') IS NOT NULL AND to_regclass('pg_search_generations') IS NOT NULL")).scalar_one()
            if not common_ready:c.exec_driver_sql('''CREATE TABLE IF NOT EXISTS pg_search_state(
                namespace text PRIMARY KEY,active text NOT NULL,rollback text,staging text,
                schema_version int NOT NULL CHECK(schema_version=1));
                CREATE TABLE IF NOT EXISTS pg_search_progress(namespace text PRIMARY KEY,progress jsonb NOT NULL);
                CREATE TABLE IF NOT EXISTS pg_search_generations(namespace text NOT NULL,generation text NOT NULL,
                digest text NOT NULL,document_count bigint NOT NULL,PRIMARY KEY(namespace,generation));''')
            definitions=','.join('"'+name+'" '+('integer NOT NULL CHECK(searchable IN(0,1))' if name=='searchable' else 'text') for name in self.fields)
            table_ready=c.execute(text('SELECT to_regclass(:table) IS NOT NULL AND to_regclass(:terms) IS NOT NULL AND to_regclass(:scope) IS NOT NULL'),{'table':self.table,'terms':self.table+'_terms','scope':self.table+'_scope'}).scalar_one()
            if not table_ready:c.exec_driver_sql(f'''CREATE TABLE IF NOT EXISTS {self.table}(namespace text NOT NULL,generation text NOT NULL,
                {definitions},terms tsvector GENERATED ALWAYS AS (to_tsvector('simple',coalesce(text,'')||' '||lexical_terms)) STORED,
                PRIMARY KEY(namespace,generation,document_id));
                CREATE INDEX IF NOT EXISTS {self.table}_terms ON {self.table} USING gin(terms) {'WHERE searchable=1' if 'searchable' in self.fields else ''};
                CREATE INDEX IF NOT EXISTS {self.table}_scope ON {self.table}(namespace,generation,world_id);''')
            proposed='gen-'+uuid.uuid4().hex
            c.execute(text('INSERT INTO pg_search_state(namespace,active,schema_version) VALUES(:n,:g,1) ON CONFLICT DO NOTHING'),{'n':self.namespace,'g':proposed})
            g=self._generation(c)
            c.execute(text('INSERT INTO pg_search_generations VALUES(:n,:g,:digest,0) ON CONFLICT DO NOTHING'),{'n':self.namespace,'g':g,'digest':hashlib.sha256(b'').hexdigest()})
        self._opened=True

    def _generation(self,c):
        return self.pinned_generation or c.execute(text('SELECT active FROM pg_search_state WHERE namespace=:n'),{'n':self.namespace}).scalar_one()

    def _scope(self,c):
        return {'namespace':self.namespace,'generation':self._generation(c)}

    def _write(self,c,prepared):
        value=asdict(prepared)
        if 'searchable' in value:value['searchable']=int(value['searchable'])
        value.update(self._scope(c))
        fence_world(c,value['world_id'])
        columns=('namespace','generation',*self.fields)
        updates=','.join('"'+name+'"=excluded."'+name+'"' for name in self.fields if name!='document_id')
        c.execute(text(f'INSERT INTO {self.table}('+','.join('"'+name+'"' for name in columns)+') VALUES('+','.join(':'+name for name in columns)+') ON CONFLICT(namespace,generation,document_id) DO UPDATE SET '+updates),value)

    def _digest(self,c,generation):
        value=hashlib.sha256();count=0
        for row in c.execute(text(f'SELECT '+','.join('"'+name+'"' for name in self.fields)+f' FROM {self.table} WHERE namespace=:n AND generation=:g ORDER BY document_id'),{'n':self.namespace,'g':generation}):
            value.update(json.dumps(list(row),ensure_ascii=False,separators=(',',':')).encode());value.update(b'\n');count+=1
        return value.hexdigest(),count

    def _refresh(self,c):
        g=self._generation(c);digest,count=self._digest(c,g)
        c.execute(text('INSERT INTO pg_search_generations VALUES(:n,:g,:d,:c) ON CONFLICT(namespace,generation) DO UPDATE SET digest=excluded.digest,document_count=excluded.document_count'),{'n':self.namespace,'g':g,'d':digest,'c':count})

    def _diagnose(self):
        self._require_open()
        with self.engine.connect() as c:
            g=self._generation(c);digest,count=self._digest(c,g)
            stored=c.execute(text('SELECT digest,document_count FROM pg_search_generations WHERE namespace=:n AND generation=:g'),{'n':self.namespace,'g':g}).one()
            index=c.execute(text('SELECT i.indisvalid FROM pg_index i JOIN pg_class t ON t.oid=i.indexrelid WHERE t.relname=:index'),{'index':self.table+'_terms'}).scalar_one()
            mismatch=c.execute(text(f"SELECT count(*) FROM {self.table} WHERE namespace=:n AND generation=:g AND terms IS DISTINCT FROM to_tsvector('simple',coalesce(text,'')||' '||lexical_terms)"),{'n':self.namespace,'g':g}).scalar_one()
            rollback=c.execute(text('SELECT rollback FROM pg_search_state WHERE namespace=:n'),{'n':self.namespace}).scalar_one()
            searchable=c.execute(text(f'SELECT count(*) FROM {self.table} WHERE namespace=:n AND generation=:g'+(' AND searchable=1' if 'searchable' in self.fields else '')),{'n':self.namespace,'g':g}).scalar_one()
        matches=stored.digest==digest and stored.document_count==count
        return dict(generation=g,digest=digest,count=count,searchable=searchable,digest_matches=matches,
            healthy=matches and bool(index) and mismatch==0,rollback=rollback,fts_available=bool(index))

    def _new_staging(self):
        self._require_open()
        with self.engine.begin() as c:
            row=c.execute(text('SELECT staging FROM pg_search_state WHERE namespace=:n FOR UPDATE'),{'n':self.namespace}).one()
            g=row.staging or 'gen-'+uuid.uuid4().hex
            c.execute(text('UPDATE pg_search_state SET staging=:g WHERE namespace=:n'),{'n':self.namespace,'g':g})
            c.execute(text('INSERT INTO pg_search_generations VALUES(:n,:g,:digest,0) ON CONFLICT DO NOTHING'),{'n':self.namespace,'g':g,'digest':hashlib.sha256(b'').hexdigest()})
            return g

    def _promote(self,writer):
        if writer.namespace!=self.namespace or writer.engine is not self.engine or not writer.pinned_generation:
            raise ValueError('postgresql_projection_writer_mismatch')
        with self.engine.begin() as c:
            row=c.execute(text('SELECT active,staging FROM pg_search_state WHERE namespace=:n FOR UPDATE'),{'n':self.namespace}).one()
            if row.staging!=writer.pinned_generation:raise ValueError('postgresql_projection_staging_changed')
            digest,count=writer._digest(c,writer.pinned_generation)
            stored=c.execute(text('SELECT digest,document_count FROM pg_search_generations WHERE namespace=:n AND generation=:g'),{'n':self.namespace,'g':writer.pinned_generation}).one()
            if tuple(stored)!=(digest,count):raise ValueError('postgresql_projection_digest_mismatch')
            c.execute(text('UPDATE pg_search_state SET rollback=active,active=staging,staging=NULL WHERE namespace=:n'),{'n':self.namespace})

    def rollback(self):
        self._require_open()
        with self.engine.begin() as c:
            row=c.execute(text('SELECT rollback FROM pg_search_state WHERE namespace=:n FOR UPDATE'),{'n':self.namespace}).one()
            if not row.rollback:raise ValueError('postgresql_projection_rollback_unavailable')
            c.execute(text('UPDATE pg_search_state SET active=rollback,rollback=active WHERE namespace=:n'),{'n':self.namespace})
        return self.doctor()

    def _require_open(self):
        if not self._opened:raise RuntimeError('postgresql_projection_not_open')

    def close(self):self._opened=False
