"""Run-scoped token admission and whole-unit omission, never generation/split."""
from collections import OrderedDict
from dataclasses import replace
from hashlib import sha256
import json
from time import monotonic

from app.contracts.sns_generation import MODEL_BUDGET_REVISION, read_generation_policies
from app.domains.world_characters.activity_models import ActivityGraphRun
from app.integrations.gemini_input_budget import GeminiModelTokenCounter
from app.providers.gemini import prepare_generate_request
from app.providers.input_budget import InputBudgetError, ModelTokenProfile


class SnsInputBudget:
    def __init__(self, db, activity_id, *, counter=None, notify=None):
        self.db, self.activity_id = db, activity_id
        self.counter = counter or GeminiModelTokenCounter()
        self.notify = notify or (lambda *_: None)
        self.profile = None
        self.cache = OrderedDict()

    def row(self):
        row = self.db.get(ActivityGraphRun, self.activity_id, populate_existing=True)
        if row is None or row.status not in {"running", "waiting", "interrupted"} or read_generation_policies(row.result).model_budget_revision != MODEL_BUDGET_REVISION:
            raise InputBudgetError("activity_generation_policy_invalid")
        return row

    def record(self, operation, receipt):
        row = self.row()
        metadata = dict(row.result or {})
        attempts = dict(metadata.get("input_budget_attempts", {}))
        if operation in {"models_get", "count_tokens"}:
            attempts[operation] = attempts.get(operation, 0) + 1
            if sum(attempts.values()) > 256:
                raise InputBudgetError("activity_input_budget_unavailable")
        metadata["input_budget_attempts"] = attempts
        if receipt is not None:
            receipts = dict(metadata.get("input_budget_receipts", {}))
            receipts[receipt["request_sha256"]] = receipt
            metadata["input_budget_receipts"] = dict(list(receipts.items())[-32:])
        row.result = metadata
        self.db.commit()

    async def ensure_profile(self, request, guard):
        if self.profile is None:
            await guard()
            prior = (self.row().result or {}).get("model_token_profile")
            self.record("models_get", None)
            start = monotonic()
            try:
                actual = await self.counter.profile(request)
            except BaseException:
                self.notify("input_budget", {"operation": "models_get", "status": "failed",
                    "duration_ms": int((monotonic()-start)*1000), "model": request.model})
                raise
            self.notify("input_budget", {"operation": "models_get", "status": "ok",
                "duration_ms": int((monotonic()-start)*1000), "model": request.model})
            await guard()
            if actual.provider != "google" or actual.model != request.model or actual.revision != MODEL_BUDGET_REVISION:
                raise InputBudgetError("model_budget_unsupported")
            if prior is not None:
                frozen = ModelTokenProfile(**prior)
                if any(getattr(frozen, key) != getattr(actual, key) for key in ("provider", "model", "version", "input_limit", "output_limit", "revision", "context_limit")):
                    raise InputBudgetError("activity_model_profile_changed")
                actual = frozen
            else:
                row = self.row()
                row.result = {**(row.result or {}), "model_token_profile": actual.to_dict()}
                self.db.commit()
            self.profile = actual
        if self.profile.model != request.model:
            raise InputBudgetError("activity_model_profile_changed")
        frozen = (self.row().result or {}).get("model_token_profile")
        if frozen != self.profile.to_dict():
            raise InputBudgetError("activity_model_profile_changed")
        return self.profile

    async def admit(self, request, *, guard, omissions):
        profile = await self.ensure_profile(request, guard)
        profile.permits(0, request.max_output_tokens)
        prepared = prepare_generate_request(request)
        request = replace(request, prepared_request=prepared)
        body = prepared.count_request(request.model)
        digest = sha256(json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        key = (profile.provider, profile.model, profile.version, profile.revision, digest)
        await guard()
        cached = key in self.cache
        start = monotonic()
        if cached:
            tokens = self.cache[key]
        else:
            self.record("count_tokens", None)
            try:
                tokens, actual_digest = await self.counter.count(request, profile)
            except BaseException:
                self.notify("input_budget", {"operation": "count_tokens", "status": "failed", "cache_hit": False,
                    "request_sha256": digest, "duration_ms": int((monotonic()-start)*1000), "model": profile.model})
                raise
        try:
            if not cached and digest != actual_digest:
                raise InputBudgetError("activity_input_budget_unavailable")
            await guard()
            if (self.row().result or {}).get("model_token_profile") != profile.to_dict():
                raise InputBudgetError("activity_model_profile_changed")
            permitted = profile.permits(tokens, request.max_output_tokens)
        except BaseException:
            # The completed count is still a physical attempt even when the
            # subsequent lease/profile fence prevents any generation.
            self.notify("input_budget", {"operation": "count_tokens", "status": "admission_rejected",
                "cache_hit": cached, "request_sha256": digest, "model": profile.model,
                "duration_ms": int((monotonic()-start)*1000), "admitted": False})
            raise
        if not cached:
            self.cache[key] = tokens
            while len(self.cache) > 32:
                self.cache.popitem(last=False)
        receipt = {"policy_version": MODEL_BUDGET_REVISION, "request_sha256": digest,
            "model": profile.model, "model_version": profile.version, "input_tokens": tokens,
            "input_limit": profile.input_limit, "output_tokens": request.max_output_tokens,
            "coverage": "generateContentRequest", "cache_hit": cached,
            "duration_ms": int((monotonic()-start)*1000), "omissions": dict(omissions), "admitted": permitted}
        self.record("receipt", receipt)
        self.notify("input_budget", {"operation": "count_tokens", **receipt})
        return request, permitted


def omit_optional_unit(context, omissions):
    today = context.get("today_activity", [])
    records = today.get("records", []) if isinstance(today, dict) else today
    if isinstance(records, list) and records:
        # shared_input presents recent-first activity; remove the oldest record.
        records.pop()
        omissions["today_activity"] += 1
        context["input_omissions"] = dict(omissions)
        return True
    memories = context.get("memories", {})
    for item in reversed(list(memories.values())) if isinstance(memories, dict) else []:
        if isinstance(item, dict) and item.get("packets"):
            omissions["memory_packets"] += len(item["packets"])
            item.update(packets=[], status="partial", input_budget_omitted=True)
            context["input_omissions"] = dict(omissions)
            return True
    return False
