"""Bounded read-only checkpoint basis. Never starts a saver or resumes a graph."""
from contextlib import closing
from pathlib import Path
import sqlite3
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from app.domains.memory.contracts.activity_situation import stable_digest, SITUATION_BASIS_DOCUMENT_MAX_BYTES
from app.domains.memory.contracts.situation_result_binding import SituationResultBasis
from app.domains.social.models.posts import Post
from app.domains.social.utils.situation_output import NORMALIZATION_REVISION, stored_output


class CheckpointResultBasis:
    def __init__(self, path):
        self.path = Path(path) if path is not None else None

    def raw_output(self, admission):
        receipt = admission.receipt
        if self.path is None or not self.path.is_file() or receipt.lane not in {"routine", "feed", "inbox"}:
            raise ValueError("situation_result_basis_missing")
        # Explicit allowlists and pickle rejection apply independently of any
        # process-wide LangGraph serialization environment setting.
        serde = JsonPlusSerializer(pickle_fallback=False, allowed_json_modules=[], allowed_msgpack_modules=[])
        matched, saw_candidate = {}, False
        try:
            with closing(sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
                db.execute("PRAGMA query_only=ON")
                rows = db.execute("SELECT checkpoint_ns,type,checkpoint FROM checkpoints WHERE thread_id=? "
                    "AND checkpoint_ns LIKE ? ORDER BY checkpoint_id DESC LIMIT 256",
                    ("activity:" + receipt.logical_activity_id, "%" + receipt.lane.capitalize() + "ActivityGraph:%"))
                for namespace, kind, data in rows:
                    if kind not in {"msgpack", "json"} or len(data) > SITUATION_BASIS_DOCUMENT_MAX_BYTES:
                        continue
                    value = serde.loads_typed((kind, data))
                    state = value.get("channel_values", {}) if isinstance(value, dict) else {}
                    if state.get("identity", {}).get("activity_id") != receipt.logical_activity_id:
                        continue
                    decision = state.get("decision", {})
                    override = decision.get("_situation_overrides", {}).get(receipt.target_key)
                    manifest = override.get("manifest") if override else decision.get("_situation_manifest")
                    if not isinstance(manifest, dict) or stable_digest(manifest) != admission.manifest_digest:
                        continue
                    raw = override.get("normalized") if override else decision.get("_situation_normalized_draft")
                    # Only the selected final Writer output or the final combined
                    # Write channel is eligible. Provisional drafts are not used.
                    if not isinstance(raw, dict) or (not override and any(
                        row.get("writer_recovery") for row in state.get("writer_input_receipts", []))):
                        continue
                    saw_candidate = True
                    if receipt.lane == "routine":
                        effects = admission.result.get("effects", [])
                        if len(effects) != 1 or effects[0].get("kind") != "post" or effects[0].get("source_type") != "POST":
                            continue
                        # Routine's execution owner binds target_post_id to its
                        # own published post before situation admission.
                        output = {"action": "post", "target": effects[0]["source_id"], "body": raw.get("body"), "title": raw.get("title")}
                    else:
                        planned = next((row for row in decision.get("decisions", []) if row.get("target_id") == receipt.target_key), {})
                        target = state.get("lane_data", {}).get(receipt.target_key, {}).get("post_id")
                        written = next((row for row in raw.get("replies", []) if row.get("target_id") == receipt.target_key), {})
                        output = {"action": "reply" if planned.get("action") == "comment" else planned.get("action"),
                            "target": target, "body": written.get("body")}
                    if stable_digest(output) == admission.result["planned_output_digest"]:
                        matched[stable_digest(output)] = output
        except (sqlite3.Error, ValueError, TypeError, KeyError, OSError):
            raise ValueError("situation_result_basis_missing") from None
        if not matched:
            raise ValueError("situation_result_basis_invalid" if saw_candidate else "situation_result_basis_missing")
        return next(iter(matched.values()))

    def prepare(self, page):
        outputs = {}
        for sequence, admission, error in page.admissions:
            if admission is not None and admission.requires_result_binding:
                try:
                    outputs[sequence] = self.raw_output(admission)
                except ValueError as exc:
                    outputs[sequence] = str(exc)
        return PreparedCheckpointResultBasis(self, outputs)

    def resolve(self, session, admission, *, raw=None):
        raw = self.raw_output(admission) if raw is None else raw
        sources = [row for row in admission.result_sources if row.role == "committed_result" and row.source_type in {"POST", "REPLY"}]
        if len(sources) != 1:
            raise ValueError("situation_result_basis_invalid")
        source, scope = sources[0], admission.manifest.snapshot.scope
        post = session.get(Post, source.source_id, populate_existing=True)
        if (post is None or post.world_id != scope.world_id or post.author_world_character_id != scope.subject_world_character_id
            or post.deleted_at or post.report_hidden_at or post.visibility != "public"):
            raise ValueError("situation_result_source_changed")
        actual = {"action": "reply" if post.reply_to_post_id else "post", "target": post.reply_to_post_id or post.id, "body": post.body}
        if actual["action"] == "post":
            actual["title"] = post.title
        receipt = admission.receipt
        return SituationResultBasis(receipt.logical_activity_id, receipt.lane, receipt.target_key,
            raw, stored_output(raw), actual, NORMALIZATION_REVISION, source)


class PreparedCheckpointResultBasis:
    """One page's interpreted basis; canonical post/receipt checks remain fresh."""
    def __init__(self, owner, outputs):
        self.owner, self.outputs = owner, outputs

    def resolve(self, session, admission):
        raw = self.outputs.get(admission.receipt.sequence)
        if isinstance(raw, str):
            raise ValueError(raw)
        if raw is None:
            raise ValueError("situation_result_basis_missing")
        return self.owner.resolve(session, admission, raw=raw)
