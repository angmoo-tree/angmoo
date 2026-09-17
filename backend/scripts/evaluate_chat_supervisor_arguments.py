"""P5/P6 opt-in comparison. Reads credentials in the contributor runtime only.

No retrieval, CRG or product writes. Held-out evaluation requires a frozen
development candidate and the original M0 baseline. Every reservation and
failed response remains in the ledger/results. No hidden resume or budget increase.
"""
import argparse
import asyncio
from collections import Counter
from contextvars import ContextVar
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
from time import monotonic

from evaluate_chat_supervisor_selection import read_material, load_baseline, SyntheticPolicy
from app.integrations import direct_llm
from app.integrations.llm.supervisor_selection import (
    DirectLlmSupervisorSelectionProvider, control_selection_tools, control_selection_system_prompt,
)
from app.domains.chat.contracts.supervisor_selection import SelectionArgumentOptions
from app.domains.chat.contracts.retrieval_policy import RetrievalPreflightCommand
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterContextMessage
from app.domains.chat.service.retrieval_routing import RetrievalRoutingService


OPTIONS = {
    "N0": SelectionArgumentOptions(), "NA": SelectionArgumentOptions(True),
    "NB": SelectionArgumentOptions(False, True), "NAB": SelectionArgumentOptions(True, True),
}
FIXTURE_HASH = "f95f0bef3dbe863815138e46c46bf211036fff0bb780d244e07b55540affda7a"
# Evaluation-only annotations for named development questions. Not model input.
# These diagnostics do not replace the original route-selection acceptance gate.
ENTITY_EXPECTATIONS = {"case-03": "민지", "case-04": "민지", "case-08": "Mina"}
DIRECTION_CASES = frozenset({"case-03", "case-04"})


def digest(value):
    return hashlib.sha256(value).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def semantic_diagnostics(case_id, result):
    expected = ENTITY_EXPECTATIONS.get(case_id)
    if expected is None:
        return {"identity_applicable": False, "direction_applicable": False}
    bound = {b.ref for b in result.resolved.entity_bindings}
    refs = {e.ref for e in result.intent.entities if e.mention.strip().casefold() == expected.casefold()}
    relationship = result.intent.relationship
    return {
        "identity_applicable": True, "expected_mention_bound": bool(refs & bound),
        "direction_applicable": case_id in DIRECTION_CASES,
        "expected_direction": None if case_id not in DIRECTION_CASES else bool(
            relationship is not None and relationship.from_ref == "responding_character"
            and relationship.to_ref in refs),
        "notes": "synthetic_binding_not_real_database_identity",
    }


def summarize(rows):
    output = {}
    for name in dict.fromkeys(r["variant"] for r in rows):
        group = [r for r in rows if r["variant"] == name]
        attempts = [a for r in group for a in r["attempts"]]
        stages = {}
        for stage in ("wire", "entities", "relationship", "meaning", "coordination", "agreement"):
            counts = Counter()
            for attempt in attempts:
                trace = attempt.get("validation") or {}
                applicable = trace.get("applicable", {}).get(
                    stage, None if stage in {"entities", "relationship", "coordination"} else True)
                status = trace.get("stages", {}).get(stage, "not_evaluated")
                counts[f"all_{status}"] += 1
                if applicable is None:
                    counts["applicability_unknown"] += 1
                elif applicable:
                    counts["applicable"] += 1
                    counts[status] += 1
                    counts["reached"] += int(status != "not_evaluated")
                else:
                    counts["not_applicable"] += 1
            stages[stage] = dict(counts)
        output[name] = {
            "n": len(group), "first_pass_valid": sum(r.get("first_pass_valid", False) for r in group),
            "valid_after_repair": sum(r["status"] == "ok" for r in group),
            "correct": sum(r["correct"] for r in group),
            "repair_requests": sum(len(r["attempts"]) > 1 for r in group),
            "physical_calls": sum(u["physical"] for r in group for u in r["usage_attempts"]),
            "prompt_tokens": sum(u["prompt_tokens"] for r in group for u in r["usage_attempts"]),
            "output_tokens": sum(u["output_tokens"] for r in group for u in r["usage_attempts"]),
            "errors": dict(Counter(a["code"] for a in attempts if a["status"] == "failed")),
            "stages_all_attempts": stages,
            "per_case": {case: {"n":sum(r["case"] == case for r in group),
                "correct":sum(r["correct"] for r in group if r["case"] == case),
                "valid":sum(r["status"] == "ok" for r in group if r["case"] == case)}
                for case in dict.fromkeys(r["case"] for r in group)},
        }
    return output


def development_entry_gate(rows, name):
    group = [r for r in rows if r["variant"] == name]
    if (len(group) != 24 or sum(r.get("first_pass_valid", False) for r in group) < 23
            or any(r["status"] != "ok" for r in group)
            or sum(r["correct"] for r in group) < 23):
        return False
    for case in ("case-01", "case-03", "case-04"):
        subset = [r for r in group if r["case"] == case]
        if len(subset) != 3 or not all(r["correct"] for r in subset):
            return False
    # Existing F3 controls gate: do not execute retrieval for these controls.
    return not any(r["expected"] in {"CURRENT_CONTEXT", "CLARIFICATION"}
                   and r.get("effective") in {"CANONICAL", "GRAPH", "BOTH"} for r in group)


def current_source_hashes():
    source = Path(__file__).resolve().parents[1] / "app"
    return {p.relative_to(source).as_posix():digest(p.read_bytes())
            for p in source.rglob("*.py") if "__pycache__" not in p.parts}


def verify_heldout_freeze(args, names):
    if (len(names) != 2 or names[0] != "M0" or names[1] not in {"NA", "NAB"}
            or args.development is None or args.baseline is None or args.baseline_metadata is None):
        raise ValueError("evaluation_heldout_contract_invalid")
    meta = json.loads((args.development / "metadata.json").read_text(encoding="utf-8"))
    rows = [json.loads(s) for s in (args.development / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(rows) != 72 or not development_entry_gate(rows, names[1]):
        raise ValueError("evaluation_development_gate_failed")
    option = OPTIONS[names[1]]
    if (meta["input_hash"] != FIXTURE_HASH or meta["source_hashes"] != current_source_hashes()
            or meta["prompt_hashes"][names[1]] != digest(control_selection_system_prompt(option).encode())
            or meta["schema_hashes"][names[1]] != digest(json.dumps(
                [asdict(t) for t in control_selection_tools(option)],sort_keys=True).encode())):
        raise ValueError("evaluation_candidate_changed_after_development")
    original = json.loads(args.baseline_metadata.read_text(encoding="utf-8"))
    if original["m0_adapter_hash"] != digest(args.baseline.read_bytes()) or original["input_hash"] != FIXTURE_HASH:
        raise ValueError("evaluation_m0_baseline_changed")
    baseline = load_baseline(args.baseline, "evaluation_arguments_m0")
    if (original["prompt_hashes"]["M0"] != digest(baseline.selection_system_prompt().encode())
            or original["schema_hashes"]["M0"] != digest(json.dumps(
                [asdict(t) for t in baseline.selection_tools()],sort_keys=True).encode())):
        raise ValueError("evaluation_m0_contract_changed")
    return baseline


def validate_ledger(ledger, planned, maximum):
    # The caller supplies an already authorized cap. This never enlarges it.
    if (not 0 <= ledger["started"] <= ledger["maximum"] == maximum
            or ledger["started"] + planned > maximum):
        raise ValueError("evaluation_global_budget_invalid")


async def main(args):
    names = args.variants.split(",")
    allowed = set(OPTIONS) | ({"M0"} if args.split == "heldout" else set())
    if len(names) != len(set(names)) or not set(names) <= allowed:
        raise ValueError("evaluation_variants_invalid")
    # Verify the candidate before reading held-out questions or credentials.
    baseline = verify_heldout_freeze(args, names) if args.split == "heldout" else None
    if digest(args.inputs.read_bytes()) != FIXTURE_HASH:
        raise ValueError("evaluation_fixture_changed")
    all_cases = json.loads(args.inputs.read_text(encoding="utf-8"))
    cases = [c for c in all_cases if c["split"] == args.split]
    if len(all_cases) != 32 or len(cases) != (8 if args.split == "development" else 24):
        raise ValueError("evaluation_fixture_changed")
    planned = len(cases) * len(names) * args.repeats
    if (planned != args.max_calls
            or (args.split == "development" and (planned > 72 or args.repeats != 3))
            or (args.split == "heldout" and (planned != 96 or args.repeats != 2))):
        raise ValueError("evaluation_budget_invalid")
    if args.check_only:
        print(json.dumps({"preflight":"pass", "split":args.split, "planned":planned,
                          "credential_reads":0, "model_calls":0, "budget_modified":False}),flush=True)
        return 0
    material, saved = read_material()
    material = replace(material, model="gemini-3.1-flash-lite", thinking_level="high")
    providers = {name: DirectLlmSupervisorSelectionProvider(material, native_controls=True,
        code_coordination=OPTIONS[name].code_coordination,
        positional_entity_refs=OPTIONS[name].positional_entity_refs) for name in names if name != "M0"}
    prompts = {name:control_selection_system_prompt(OPTIONS[name]) for name in names if name != "M0"}
    schemas = {name:control_selection_tools(OPTIONS[name]) for name in names if name != "M0"}
    if baseline is not None:
        providers["M0"] = baseline.DirectLlmSupervisorSelectionProvider(material)
        prompts["M0"], schemas["M0"] = baseline.selection_system_prompt(), baseline.selection_tools()
    args.output.mkdir(exist_ok=False)
    lock = args.ledger.with_suffix(".lock")
    with lock.open("x") as file:
        file.write(str(os.getpid()))
    original_generate = direct_llm.generate_text
    try:
        ledger = json.loads(args.ledger.read_text())
        validate_ledger(ledger, planned, args.authorized_maximum)
        meta = {
            "started_at":datetime.now(UTC).isoformat(), "model":material.model, "thinking":material.thinking_level,
            "output_limit":3072, "provider_timeout_seconds":30, "request_deadline_seconds":95,
            "concurrency":2, "split":args.split, "repeats":args.repeats, "variants":names,
            "planned_initial_calls":planned, "ledger_started_before":ledger["started"],
            "authorized_maximum":args.authorized_maximum,
            "saved_model":saved["default_model"], "saved_thinking":saved["default_thinking_level"],
            "sdk_versions":{name:importlib.metadata.version(name) for name in ("google-genai","langgraph","langgraph-prebuilt")},
            "input_hash":FIXTURE_HASH,
            "prompt_hashes":{name:digest(prompts[name].encode()) for name in names},
            "schema_hashes":{name:digest(json.dumps([asdict(t) for t in schemas[name]],sort_keys=True).encode()) for name in names},
            "source_hashes":current_source_hashes(),
            "evaluator_hash":digest(Path(__file__).read_bytes()),
            "m0_adapter_hash":None if baseline is None else digest(args.baseline.read_bytes()),
            "development_results_hash":None if args.development is None else digest((args.development / "results.jsonl").read_bytes()),
            "annotations":{"identity":ENTITY_EXPECTATIONS,"direction":sorted(DIRECTION_CASES)},
            "notes":"No retrieval, CRG or product writes. Temperature/seed not set. Failures retained. Annotations not included in prompts.",
        }
        write_json(args.output / "metadata.json", meta)
        usage_context = ContextVar("argument_evaluation_usage", default=None)
        async def measured_generate(**kwargs):
            try:
                return await original_generate(**kwargs)
            finally:
                samples = usage_context.get()
                if samples is not None:
                    summary = kwargs["tracker"].summary()
                    samples.append({"physical":len(summary["calls"]), "prompt_tokens":summary["total_prompt_tokens"],
                        "output_tokens":summary["total_output_tokens"], "thought_tokens":summary["total_thought_tokens"],
                        "latency_ms":sum(int(c.get("duration_ms") or 0) for c in summary["calls"])})
        direct_llm.generate_text = measured_generate
        semaphore = asyncio.Semaphore(2)
        completed = []
        async def evaluate(case, name, repeat):
            async with semaphore:
                ledger = json.loads(args.ledger.read_text())
                if ledger["started"] >= ledger["maximum"]:
                    raise ValueError("evaluation_global_budget_exhausted")
                ledger["started"] += 1
                ledger["remaining"] = ledger["maximum"] - ledger["started"]
                write_json(args.ledger, ledger)
                row = {"case":case["id"], "split":args.split, "variant":name, "repeat":repeat,
                    "expected":case["expected"], "language":case["language"], "attempts":[]}
                command = RetrievalPreflightCommand(request_id=f'{name}-{case["id"]}-{repeat}',owner_id="synthetic-owner",world_id="synthetic-world",thread_id="synthetic-thread",requester_world_character_id="synthetic-requester",responding_world_character_id="synthetic-responder",user_message=case["question"])
                context = () if not case["context"] else (RetrievalRouterContextMessage("assistant",case["context"]),)
                usage, started = [], monotonic()
                token = usage_context.set(usage)
                try:
                    class Observed:
                        async def route(self, request):
                            try:
                                value = await providers[name].route(request)
                            except Exception as exc:
                                row["attempts"].append({"status":"failed", "code":getattr(exc,"validation_code","provider_failure"),
                                    "repair":request.repair_diagnostic is not None,
                                    "validation":getattr(exc,"selection_validation",None)})
                                raise
                            row["attempts"].append({"status":"ok", "repair":request.repair_diagnostic is not None,
                                "validation":value.selection_validation, "argument_protocol":value.argument_protocol,
                                "functions":[c.name for c in value.tool_calls]})
                            return value
                    now = datetime.now(UTC)
                    result = await RetrievalRoutingService(router=Observed(),policy=SyntheticPolicy(case)).route(command,recent_context=context,today_sns_context=case["today_sns"],now=now,deadline_at=now+timedelta(seconds=95))
                    m = result.metrics
                    row.update(status="ok",correct=result.intent.route.value == case["expected"],proposed=m.router_proposed_route.value,
                        effective=result.intent.route.value,first_pass_valid=m.first_pass_valid,repair=m.repair_used,
                        logical=m.router_logical_calls,physical=m.router_physical_attempts,guard=m.sufficiency_guard_reason,
                        semantics=semantic_diagnostics(case["id"],result))
                except Exception as exc:
                    diagnostic = getattr(exc,"router_diagnostic",None)
                    row.update(status="failed",correct=False,error_type=type(exc).__name__,
                        validation_code=getattr(diagnostic,"router_validation_code",None))
                finally:
                    usage_context.reset(token)
                row.update(usage_attempts=usage,elapsed_ms=round((monotonic()-started)*1000))
                with (args.output / "results.jsonl").open("a",encoding="utf-8") as file:
                    file.write(json.dumps(row,ensure_ascii=False)+"\n")
                completed.append(row)
                print(json.dumps({"completed":len(completed),"planned":planned,"variant":name,"case":case["id"],"status":row["status"],"correct":row["correct"]}),flush=True)
        work = []
        for repeat in range(args.repeats):
            for index, case in enumerate(cases):
                offset = (index + repeat) % len(names)
                for name in names[offset:] + names[:offset]:
                    work.append(evaluate(case,name,repeat))
        await asyncio.gather(*work)
        summary = summarize(completed)
        write_json(args.output / "summary.json",summary)
        ledger = json.loads(args.ledger.read_text())
        prefix = "p_execution" if args.split == "development" else "p_heldout"
        ledger[f"{prefix}_initial_completed"] = len(completed)
        ledger[f"{prefix}_physical_calls"] = sum(v["physical_calls"] for v in summary.values())
        write_json(args.ledger,ledger)
        print(json.dumps({"finished":True,"completed":len(completed),"remaining":ledger["remaining"]}),flush=True)
        return 0
    finally:
        direct_llm.generate_text = original_generate
        lock.unlink()


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--ledger",type=Path,required=True)
    parser.add_argument("--variants",default="N0,NA,NAB")
    parser.add_argument("--repeats",type=int,default=3)
    parser.add_argument("--max-calls",type=int,required=True)
    parser.add_argument("--split",choices=["development","heldout"],default="development")
    parser.add_argument("--development",type=Path)
    parser.add_argument("--baseline",type=Path)
    parser.add_argument("--baseline-metadata",type=Path)
    parser.add_argument("--authorized-maximum",type=int,default=312)
    parser.add_argument("--check-only",action="store_true")
    try:
        raise SystemExit(asyncio.run(main(parser.parse_args())))
    except Exception as exc:
        print(json.dumps({"evaluation":"failed","type":type(exc).__name__}),flush=True)
        raise SystemExit(1)
