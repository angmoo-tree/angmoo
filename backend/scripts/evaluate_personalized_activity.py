"""Opt-in actual-provider contract/behavior probes on synthetic frozen inputs.

Canonical data is opened read-only ONLY to resolve the specified existing
character credential. No scheduler, graph effects, retrieval or publication is
started. This report is not evidence of retrieval quality or a full V1/V2 win.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
from time import monotonic
from types import SimpleNamespace

from app.config import settings
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity.contracts import Candidate
from app.runtime.autonomous_activity.provider import ActivityProvider, SELECTOR_INSTRUCTIONS, PLANNER_INSTRUCTIONS
from app.runtime.autonomous_activity.queries import validate_selection


CASES = [
    ("negation", "약속을 어긴 게 아니야. 배가 결항돼 도착하지 못했어.", "상대는 이전에 이동이 불가능할 때 미리 연락했고 약속을 지켰다."),
    ("correction", "내가 도구를 망가뜨렸다는 말은 정정됐어. 수리가 끝났어.", "처음에는 상대가 도구를 망가뜨렸다고 생각했지만 정비 기록으로 자연 마모임을 확인했다."),
    ("repetition", "다음에는 무리하지 말고 같이 쉬자.", "이미 같은 조언에 감사했고 충분히 쉬겠다고 답하면서 그 대화를 마무리했다."),
    ("ordinary", "오늘 점심은 국수야.", ""),
    ("proposal", "다음 주 전시를 같이 보러 갈래?", "지난번에는 일정이 겹쳐 전시 동행을 거절했다. 이번 주의 일정은 아직 정하지 않았다."),
    ("ambiguous", "또 일찍 왔네.", "상대는 예전에도 일찍 도착한 내게 자리를 마련해 주었다. 오늘 말투의 의도는 아직 모른다."),
    ("help", "잃어버린 자료의 사본을 찾았어. 필요하면 줄게.", "상대에게 자료 분실을 이야기했지만 아직 사본은 받지 못했다."),
    ("conflict", "그 방법엔 반대야. 다른 방법을 검토해 보자.", "이 상대의 반대 의견 덕분에 지난 작업에서 위험한 부분을 고쳤다."),
    ("heldout_cancellation", "내일 배송은 취소됐어. 포장은 아직 시작 안 했어.", "상대가 내일 물건을 보내기로 약속했지만 실제 배송 완료 기록은 없다."),
    ("heldout_question", "지난번 고민은 어떻게 됐어?", "지난 대화에서 새 일자리를 고민한다고 말했지만 결정한 기록은 없다."),
    ("heldout_multi_speaker", "수아가 장부를 잃어버렸대. 나는 사본을 보관해 뒀어.", "예전 장부 실수의 당사자는 수아였다. 현재 말하는 상대는 사본을 잘 관리해 왔다."),
    ("heldout_independence", "정말 고마워. 하지만 이번 작품은 내가 직접 마무리하고 싶어.", "상대가 이전 작품에서는 함께 수정해 달라고 요청했다."),
]
PERSONAS = ["침착하고 근거를 확인하는 신중한 기록가", "적극적으로 격려하지만 상대의 거절을 존중하는 낙관적인 동료", "직설적이고 경쟁을 즐기지만 정정에는 공정한 장인"]


def credential(root, character_id):
    canonical = root.resolve() / "canonical"
    marker = json.loads((canonical / "current-generation.json").read_text())
    database = (canonical / marker["relative_path"] / "angmoo.sqlite3").resolve()
    if not database.is_relative_to(canonical):
        raise ValueError("evaluation_path_invalid")
    settings.APP_SECRET_FILE = str(root / "secrets" / "app-secret")
    settings.CREDENTIAL_ENCRYPTION_PROVIDER = "local"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT * FROM llm_credentials WHERE character_id=? AND purpose='agent' AND enabled=1", (character_id,)).fetchall()
        if len(rows) != 1:
            raise ValueError("evaluation_credential_unavailable")
        return SimpleNamespace(**dict(rows[0]))


async def run(args):
    if args.output.exists():
        raise ValueError("evaluation_output_exists")
    cred = credential(args.root, args.character_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    metadata = {"model": cred.model, "thinking": cred.thinking_level, "kind": "real_ai_synthetic_inputs",
        "retrieval_performed": False, "operational_writes": False,
        "prompt_hash": hashlib.sha256((SELECTOR_INSTRUCTIONS + PLANNER_INSTRUCTIONS).encode()).hexdigest()}
    args.output.with_suffix(".meta.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    limit = asyncio.Semaphore(2)
    async def case(index, entry):
        async with limit:
            case_id, text, memory = entry
            tracker = RunLlmTracker(max_calls=3)
            context = SimpleNamespace(credential=cred, character=SimpleNamespace(id=args.character_id),
                run_id="evaluation-v2-" + case_id, generation_thinking_level=cred.thinking_level,
                on_rate_limit_wait=None)
            provider = ActivityProvider(context, tracker)
            target = Candidate(target_id="target", counterpart_id="partner", source_ids=["source"], text=text,
                allowed_actions=["comment", "like"]).model_dump()
            other = Candidate(target_id="other", counterpart_id="other-person", source_ids=["other-source"],
                text="게시판 점검이 끝났습니다.", allowed_actions=["like"]).model_dump()
            shared = {"persona": PERSONAS[index % 3], "current_state": {"known": True,"mood":"calm","mood_intensity":25,"state_note":"차분하게 하루를 보내고 있다."},
                "today_activity": [], "state_elapsed_seconds": 1800, "metric_sources": [{"source_ref":"source","target_ref":"partner","text":text}]}
            start = monotonic()
            row = {"case":case_id,"persona":index % 3,"heldout":index >= 8}
            try:
                selected = await provider.select(lane="feed", context=shared, candidates=[target,other], limit=1)
                validated = validate_selection(selected,[Candidate.model_validate(target),Candidate.model_validate(other)],1)
                row["selections"] = [s.model_dump() for s in validated]
                # Freeze the same target in the paired action test; selection
                # quality and effect of memory are independent questions.
                for variant, recalled in (("without_memory", ""),("with_memory", memory)):
                    result = await provider.plan(lane="inbox", context={**shared,"memories":recalled}, candidates=[target])
                    result.pop("judged_at", None)
                    row[variant] = result
                row["status"] = "valid"
            except Exception as exc:
                row.update(status="failed", reason=type(exc).__name__)
            row.update(duration_ms=round((monotonic()-start)*1000),usage=tracker.summary())
            for call in row["usage"].get("calls", []):
                for key in ("credential_id", "key_fingerprint", "character_id"):
                    call.pop(key, None)
            with args.output.open("a",encoding="utf-8") as output:
                output.write(json.dumps(row,ensure_ascii=False,default=str)+"\n")
            print(json.dumps({"case":case_id,"status":row["status"],"duration_ms":row["duration_ms"]}),flush=True)
    await asyncio.gather(*(case(i,entry) for i,entry in enumerate(CASES)))


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--character-id",required=True)
    parser.add_argument("--output",type=Path,required=True)
    asyncio.run(run(parser.parse_args()))
