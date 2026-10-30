"""Prefetch reachable identities only; canonical Python policies decide access."""
from sqlalchemy import text


_ANCESTRY = text("""
WITH RECURSIVE ancestry(id) AS (
    SELECT unnest(CAST(:seeds AS text[]))
    UNION
    SELECT neighbour.id
    FROM ancestry a
    JOIN memory_items i ON i.id = a.id
    LEFT JOIN memory_situation_info s ON s.memory_item_id = i.id
    LEFT JOIN memory_situation_receipts r ON r.sequence = s.receipt_sequence
    LEFT JOIN memory_situation_manifests m ON m.id = r.manifest_id
    LEFT JOIN memory_episode_restrictions x
        ON x.memory_item_id = i.id AND s.memory_item_id IS NULL
    CROSS JOIN LATERAL (
        SELECT source ->> 'source_id' AS id
        FROM jsonb_array_elements(CASE
            WHEN jsonb_typeof(CAST(m.payload AS jsonb) -> 'sources') = 'array'
            THEN CAST(m.payload AS jsonb) -> 'sources' ELSE '[]'::jsonb END) source
        WHERE source ->> 'source_type' = 'MEMORY_ITEM'
            AND jsonb_typeof(source -> 'source_id') = 'string'
        UNION ALL
        SELECT parent.id FROM memory_items parent
        WHERE s.memory_item_id IS NULL AND parent.superseded_by_id = i.id
        UNION ALL
        SELECT prior ->> 'id'
        FROM jsonb_array_elements(CASE
            WHEN pg_input_is_valid(x.priors_json, 'jsonb')
            THEN CASE WHEN jsonb_typeof(CAST(x.priors_json AS jsonb)) = 'array'
                THEN CAST(x.priors_json AS jsonb) ELSE '[]'::jsonb END
            ELSE '[]'::jsonb END) prior
        WHERE s.memory_item_id IS NULL AND jsonb_typeof(prior -> 'id') = 'string'
    ) neighbour
)
SELECT id FROM ancestry
""")


def reachable_ids(session, seeds):
    """Match prepare_access's graph, including missing IDs and cyclic edges.

    UNION visits each identity once. This only batches row discovery; malformed
    proofs, scope/version checks, missing rows and cycles still reach the same
    fail-closed validators. Do not use this set as an authorization result.
    The caller's transaction/deadline applies to the entire recursive query.
    """
    return set(session.scalars(_ANCESTRY, {'seeds': list(seeds)})) if seeds else set()
