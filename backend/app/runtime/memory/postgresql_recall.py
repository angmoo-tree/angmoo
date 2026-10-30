"""Scoped Memory full-text projection with bounded Korean/grouped recall."""
from dataclasses import fields
import json
from datetime import UTC,datetime
from pathlib import Path
from time import monotonic
import re
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.core.postgresql_deadline import read_deadline
from app.core.postgresql_reads import retry_read, begin_owned_read
from app.core.postgresql_concurrency import retryable
from app.core.search_text import normalize_search_text
from app.domains.memory.contracts.recall import (MemoryRecallDoctor,MemoryRecallLexicalPolicy,
    RecallDocumentKind,MemoryRecallPreparing,MemoryRecallSearchIncomplete)
from app.domains.memory.contracts.fts_recall import FtsSearchBatch
from app.domains.memory.contracts.hybrid_recall import RecallAxisStatus as Status
from app.domains.memory.policies.grouped_fts import build_groups,build_image_groups,strict_literal_groups,match_groups
from app.domains.memory.policies.korean_recall import spacing_groups,spacing_matches
from app.domains.memory.policies.lexical_terms import _lexical_terms
from app.runtime.search.postgresql_store import PostgresSearchStore,bound_filters
from app.runtime.memory.sqlite_fts5_recall import (_PreparedRecallDocument,_prepare_unique_documents,
    _scope_filters,_row_to_candidate,_utc_text,MemoryRecallIndexSettings)

MAX_BYTES=4*1024*1024


class PostgresMemoryRecallIndex(PostgresSearchStore):
    table='pg_recall_documents'
    fields=tuple(f.name for f in fields(_PreparedRecallDocument))

    def __init__(self,engine,*,settings=None,progress_path=None,generation=None):
        self.settings=settings or MemoryRecallIndexSettings()
        self.progress_path=Path(progress_path) if progress_path is not None else None
        super().__init__(engine,'recall:'+self.settings.generation,generation=generation)

    def open(self):self._open();return self.doctor()

    def load_progress(self):
        with self.engine.connect() as c:
            value=c.execute(text('SELECT progress FROM pg_search_progress WHERE namespace=:n'),{'n':self.namespace}).scalar_one_or_none()
        return value

    def save_progress(self,value):
        with self.engine.begin() as c:
            if value is None:
                c.execute(text('DELETE FROM pg_search_progress WHERE namespace=:n'),{'n':self.namespace})
            else:
                c.execute(text('INSERT INTO pg_search_progress VALUES(:n,CAST(:p AS jsonb)) ON CONFLICT(namespace) DO UPDATE SET progress=excluded.progress'),{'n':self.namespace,'p':json.dumps(value)})

    def doctor(self):
        d=self._diagnose()
        return MemoryRecallDoctor(database_path='postgresql:'+self.table,generation=self.settings.generation,schema_version=1,
            fts5_available=False,integrity_check='projection_verified' if d['healthy'] else 'projection_mismatch',
            document_count=d['count'],searchable_document_count=d['searchable'],indexed_document_count=d['searchable'],
            tombstone_count=d['count']-d['searchable'],digest=d['digest'],digest_matches=d['digest_matches'],
            rollback_available=bool(d['rollback']),healthy=d['healthy'],tokenizer_strategy=self.strategy,
            provider='postgresql',full_text_available=d['fts_available'])

    def rebuild_writer(self):
        writer=type(self)(self.engine,settings=self.settings,generation=self._new_staging())
        writer._opened=True
        return writer

    def promote_rebuild(self,writer):self._promote(writer)

    def rebuild(self,documents):
        prepared=_prepare_unique_documents(documents);writer=self.rebuild_writer()
        with self.engine.begin() as c:
            c.execute(text(f'DELETE FROM {self.table} WHERE namespace=:namespace AND generation=:generation'),writer._scope(c))
            for d in prepared.values():writer._write(c,d)
            writer._refresh(c)
        self._promote(writer)
        return self.doctor()

    def memory_item_id_page(self,*,after='',limit=100):
        self._require_open()
        if not 1<=limit<=1000:raise ValueError('memory_recall_page_limit')
        with self.engine.connect() as c:
            return tuple(c.execute(text(f'SELECT DISTINCT memory_item_id FROM {self.table} WHERE namespace=:namespace AND generation=:generation AND memory_item_id>:after ORDER BY memory_item_id LIMIT :limit'),{**self._scope(c),'after':after,'limit':limit}).scalars())

    def replace_memory_item(self,*,memory_item_id,documents,tombstoned_at=None):
        self.replace_memory_items({memory_item_id:tuple(documents)},tombstoned_at=tombstoned_at)

    def replace_memory_items(self,replacements,*,tombstoned_at=None):
        self._require_open();prepared={};seen=set()
        for item,documents in replacements.items():
            values=_prepare_unique_documents(documents)
            if not item or any(v.memory_item_id!=item for v in values.values()) or seen.intersection(values):
                raise ValueError('memory_recall_replacement_item_mismatch')
            prepared[item]=values;seen.update(values)
        with self.engine.begin() as c:
            scope=self._scope(c)
            for item,documents in sorted(prepared.items()):
                c.execute(text(f'UPDATE {self.table} SET searchable=0,tombstoned_at=:at WHERE namespace=:namespace AND generation=:generation AND memory_item_id=:item AND searchable=1'),{**scope,'item':item,'at':_utc_text(tombstoned_at or datetime.now(UTC))})
                for d in documents.values():self._write(c,d)
            self._refresh(c)

    def tombstone_memory_item(self,*,memory_item_id,tombstoned_at=None):
        self.replace_memory_items({memory_item_id:()},tombstoned_at=tombstoned_at)

    def tombstone_scope(self,*,owner_id,world_id,subject_world_character_id,tombstoned_at=None):
        self._require_open()
        with self.engine.begin() as c:
            c.execute(text(f'UPDATE {self.table} SET searchable=0,tombstoned_at=:at WHERE namespace=:namespace AND generation=:generation AND owner_id=:owner AND world_id=:world AND subject_world_character_id=:subject'),
                {**self._scope(c),'owner':owner_id,'world':world_id,'subject':subject_world_character_id,'at':_utc_text(tombstoned_at or datetime.now(UTC))})
            self._refresh(c)

    def erase_memory_items(self,identifiers):
        self._require_open()
        with self.engine.begin() as c:
            for item in identifiers:
                c.execute(text(f'DELETE FROM {self.table} WHERE namespace=:n AND memory_item_id=:item'),{'n':self.namespace,'item':item})
            for g in c.execute(text('SELECT generation FROM pg_search_generations WHERE namespace=:n'),{'n':self.namespace}).scalars():
                digest,count=self._digest(c,g)
                c.execute(text('UPDATE pg_search_generations SET digest=:d,document_count=:c WHERE namespace=:n AND generation=:g'),{'d':digest,'c':count,'n':self.namespace,'g':g})

    erase_retained=erase_memory_items

    def _require_searchable(self):
        self._require_open()
        if self.load_progress() is not None or (self.progress_path is not None and self.progress_path.exists()):
            raise MemoryRecallPreparing('memory_recall_projection_preparing')

    def search_grouped(self,query,*,deadline,cancellation=None):
        if query.lexical_policy!=MemoryRecallLexicalPolicy.GROUP_OR_V1:
            raise ValueError('fts_grouped_query_invalid')
        return self._search(query,deadline,grouped=True,cancelled=None if cancellation is None else cancellation.signal)

    def search(self,query,*,deadline=None,cancellation=None):
        if query.lexical_policy!=MemoryRecallLexicalPolicy.LEGACY_STRICT_V1:
            raise ValueError('fts_policy_requires_bounded_result')
        batch=self._search(query,deadline or monotonic()+5,grouped=False,cancelled=None if cancellation is None else cancellation.signal)
        if batch.status not in {Status.READY,Status.PARTIAL} or batch.reason_code in {'fts_spacing_budget','fts_materialization_budget'}:
            raise MemoryRecallSearchIncomplete('memory_fts_incomplete')
        return batch.candidates

    def _search(self,query,deadline,*,grouped,cancelled=None):
        # Preserve the physical materialization budget across aborted snapshots;
        # only result candidates and validation state reset for the next read.
        stats=dict(scanned=0,accepted=0,excluded=0,bytes_scanned=0,spacing_attempted=False,read_attempts=0)
        state={'executed':False}
        def attempt():
            stats['read_attempts']+=1
            return self._search_attempt(query,deadline,grouped=grouped,cancelled=cancelled,stats=stats,state=state)
        try:
            return retry_read(attempt,deadline=deadline,cancelled=cancelled)
        except (DBAPIError,TimeoutError):
            code='fts_deadline_exceeded' if monotonic()>=deadline or cancelled is not None and cancelled.is_set() else 'fts_postgresql_error'
            return FtsSearchBatch((),Status.UNAVAILABLE,state['executed'],code,dict(stats))

    def _search_attempt(self,query,deadline,*,grouped,cancelled,stats,state):
        self._require_searchable()
        if not 1<=query.limit<=50:raise ValueError('fts_limit_invalid')
        result=[];executed=False;reason=None
        def finish(status,code=None):
            return FtsSearchBatch(tuple(result) if status in {Status.READY,Status.PARTIAL} else (),status,executed,code,dict(stats))
        if monotonic()>=deadline:return finish(Status.UNAVAILABLE,'fts_deadline_exceeded')
        normalized=normalize_search_text(query.image_base_text or query.text,max_chars=1000)
        if grouped:
            compiled=build_image_groups(query.image_base_text,query.image_hint) if query.image_hint and query.image_base_text else build_groups(query.text)
            groups=compiled.groups
            term_groups=[g.tokens for g in groups]
            if compiled.truncated:reason='fts_input_truncated'
            stats.update(groups=len(groups),tokens=len({t for g in groups for t in g.tokens}),truncated=compiled.truncated)
        else:
            groups=strict_literal_groups(normalized)
            term_groups=[_lexical_terms(normalized,query_mode=True)]
        if not query.kinds or not term_groups or not any(term_groups):return finish(Status.PARTIAL if reason else Status.READY,reason or 'fts_no_terms')
        where,values=bound_filters(*_scope_filters(query));limit=min(200,query.limit*4)
        tsqueries=[]
        for i,terms in enumerate(term_groups):
            values['q'+str(i)]=' '.join(terms);tsqueries.append(f"plainto_tsquery('simple',:q{i})")
        tsquery='('+' || '.join(tsqueries)+')'
        reason_holder=[reason]
        try:
            with self.engine.connect() as c,read_deadline(c,deadline,cancelled=cancelled):
                begin_owned_read(c)
                values.update(self._scope(c),limit=limit)
                where+=' AND d.namespace=:namespace AND d.generation=:generation'
                def ids(extra,rank='0.0',maximum=limit):
                    return c.execute(text(f'SELECT d.document_id,{rank} AS rank,octet_length(d.normalized_text) AS normalized_bytes,octet_length(d.text) AS text_bytes,octet_length(d.metadata_json) AS metadata_bytes FROM {self.table} d WHERE {where} AND {extra} ORDER BY rank,d.occurred_at DESC,d.document_id LIMIT :maximum'),{**values,'maximum':maximum}).mappings().all()
                def inspect(row,*,spacing=(),local_deadline=deadline):
                    if monotonic()>=local_deadline:raise TimeoutError
                    if stats['bytes_scanned']+row['normalized_bytes']>MAX_BYTES:
                        reason_holder[0]='fts_materialization_budget';return False
                    scoped={**values,'id':row['document_id']}
                    material=c.execute(text(f'SELECT normalized_text FROM {self.table} d WHERE {where} AND document_id=:id'),scoped).scalar_one()
                    stats['bytes_scanned']+=row['normalized_bytes'];stats['scanned']+=1
                    matched=match_groups(groups,material) if groups else ()
                    accepted=(spacing_matches(spacing,material) if spacing else bool(matched) if grouped else len(matched)==len(groups))
                    if accepted:
                        if stats['bytes_scanned']+row['text_bytes']+row['metadata_bytes']>MAX_BYTES:
                            reason_holder[0]='fts_materialization_budget';return False
                        item=c.execute(text(f'SELECT d.*,:rank AS rank FROM {self.table} d WHERE {where} AND document_id=:id'),{**scoped,'rank':row['rank']}).mappings().one()
                        stats['bytes_scanned']+=row['text_bytes']+row['metadata_bytes'];stats['accepted']+=1
                        result.append(_row_to_candidate(item))
                    else:stats['excluded']+=1
                    return True
                executed=True;state['executed']=True
                rows=ids(f'd.terms @@ {tsquery}',f'-ts_rank_cd(d.terms,{tsquery})')
                stats['window_candidates']=len(rows)
                for row in rows:
                    if not inspect(row) or len(result)>=query.limit:break
                if grouped and len(rows)==limit and len(result)<query.limit and not reason_holder[0]:reason_holder[0]='fts_candidate_window_exhausted'
                if not grouped and not result and not reason_holder[0]:
                    clauses=[]
                    for i,term in enumerate(term_groups[0]):
                        values['t'+str(i)]=term;clauses.append(f'strpos(d.normalized_text,:t{i})>0')
                    for row in ids(' AND '.join(clauses)):
                        if not inspect(row) or len(result)>=query.limit:break
                spacing=spacing_groups(normalize_search_text(query.text,max_chars=1000))
                if not result and not reason_holder[0] and query.korean_spacing_fallback and RecallDocumentKind.MEMORY_ITEM in query.kinds and spacing:
                    stats['spacing_attempted']=True;short=min(deadline,monotonic()+.05)
                    anchor=max((g for g in spacing if re.fullmatch(r'[가-힣]+',g)),key=len)
                    clauses=["d.kind='memory_item'"]
                    for i,char in enumerate(tuple(dict.fromkeys(anchor))[:4]):
                        values['anchor'+str(i)]=char;clauses.append(f'strpos(d.normalized_text,:anchor{i})>0')
                    try:
                        with read_deadline(c,short):
                            for n,row in enumerate(ids(' AND '.join(clauses),maximum=2001)):
                                if n>=2000:reason_holder[0]='fts_spacing_budget';break
                                if not inspect(row,spacing=spacing,local_deadline=short) or len(result)>=query.limit:break
                    except TimeoutError:reason_holder[0]='fts_spacing_budget'
                if monotonic()>=deadline:return finish(Status.UNAVAILABLE,'fts_deadline_exceeded')
        except DBAPIError as exc:
            if retryable(exc):raise
            return finish(Status.UNAVAILABLE,'fts_postgresql_error')
        except TimeoutError:
            return finish(Status.UNAVAILABLE,'fts_deadline_exceeded' if monotonic()>=deadline else 'fts_postgresql_error')
        reason=reason_holder[0]
        return finish(Status.PARTIAL if reason else Status.READY,reason or (None if result else 'fts_no_match'))
