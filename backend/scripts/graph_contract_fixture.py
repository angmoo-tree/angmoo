"""Synthetic GC evaluation data, never imported by product code."""
from collections import deque
from datetime import datetime, UTC

from app.domains.chat.contracts.retrieval_policy import CanonicalRetrievalScope, RetrievalEntityCandidate, RetrievalEntityResolution
from app.domains.relationships.contracts.graph_query import GraphPathHit, GraphNeighborhoodHit
from app.domains.relationships.service.graph_recall import GraphRecallService
from test_p8_l_i_graph_recall import FakeGraphRecallGateway, FakeGraphRepository, _hit, OWNER_ID, WORLD_ID, SUBJECT_ID

IDS = {"리오": SUBJECT_ID, "소라": "wc-sora", "진": "wc-jin", "하나": "wc-hana", "테오": "wc-theo"}
ALIASES = {"rio": "리오", "sora": "소라", "jin": "진", "hana": "하나", "theo": "테오", **{n:n for n in IDS}}
NOW = datetime(2026, 9, 13, tzinfo=UTC)


class Policy:
    def __init__(self, language): self.language = language

    def load_scope(self, c):
        return CanonicalRetrievalScope(c.request_id, c.owner_id, c.world_id, c.thread_id,
            c.requester_world_character_id, c.responding_world_character_id, "Asia/Seoul",
            self.language, "리오 (Rio)", True)

    def resolve_entity_mentions(self, scope, mentions):
        def candidate(mention):
            matches = [name for key, name in ALIASES.items() if key == mention.strip().casefold()]
            return tuple(RetrievalEntityCandidate(IDS[n], n, IDS[n], True, False, True, True) for n in dict.fromkeys(matches))
        return tuple(RetrievalEntityResolution(ref, candidate(mention)) for ref, mention in mentions)


class Repository(FakeGraphRepository):
    def __init__(self, hits):
        super().__init__()
        self.hits = hits

    def neighbors(self, center, direction):
        result = []
        for h in self.hits:
            if direction in {"outgoing", "either"} and h.actor_world_character_id == center:
                result.append(h.target_world_character_id)
            if direction in {"incoming", "either"} and h.target_world_character_id == center:
                result.append(h.actor_world_character_id)
        return list(dict.fromkeys(result))

    def get_direct_relationship(self, **kw):
        a, b = kw["source_world_character_id"], kw["target_world_character_id"]
        return [h for h in self.hits if (h.actor_world_character_id, h.target_world_character_id) == (a, b)
                or (kw["include_reverse"] and (h.actor_world_character_id, h.target_world_character_id) == (b, a))]

    def list_shared_neighbors(self, **kw):
        return sorted(set(self.neighbors(kw["source_world_character_id"], kw["direction_mode"])) &
                      set(self.neighbors(kw["target_world_character_id"], kw["direction_mode"])))[:kw["limit"]]

    def rank_related_characters(self, **kw):
        return sorted((h for h in self.hits if h.actor_world_character_id == kw["source_world_character_id"]),
                      key=lambda h:(h.affinity+h.trust, h.familiarity, h.interaction_count, h.relationship_state_id), reverse=True)[:kw["limit"]]

    def find_shortest_path(self, **kw):
        source, target = kw["source_world_character_id"], kw["target_world_character_id"]
        queue = deque([([source], [])])
        while queue:
            nodes, edges = queue.popleft()
            if len(edges) >= kw["max_hops"]: continue
            for neighbor in self.neighbors(nodes[-1], kw["direction_mode"]):
                if neighbor in nodes: continue
                edge = next(h for h in self.hits if {h.actor_world_character_id, h.target_world_character_id} == {nodes[-1], neighbor}
                            and (kw["direction_mode"] == "either" or
                                 (h.actor_world_character_id == nodes[-1]) == (kw["direction_mode"] == "outgoing")))
                if neighbor == target:
                    return GraphPathHit(tuple(nodes+[neighbor]), tuple(edges+[edge]), len(edges)+1)
                queue.append((nodes+[neighbor], edges+[edge]))
        return None

    def get_visualization_neighborhood(self, **kw):
        return GraphNeighborhoodHit(kw["source_world_character_id"], tuple(IDS.values()), tuple(self.hits), False)


class Recall:
    def __init__(self, fixture):
        hits = [_hit(IDS[r["from"]], IDS[r["to"]], affinity=r["affinity"]) for r in fixture["relationships"]]
        gateway = FakeGraphRecallGateway(Repository(hits))
        for hit, row in zip(hits, fixture["relationships"], strict=True):
            gateway.canonical_by_state[hit.relationship_state_id] = hit
            gateway.observed_by_state[hit.relationship_state_id] = row["observed"]
            for person in (hit.actor_world_character_id, hit.target_world_character_id):
                gateway.canonical_by_center.setdefault(person, []).append(hit)
        self.service = GraphRecallService(gateway)
        self.executed = []

    def execute(self, query, **kwargs):
        result = self.service.execute(query, **kwargs)
        self.executed.append({"operation": query.operation.value, "direction":query.direction.value,
            "target":query.counterpart_world_character_id, "limit":query.limit, "source":result.source.value,
            "reason":result.reason_code, "candidate_count":result.candidate_count, "excluded_count":result.excluded_count,
            "people":list(result.world_character_ids), "facts":[{"from":h.actor_world_character_id,
                "to":h.target_world_character_id,"affinity":h.affinity} for h in result.relationships]})
        return result
