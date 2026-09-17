"""Single-snapshot, bounded FTS5 word-group reads over the v1 projection."""
import re
import sqlite3
from time import monotonic
from app.contracts.retrieval_observation import observe, detail
from app.core.search_text import normalize_search_text
from app.domains.memory.contracts.fts_recall import FtsSearchBatch
from app.domains.memory.contracts.hybrid_recall import RecallAxisStatus as Status
from app.domains.memory.contracts.recall import RecallDocumentKind
from app.domains.memory.policies.grouped_fts import build_groups, match_groups
from app.domains.memory.policies.korean_recall import spacing_groups, spacing_matches

MAX_BYTES = 4 * 1024 * 1024
_FIELDS = 'document_id,memory_item_id,kind,canonical_source_id,text,counterpart_world_character_id,thread_id,source_type,source_event_id,occurred_at,metadata_json'


def render_match(groups):
    return ' OR '.join('(' + ' AND '.join('"' + t.replace('"', '""') + '"' for t in g.tokens) + ')' for g in groups)


def search_grouped(index, query, deadline, filters, parameters, to_candidate):
    started = monotonic()
    compiled = build_groups(query.text)
    match = render_match(compiled.groups)
    candidates = []
    stats = dict(groups=len(compiled.groups), tokens=len({t for g in compiled.groups for t in g.tokens}),
                 match_bytes=len(match.encode()), scanned=0, accepted=0, excluded=0,
                 bytes_scanned=0, truncated=compiled.truncated, spacing_attempted=False)
    executed = False
    reason = 'fts_input_truncated' if compiled.truncated else None

    def finish(status, code=None):
        rows = tuple(candidates) if status in (Status.READY, Status.PARTIAL) else ()
        observe('fts_search', policy='group_or_v1', status=status.value, reason=code or 'completed',
                executed=executed, returned=len(rows), elapsed_ms=(monotonic()-started)*1000, **stats)
        return FtsSearchBatch(rows, status, executed, code, stats)

    if monotonic() >= deadline:
        return finish(Status.UNAVAILABLE, 'fts_deadline_exceeded')
    if not compiled.groups or not query.kinds:
        return finish(Status.PARTIAL if reason else Status.READY, reason or 'fts_no_terms')
    detail(search_text=query.text, match_query=match, operation='group_or_v1')
    limit = min(200, query.limit * 4)
    where = ' AND '.join(filters)
    try:
        with index._connect(index.database_path, busy_timeout_ms=min(index.settings.busy_timeout_ms, max(1, int((deadline-monotonic())*1000)))) as connection:
            local_deadline = deadline
            connection.set_progress_handler(lambda: int(monotonic() >= local_deadline), 1000)
            connection.execute('BEGIN')
            try:
                executed = True
                ids = connection.execute(
                    f'SELECT d.document_id,bm25(memory_recall_fts) AS rank FROM memory_recall_fts '
                    f'JOIN memory_recall_documents d ON d.document_id=memory_recall_fts.document_id '
                    f'WHERE memory_recall_fts MATCH ? AND {where} '
                    'ORDER BY rank ASC,d.occurred_at DESC,d.document_id ASC LIMIT ?',
                    (match, *parameters, limit)).fetchall()
                stats['window_candidates'] = len(ids)

                def inspect(document_id, rank, *, spacing=()):
                    nonlocal reason
                    if monotonic() >= local_deadline:
                        raise TimeoutError
                    sizes = connection.execute(
                        f'SELECT length(CAST(d.normalized_text AS BLOB)),length(CAST(d.text AS BLOB)),length(CAST(d.metadata_json AS BLOB)) '
                        f'FROM memory_recall_documents d WHERE {where} AND d.document_id=?',
                        (*parameters, document_id)).fetchone()
                    if sizes is None:
                        raise sqlite3.DatabaseError('projection_identity_missing')
                    if stats['bytes_scanned'] + sizes[0] > MAX_BYTES:
                        reason = 'fts_materialization_budget'
                        return False
                    text = connection.execute(f'SELECT d.normalized_text FROM memory_recall_documents d WHERE {where} AND d.document_id=?', (*parameters, document_id)).fetchone()[0]
                    stats['bytes_scanned'] += sizes[0]
                    stats['scanned'] += 1
                    matched = match_groups(compiled.groups, text) if not spacing else ()
                    accepted = bool(matched) if not spacing else spacing_matches(spacing, text)
                    if stats['scanned'] <= 10:
                        detail(operation='fts_candidate', candidate_rank=str(stats['scanned']), matched_groups=','.join(map(str,matched)), match_state='accepted' if accepted else 'excluded')
                    if accepted:
                        if stats['bytes_scanned'] + sizes[1] + sizes[2] > MAX_BYTES:
                            reason = 'fts_materialization_budget'
                            return False
                        row = connection.execute(f'SELECT {_FIELDS},? AS rank FROM memory_recall_documents d WHERE {where} AND d.document_id=?', (rank, *parameters, document_id)).fetchone()
                        stats['bytes_scanned'] += sizes[1] + sizes[2]
                        candidates.append(to_candidate(row))
                        stats['accepted'] += 1
                    else:
                        stats['excluded'] += 1
                    if monotonic() >= local_deadline:
                        raise TimeoutError
                    return True

                for row in ids:
                    if not inspect(row['document_id'], row['rank']) or len(candidates) >= query.limit:
                        break
                if len(ids) == limit and len(candidates) < query.limit and not reason:
                    reason = 'fts_candidate_window_exhausted'
                groups = spacing_groups(normalize_search_text(query.text, max_chars=1000))
                if not candidates and not reason and query.korean_spacing_fallback and RecallDocumentKind.MEMORY_ITEM in query.kinds and groups:
                    stats['spacing_attempted'] = True
                    local_deadline = min(deadline, monotonic() + .050)
                    anchor = max((g for g in groups if re.fullmatch(r'[가-힣]+', g)), key=len)
                    anchors = tuple(dict.fromkeys(anchor))[:4]
                    conditions = ' AND '.join('instr(d.normalized_text,?)>0' for _ in anchors)
                    cursor = connection.execute(
                        f'SELECT d.document_id FROM memory_recall_documents d WHERE {where} AND d.kind=? AND {conditions} '
                        'ORDER BY d.occurred_at DESC,d.document_id ASC LIMIT 2001',
                        (*parameters, RecallDocumentKind.MEMORY_ITEM.value, *anchors))
                    try:
                        for n, row in enumerate(cursor):
                            if n >= 2000:
                                reason = 'fts_spacing_budget'
                                break
                            if not inspect(row['document_id'], 0.0, spacing=groups) or len(candidates) >= query.limit:
                                break
                    finally:
                        cursor.close()
                if monotonic() >= deadline:
                    return finish(Status.UNAVAILABLE, 'fts_deadline_exceeded')
            except (TimeoutError, sqlite3.OperationalError):
                if monotonic() >= deadline:
                    return finish(Status.UNAVAILABLE, 'fts_deadline_exceeded')
                if stats['spacing_attempted'] and monotonic() >= local_deadline:
                    reason = 'fts_spacing_budget'
                else:
                    return finish(Status.UNAVAILABLE, 'fts_sql_error')
            finally:
                connection.set_progress_handler(None, 0)
                connection.rollback()
    except sqlite3.DatabaseError:
        return finish(Status.UNAVAILABLE, 'fts_deadline_exceeded' if monotonic() >= deadline else 'fts_sql_error')
    return finish(Status.PARTIAL if reason else Status.READY, reason or (None if candidates else 'fts_no_match'))
