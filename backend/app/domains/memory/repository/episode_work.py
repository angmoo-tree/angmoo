"""Durable per-bundle attempt receipts on the existing maintenance job lane.

The bundle table retains source identities and progress, never copies raw text.
The original batch-v2 physical_calls constraint remains unchanged; episode
calls are counted in these bundle receipts rather than misusing its three-call
counter for an entire day. Runtime/API must aggregate this lane explicitly.
"""

from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
import json
import re

from sqlalchemy import select

from app.domains.memory.contracts.episode import EPISODE_VERSION
from app.domains.memory.exceptions import MemoryConflictError, MemoryValidationError
from app.domains.memory.models.episode import MemoryEpisodeBundle
from app.domains.memory.policies.episode_bundles import bundle_manifest_hash
from app.domains.memory.service.episode_manifest import episode_input_manifest
from app.domains.memory.contracts.activity_batch import ACTIVITY_POLICY_VERSION, ACTIVITY_WORK_VERSION, MemoryActivity

WORK_VERSION = "episode-work.v1"
MAX_JOB_BUNDLES = 256
MAX_BUNDLE_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class EpisodeWork:
    id: str
    manifest: dict
    state: str
    calls: int
    depth: int
    candidate_ids: tuple[str, ...]


class SqlAlchemyEpisodeWork:
    def __init__(self, session):
        self.session = session

    def usage(self, *, job_id, setting):
        """Content-free totals; unknown interrupted attempts stay unknown."""
        work = self.list(job_id=job_id, setting=setting)
        calls = []
        for item in work:
            row = self.session.get(MemoryEpisodeBundle, item.id)
            calls.extend(self._read(row)["calls"])
        return {
            "bundle_count": len(work), "logical_attempts": len(calls),
            "known_physical_calls": sum(c.get("physical_calls") or 0 for c in calls),
            "unknown_physical_attempts": sum(c.get("physical_calls") is None for c in calls),
            **{field: sum(c.get(field) or 0 for c in calls)
               for field in ("input_tokens", "output_tokens", "thought_tokens", "latency_ms")},
        }

    def plan(self, *, job_id, setting, bundles, candidate_ids, now, job_fence):
        """Persist the complete input plan once, under the caller's job fence."""
        if not re.fullmatch(r"[A-Za-z0-9-]{1,48}", job_id) or not 1 <= len(bundles) <= MAX_JOB_BUNDLES:
            raise MemoryValidationError("episode_work_plan_invalid")
        job_fence()
        old = self.list(job_id=job_id, setting=setting)
        if old:
            return old
        for ordinal, bundle in enumerate(bundles):
            if bundle.scope != setting.scope or not bundle.activation_epoch:
                raise MemoryValidationError("episode_work_scope_invalid")
            modern = bundle.policy_version == ACTIVITY_POLICY_VERSION
            manifest = {"version": ACTIVITY_WORK_VERSION if modern else WORK_VERSION, "job_id": job_id,
                **({"lineage_root": f"{job_id}:{ordinal:03d}"} if modern else {}),
                "input": episode_input_manifest(bundle), "state": "pending", "calls": [],
                "depth": 0, "candidate_ids": list(candidate_ids), "last_code": None}
            self.session.add(MemoryEpisodeBundle(id=f"{job_id}:{ordinal:03d}", scope_setting_id=setting.id,
                policy_version=bundle.policy_version, activation_epoch=bundle.activation_epoch,
                cutoff_sequence=bundle.cutoff_sequence, manifest_hash=bundle_manifest_hash(bundle),
                manifest_json=json.dumps(manifest, ensure_ascii=False, sort_keys=True), result_hash="", created_at=now))
        self.session.flush()
        return self.list(job_id=job_id, setting=setting)

    def list(self, *, job_id, setting):
        if not re.fullmatch(r"[A-Za-z0-9-]{1,48}", job_id):
            raise MemoryValidationError("episode_work_job_invalid")
        rows = self.session.scalars(select(MemoryEpisodeBundle).where(
            MemoryEpisodeBundle.scope_setting_id == setting.id,
            MemoryEpisodeBundle.id.startswith(job_id + ":"),
            MemoryEpisodeBundle.policy_version.in_((EPISODE_VERSION, ACTIVITY_POLICY_VERSION)),
        ).order_by(MemoryEpisodeBundle.id).limit(MAX_JOB_BUNDLES + 1)).all()
        if len(rows) > MAX_JOB_BUNDLES:
            raise MemoryValidationError("episode_work_limit")
        result = []
        for row in rows:
            value = self._read(row)
            if value["job_id"] != job_id:
                raise MemoryConflictError("episode_work_job_changed")
            result.append(EpisodeWork(row.id, value["input"], value["state"], len(value["calls"]),
                                      value["depth"], tuple(value["candidate_ids"])))
        return tuple(result)

    def start_call(self, work, *, model_id, thinking_level, profile_version, now, job_fence):
        job_fence()
        row = self.session.get(MemoryEpisodeBundle, work.id, populate_existing=True)
        value = self._read(row)
        allowance = MAX_BUNDLE_ATTEMPTS * (1 + len(value.get("retry_grants", ())))
        calls = len(value["calls"])
        if value["version"] == ACTIVITY_WORK_VERSION:
            calls = self._lineage_calls(value, setting_id=row.scope_setting_id)
        if value["state"] not in {"pending", "running"} or calls >= allowance:
            raise MemoryConflictError("episode_work_attempts_exhausted")
        value["calls"].append({"model_id": model_id, "thinking_level": thinking_level,
            "profile_version": profile_version, "started_at": now.isoformat(), "outcome": "in_flight"})
        value["state"] = "running"
        row.manifest_json = json.dumps(value, ensure_ascii=False, sort_keys=True)
        self.session.flush()
        # The caller commits this counter BEFORE awaiting a physical provider.
        return len(value["calls"])

    def finish_call(self, work, *, call_number, code, elapsed_ms, usage=None, job_fence, physical_calls=None):
        job_fence()
        if not re.fullmatch(r"[a-z0-9_]{1,80}", code):
            raise MemoryValidationError("episode_work_code_invalid")
        row = self.session.get(MemoryEpisodeBundle, work.id, populate_existing=True)
        value = self._read(row)
        if call_number != len(value["calls"]) or value["calls"][-1]["outcome"] != "in_flight":
            raise MemoryConflictError("episode_work_call_changed")
        result = value["calls"][-1]
        result["outcome"], result["latency_ms"] = code, max(0, int(elapsed_ms))
        result["physical_calls"] = physical_calls if isinstance(physical_calls, int) and not isinstance(physical_calls, bool) and 0 <= physical_calls <= 1 else None
        for field in ("input_tokens", "output_tokens", "thought_tokens"):
            count = getattr(usage, field, None)
            if type(count) is int and count >= 0:
                result[field] = count
        value["last_code"] = code
        if code != "episode_selection_completed":
            allowance = MAX_BUNDLE_ATTEMPTS * (1 + len(value.get("retry_grants", ())))
            value["state"] = "pending" if len(value["calls"]) < allowance else "failed"
        row.manifest_json = json.dumps(value, ensure_ascii=False, sort_keys=True)
        self.session.flush()

    def grant_explicit_retry(self, *, job_id, setting, request_key, now, previous_job_attempts):
        """User retry retains completed inputs and every earlier call receipt."""
        work = self.list(job_id=job_id, setting=setting)
        for snapshot in work:
            if snapshot.state in {"completed", "split"}:
                continue
            row = self.session.get(MemoryEpisodeBundle, snapshot.id)
            value = self._read(row)
            grants = value.setdefault("retry_grants", [])
            if any(grant["request_key"] == request_key for grant in grants):
                continue
            grants.append({"request_key": request_key, "at": now.isoformat(), "previous_job_attempts": previous_job_attempts})
            value["state"] = "pending"
            row.manifest_json = json.dumps(value, ensure_ascii=False, sort_keys=True)
        self.session.flush()

    def split(self, work, *, bundle, setting, now, job_fence):
        """A bounded binary split is durable and never reprocesses its parent."""
        job_fence()
        row = self.session.get(MemoryEpisodeBundle, work.id, populate_existing=True)
        value = self._read(row)
        if value["state"] != "running" or value["depth"] >= 3 or len(bundle.new_units) < 2:
            raise MemoryConflictError("episode_work_split_exhausted")
        existing = self.list(job_id=value["job_id"], setting=setting)
        if len(existing) + 2 > MAX_JOB_BUNDLES:
            raise MemoryConflictError("episode_work_limit")
        middle = len(bundle.new_units) // 2
        modern = bundle.policy_version == ACTIVITY_POLICY_VERSION
        if modern and len(bundle.activities) > 1:
            middle = sum(len(a.unit_keys) for a in bundle.activities[:len(bundle.activities) // 2])
        left, right = bundle.new_units[:middle], bundle.new_units[middle:]
        context = (*bundle.context_units, *left)[-5:] if left[0].kind == "chat_turn" else ()
        def child(values, suffix, preceding):
            if not modern:
                return replace(bundle, bundle_ref=bundle.bundle_ref + suffix, new_units=values, context_units=preceding)
            keys = {u.unit_key for u in values}
            known = {u.unit_key: u for u in (*bundle.context_units, *bundle.new_units)}
            activities = tuple(replace(a, unit_keys=tuple(k for k in a.unit_keys if k in keys))
                for a in bundle.activities if set(a.unit_keys) & keys)
            references = {k for a in activities for k in a.context_keys} - keys
            return replace(bundle, bundle_ref=bundle.bundle_ref + suffix, new_units=values,
                context_units=tuple(known[k] for k in sorted(references)), activities=activities)
        children = (child(left, ".1", bundle.context_units), child(right, ".2", context))
        for index, child in enumerate(children, 1):
            child_value = {"version": value["version"], "job_id": value["job_id"], "input": episode_input_manifest(child),
                **({"lineage_root": value["lineage_root"]} if modern else {}),
                "state": "pending", "calls": [], "depth": value["depth"] + 1,
                "candidate_ids": value["candidate_ids"], "last_code": None}
            self.session.add(MemoryEpisodeBundle(id=f"{work.id}.{index}", scope_setting_id=setting.id,
                policy_version=child.policy_version, activation_epoch=child.activation_epoch,
                cutoff_sequence=child.cutoff_sequence, manifest_hash=bundle_manifest_hash(child),
                manifest_json=json.dumps(child_value, ensure_ascii=False, sort_keys=True), result_hash="", created_at=now))
        value["state"], value["last_code"] = "split", "episode_needs_split"
        row.manifest_json = json.dumps(value, ensure_ascii=False, sort_keys=True)
        self.session.flush()

    @staticmethod
    def _read(row):
        if row is None:
            raise MemoryConflictError("episode_work_missing")
        try:
            value = json.loads(row.manifest_json)
            if (value["version"] not in {WORK_VERSION, ACTIVITY_WORK_VERSION} or value["state"] not in {"pending", "running", "completed", "split", "failed"}
                or not isinstance(value["calls"], list)
                or len(value["calls"]) > MAX_BUNDLE_ATTEMPTS * (1 + len(value.get("retry_grants", ())))
                or value["input"]["manifest_hash"] != row.manifest_hash):
                raise ValueError()
            return value
        except (ValueError, KeyError, TypeError):
            raise MemoryValidationError("episode_work_receipt_invalid") from None

    def access_manifest(self, work, *, setting):
        """Every split leaf retains the admitted root's access intersection."""
        row = self.session.get(MemoryEpisodeBundle, work.id)
        value = self._read(row)
        if value["version"] != ACTIVITY_WORK_VERSION:
            return value["input"]
        root = self.session.get(MemoryEpisodeBundle, value["lineage_root"])
        if root is None or root.scope_setting_id != setting.id or root.policy_version != ACTIVITY_POLICY_VERSION:
            raise MemoryConflictError("episode_access_root_unavailable")
        parent = self._read(root)
        if parent["job_id"] != value["job_id"] or parent.get("lineage_root") != root.id:
            raise MemoryConflictError("episode_access_root_unavailable")
        return parent["input"]

    def _lineage_calls(self, value, *, setting_id):
        root = value.get("lineage_root")
        if not isinstance(root, str) or not root.startswith(value["job_id"] + ":"):
            raise MemoryValidationError("episode_work_lineage_invalid")
        rows = self.session.scalars(select(MemoryEpisodeBundle).where(
            MemoryEpisodeBundle.scope_setting_id == setting_id,
            MemoryEpisodeBundle.policy_version == ACTIVITY_POLICY_VERSION,
            (MemoryEpisodeBundle.id == root) | MemoryEpisodeBundle.id.startswith(root + ".")))
        calls = 0
        for row in rows:
            child = self._read(row)
            if child.get("lineage_root") != root:
                raise MemoryValidationError("episode_work_lineage_invalid")
            calls += len(child["calls"])
        return calls
