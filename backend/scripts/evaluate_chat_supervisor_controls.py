"""F2/F3/F4 opt-in synthetic selection evaluation; no retrieval or product writes."""
import argparse
import asyncio
from contextvars import ContextVar
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
from time import monotonic

from evaluate_chat_supervisor_selection import read_material, load_baseline, SyntheticPolicy
from app.integrations import direct_llm
from app.integrations.llm import supervisor_selection as selected
from app.domains.chat.contracts.retrieval_policy import RetrievalPreflightCommand
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterContextMessage
from app.domains.chat.service.retrieval_routing import RetrievalRoutingService


def digest(value):
    return hashlib.sha256(value).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temporary, path)


async def main(args):
    names = args.variants.split(",")
    # M2 must not be created/run before the F2 format gate passes.
    if len(set(names)) != len(names) or not set(names) <= {"M0", "M1"}:
        raise ValueError("evaluation_variants_invalid")
    cases = json.loads(args.inputs.read_text(encoding="utf-8"))
    if len(cases) != 32 or sum(c["split"] == "development" for c in cases) != 8:
        raise ValueError("evaluation_fixture_changed")
    if digest(args.inputs.read_bytes()) != "f95f0bef3dbe863815138e46c46bf211036fff0bb780d244e07b55540affda7a":
        raise ValueError("evaluation_fixture_changed")
    cases = [c for c in cases if c["split"] == args.split]
    planned = len(cases) * len(names) * args.repeats
    if planned > args.max_calls or args.max_calls > 168:
        raise ValueError("evaluation_budget_invalid")
    material, saved = read_material()
    material = replace(material, model="gemini-3.1-flash-lite", thinking_level="high")
    baseline = load_baseline(args.baseline, "evaluation_controls_m0")
    providers = {"M0": baseline.DirectLlmSupervisorSelectionProvider(material), "M1": selected.DirectLlmSupervisorSelectionProvider(material, native_controls=True)}
    prompts = {"M0": baseline.selection_system_prompt(), "M1": selected.control_selection_system_prompt()}
    schemas = {"M0": baseline.selection_tools(), "M1": selected.control_selection_tools()}
    args.output.mkdir(exist_ok=False)
    ledger = json.loads(args.ledger.read_text())
    if not 0 <= ledger["started"] <= 312 or ledger["maximum"] != 312 or ledger["started"] + planned > 312:
        raise ValueError("evaluation_global_budget_invalid")
    lock = args.ledger.with_suffix(".lock")
    with lock.open("x") as file:
        file.write(str(os.getpid()))
    try:
        source = Path(selected.__file__).parents[2]
        meta = {
            "started_at": datetime.now(UTC).isoformat(), "model": material.model, "thinking": material.thinking_level,
            "output_limit": 3072, "provider_timeout_seconds": 30, "request_deadline_seconds": 95,
            "saved_model": saved["default_model"], "saved_thinking": saved["default_thinking_level"],
            "sdk": importlib.metadata.version("google-genai"), "langgraph": importlib.metadata.version("langgraph"),
            "split": args.split, "repeats": args.repeats, "variants": names, "planned_initial_calls": planned,
            "ledger_started_before": ledger["started"], "input_hash": digest(args.inputs.read_bytes()),
            "prompt_hashes": {name: digest(prompts[name].encode()) for name in names},
            "schema_hashes": {name: digest(json.dumps([asdict(t) for t in schemas[name]], sort_keys=True).encode()) for name in names},
            "source_hashes": {str(path.relative_to(source)): digest(path.read_bytes()) for path in source.rglob("*.py") if "__pycache__" not in path.parts},
            "m0_adapter_hash": digest(args.baseline.read_bytes()), "concurrency": 2,
            "notes": "Synthetic resolver. No retrieval, CRG, chat, memory writes. Temperature/seed not set. All failures retained.",
        }
        write_json(args.output / "metadata.json", meta)
        usage_context = ContextVar("controls_evaluation_usage", default=None)
        original_generate = direct_llm.generate_text
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
                if not 0 <= ledger["started"] < ledger["maximum"] == 312:
                    raise ValueError("evaluation_global_budget_exhausted")
                ledger["started"] += 1
                write_json(args.ledger, ledger)
                row = {"case":case["id"], "split":case["split"], "language":case["language"], "expected":case["expected"], "variant":name, "repeat":repeat}
                command = RetrievalPreflightCommand(request_id=f'{name}-{case["id"]}-{repeat}',owner_id="synthetic-owner",world_id="synthetic-world",thread_id="synthetic-thread",requester_world_character_id="synthetic-requester",responding_world_character_id="synthetic-responder",user_message=case["question"])
                context = () if not case["context"] else (RetrievalRouterContextMessage("assistant",case["context"]),)
                usage = []
                token = usage_context.set(usage)
                start = monotonic()
                try:
                    class Observed:
                        async def route(self, request):
                            try:
                                return await providers[name].route(request)
                            except Exception as exc:
                                row.setdefault("attempt_errors", []).append({"type":type(exc).__name__, "code":getattr(exc,"validation_code",None), "physical":getattr(exc,"physical_attempt_count",None), "shape":getattr(exc,"selection_shape",None)})
                                raise
                    now = datetime.now(UTC)
                    result = await RetrievalRoutingService(router=Observed(),policy=SyntheticPolicy(case)).route(command,recent_context=context,today_sns_context=case["today_sns"],now=now,deadline_at=now+timedelta(seconds=95))
                    m = result.metrics
                    row.update(status="ok", correct=result.intent.route.value == case["expected"], proposed=m.router_proposed_route.value,
                        effective=result.intent.route.value, first_pass_valid=m.first_pass_valid, repair=m.repair_used,
                        logical=m.router_logical_calls, physical=m.router_physical_attempts, guard=m.sufficiency_guard_reason,
                        functions=[call.name for call in result.proposed_tool_calls])
                except Exception as exc:
                    diagnostic = getattr(exc,"router_diagnostic",None)
                    row.update(status="failed",correct=False,error_type=type(exc).__name__,validation_code=getattr(diagnostic,"router_validation_code",None))
                finally:
                    usage_context.reset(token)
                row.update(usage_attempts=usage,elapsed_ms=round((monotonic()-start)*1000))
                with (args.output / "results.jsonl").open("a",encoding="utf-8") as file:
                    file.write(json.dumps(row,ensure_ascii=False)+"\n")
                completed.append(row)
                print(json.dumps({"completed":len(completed),"variant":name,"case":case["id"],"status":row["status"],"correct":row["correct"]}),flush=True)
        work = []
        for repeat in range(args.repeats):
            for index, case in enumerate(cases):
                offset = (index + repeat) % len(names)
                for name in names[offset:] + names[:offset]:
                    work.append(evaluate(case, name, repeat))
        await asyncio.gather(*work)
        summary = {name:{"n":len(rows),"first_pass_valid":sum(r.get("first_pass_valid",False) for r in rows),"valid_after_repair":sum(r["status"]=="ok" for r in rows),"correct":sum(r["correct"] for r in rows)} for name in names for rows in [[r for r in completed if r["variant"]==name]]}
        write_json(args.output / "summary.json", summary)
        print(json.dumps({"finished":summary}),flush=True)
        return 0  # Controller completed; adoption is an independent recorded gate.
    finally:
        lock.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs",type=Path,required=True)
    parser.add_argument("--baseline",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--ledger",type=Path,required=True)
    parser.add_argument("--split",choices=["development","heldout"],required=True)
    parser.add_argument("--variants",default="M0,M1")
    parser.add_argument("--repeats",type=int,choices=[2,3],default=3)
    parser.add_argument("--max-calls",type=int,required=True)
    try:
        raise SystemExit(asyncio.run(main(parser.parse_args())))
    except Exception as exc:
        print(json.dumps({"evaluation":"failed","type":type(exc).__name__}),flush=True)
        raise SystemExit(1)
