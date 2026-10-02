"""Opt-in R01-R05. Read only the approved scoped source; never persist its key."""
import argparse
import asyncio
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
from io import BytesIO
import json
import ipaddress
import socket
import sqlite3
import sys
from tempfile import TemporaryDirectory
from time import monotonic
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "tests"))


def physical_read_path(path):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    handle = kernel.CreateFileW(str(path),0x80000000,7,None,3,0,None)
    if handle == ctypes.c_void_p(-1).value: raise RuntimeError("approved_source_open_failed")
    try:
        kernel.GetFinalPathNameByHandleW.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD]
        buffer=ctypes.create_unicode_buffer(32768)
        if not kernel.GetFinalPathNameByHandleW(handle,buffer,32768,0): raise RuntimeError("approved_source_identity_unverified")
        actual=buffer.value.lower().replace("\\\\?\\unc\\","\\\\").replace("\\\\?\\","")
        expected=str(path).lower()
        # UNC reads may be opened by the redirector or resolved to the local volume.
        local=expected.replace("\\\\localhost\\c$\\","c:\\",1)
        if actual not in {expected,local}: raise RuntimeError("approved_source_identity_differs")
    finally:
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        kernel.CloseHandle(handle)


def approved_material(args):
    physical_read_path(args.database); physical_read_path(args.secret_file)
    from app.config import settings
    from app.domains.identity.service.credential_resolution import CredentialResolver
    from app.domains.identity.contracts import CredentialPurpose
    settings.APP_SECRET_FILE=str(args.secret_file)
    settings.CREDENTIAL_ENCRYPTION_PROVIDER="local"
    with sqlite3.connect("file:"+str(args.database)+"?mode=ro",uri=True) as db:
        db.row_factory=sqlite3.Row
        rows=db.execute("SELECT id,owner_id,name FROM characters WHERE name=? AND deleted_at IS NULL",("미도리야 이즈쿠",)).fetchall()
        if len(rows)!=1 or rows[0]["id"]!=args.character_id or rows[0]["owner_id"]!=args.owner_id:
            raise RuntimeError("approved_character_scope_differs")
        source=db.execute("SELECT id,owner_id,character_id,provider,purpose,model,encrypted_api_key,key_fingerprint,enabled,thinking_level FROM llm_credentials WHERE id=?",(args.credential_id,)).fetchone()
        if source is None or source["provider"]!="google": raise RuntimeError("approved_credential_missing")
        material=CredentialResolver.resolve_llm_credential(SimpleNamespace(**dict(source)),purpose=CredentialPurpose.RESIDENT_LLM,
            owner_id=args.owner_id,character_id=args.character_id)
        return material


def only_gemini_network():
    original_dns=socket.getaddrinfo; original_connect=socket.socket.connect; allowed=set()
    def dns(host,*args,**kwargs):
        name=host.decode() if isinstance(host,bytes) else host
        if name not in {"generativelanguage.googleapis.com","127.0.0.1","::1","localhost"}: raise RuntimeError("live_network_target_denied")
        values=original_dns(host,*args,**kwargs)
        allowed.update(value[4][0] for value in values)
        return values
    def connect(sock,address):
        if not isinstance(address,tuple) or (address[0] not in allowed and not ipaddress.ip_address(address[0]).is_loopback): raise RuntimeError("live_network_target_denied")
        return original_connect(sock,address)
    socket.getaddrinfo=dns; socket.socket.connect=connect


def fixture(kind):
    from PIL import Image,ImageDraw,ImageFont
    image=Image.new("RGB",(480,240),"white"); draw=ImageDraw.Draw(image)
    if kind=="letters":
        font=ImageFont.truetype("C:/Windows/Fonts/malgun.ttf",38)
        draw.text((20,35),"파란 컵 123",font=font,fill="black")
        draw.text((20,120),"ANGMOO 42",font=font,fill="black")
    else:
        draw.ellipse((35,40,190,195),fill="blue")
        draw.polygon([(300,35),(230,195),(390,195)],fill="red" if kind=="shapes" else "green")
    output=BytesIO(); image.save(output,"PNG"); return output.getvalue()


async def run(args,material,folder,report):
    from sqlalchemy import create_engine,select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.runtime.persistence.model_registration import register_models
    from app.domains.identity.models import User
    from app.domains.media.service.assets import AssetService
    from app.domains.media.service.interpretation import InterpretationService,write_interpretation_settings
    from app.domains.media.setting_schemas import InterpretationSettingsWrite
    from app.domains.media.models import InterpretationSetting
    from app.integrations.llm.image_interpretation import GeminiImageInterpreter
    from app.providers.gemini import GeminiAdapter
    from app.domains.chat.contracts.image_evidence import ChatImageEvidence,visible_context
    from app.domains.chat.service.evidence_assembly import EvidenceBundleAssembler
    owner="synthetic-recognition-owner"; scopes={"public-fixture","private-a","private-b"}
    engine=create_engine("sqlite://",poolclass=StaticPool)
    register_models().create_all(engine); sessions=sessionmaker(engine)
    with sessions() as db:
        db.add(User(id=owner,email="recognition@example.test",display_name="Synthetic")); db.commit()
        write_interpretation_settings(db,owner,InterpretationSettingsWrite(expected_revision=0,enabled=True,daily_limit=6,
            model="gemini-3.1-flash-lite",thinking_level="medium",api_key=material.reveal())); db.commit()
    def authorize(db,received_owner,kind,scope):
        if received_owner!=owner or scope not in scopes: raise RuntimeError("synthetic_scope_forbidden")
    assets=AssetService(Path(folder)/"pixels",authorize)
    class CountedGemini:
        def __init__(self): self.calls=args.prior_requests; self.delegate=GeminiAdapter()
        async def generate_json(self,request):
            if self.calls>=6 or request.model!="gemini-3.1-flash-lite" or request.thinking_level!="medium" or request.sdk_attempts!=1 or len(request.image_parts)!=1:
                raise RuntimeError("approved_live_bound_exceeded")
            report["adapter_attempts"] += 1
            try:
                result=await self.delegate.generate_json(request)
                report["last_public_fixture_response"]={"text":(result.text or "")[:8000],"parsed":result.parsed}
                return result
            except Exception as exc:
                code=getattr(exc,"provider_code",None) or getattr(exc,"code",None)
                report["provider_failure"]={"class":getattr(exc,"failure_class",None) or type(exc).__name__,"code":code if type(code) is int else None}
                raise
    counted=CountedGemini()
    # Count at the actual sync HTTP transport, after SDK serialization. A local
    # validation failure is an adapter attempt, not a physical paid request.
    import httpx
    original_send = httpx.Client.send
    def bounded_send(client, request, *positional, **keyword):
        if (request.url.host != "generativelanguage.googleapis.com" or request.method != "POST"
                or not request.url.path.endswith("/models/gemini-3.1-flash-lite:generateContent")):
            raise RuntimeError("unapproved_live_http_request")
        if counted.calls >= 6:
            raise RuntimeError("approved_live_bound_exceeded")
        counted.calls += 1
        report["physical_requests"] = counted.calls
        return original_send(client, request, *positional, **keyword)
    httpx.Client.send = bounded_send
    service=InterpretationService(sessions,assets,GeminiImageInterpreter(counted),quota_day=lambda at:at.date().isoformat())
    def upload(kind,scope="public-fixture"):
        with sessions() as db:
            asset=assets.upload(db,owner_id=owner,scope_kind="world" if scope=="public-fixture" else "thread",scope_id=scope,content_type="image/png",content=fixture(kind),draft=False); identity=asset.id;db.commit();return identity
    async def analyze(case,identity):
        started=monotonic()
        with sessions() as db: row=await service.interpret(db,owner,identity); value=json.loads(row.result_json)
        report["results"].append({"id":case,"elapsed_seconds":round(monotonic()-started,3),"analysis":value})
        return row,value
    try:
        r1=upload("shapes");await analyze("R01",r1)
        r2=upload("letters");_,ocr=await analyze("R02",r2)
        report["ocr_expected"]=["파란 컵 123","ANGMOO 42"]
        report["ocr_exact_visible_text"]={text:any(text in line for line in ocr.get("visible_text",[])) for text in report["ocr_expected"]}
        r3=upload("other")
        before=counted.calls
        async def selected():
            with sessions() as db:return (await service.interpret(db,owner,r3)).id
        joined=await asyncio.gather(selected(),selected())
        report["results"].append({"id":"R03","shared_identity":joined[0]==joined[1],"new_physical_requests":counted.calls-before})
        from image_integration.chat_support import synthetic_chat
        from app.config import Settings
        from app.domains.chat.schemas import WorldChatMessageCreate
        from app.domains.chat.models import MessageAttachment, MessageMessage
        for scope,text in [("private-a",""),("private-b","이 사진에 보이는 도형을 설명해 줘.")]:
            chat=synthetic_chat(Path(folder)/scope,GeminiImageInterpreter(counted),key=material.reveal())
            try:
                with chat.sessions() as local:
                    asset=chat.media.assets.upload(local,owner_id=chat.owner.id,scope_kind="thread",scope_id=chat.thread_id,
                        content_type="image/png",content=fixture("shapes"));identity=asset.id;local.commit()
                accepted=chat.generation.accept_world_message(chat.db,chat.owner,chat.world_id,chat.thread_id,
                    WorldChatMessageCreate(content=text,attachment_asset_id=identity,idempotency_key="synthetic-live-message-001"))
                events=[event async for event in chat.generation.stream_world_response(chat.db,chat.owner,
                    chat.world_id,chat.thread_id,accepted.response_request.request_id,memory_recall_service=object(),
                    runtime_settings=Settings(graph_projection_enabled=False))]
                attachment=chat.db.get(MessageAttachment,accepted.user_message.id)
                body=chat.db.get(MessageMessage,accepted.user_message.id).content
                value=json.loads(attachment.snapshot_json)["analysis"] if attachment.snapshot_json else None
                report["results"].append({"id":"R04-"+scope,"analysis":value,"user_body_preserved":body==text,
                    "image_evidence_kind":chat.generator.requests[0].evidence.items[0].kind.value if chat.generator.requests else None,
                    "workflow_order":chat.events,"terminal_event":events[-1].event_type.value,
                    "private_asset":identity,"real_text_provider_requests":0})
                if events[-1].event_type.value!="completed": raise RuntimeError("live_chat_workflow_failed")
            finally:
                await chat.media.interpretation.close();chat.source.close()
        with sessions() as db:
            db.get(InterpretationSetting,owner).enabled=False;db.commit();state=service.preflight(db,owner,r1)
            before=counted.calls;cached=await service.interpret(db,owner,r1)
            report["results"].append({"id":"R05","off_cache_reused":state["reason"]=="cached" and bool(cached.description),"new_physical_requests":counted.calls-before})
        from app.domains.media.models import InterpretationAttempt
        with sessions() as db:
            report["attempt_usage"]=[{"status":r.status,"usage":json.loads(r.usage_json) if r.usage_json else None} for r in db.scalars(select(InterpretationAttempt))]
        report["status"]="completed"
    finally:
        await service.close();engine.dispose()
        httpx.Client.send = original_send


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--database",type=Path,required=True);parser.add_argument("--secret-file",type=Path,required=True)
    parser.add_argument("--owner-id",required=True);parser.add_argument("--character-id",required=True);parser.add_argument("--credential-id",required=True);parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--prior-requests",type=int,default=0)
    args=parser.parse_args()
    if not 0 <= args.prior_requests < 6: parser.error("prior requests must be within the approved bound")
    report={"status":"not_started","model":"gemini-3.1-flash-lite","thinking_level":"medium","physical_requests":args.prior_requests,"adapter_attempts":0,"results":[],"generation_requests":0,"production_writes":0}
    started=monotonic()
    try:
        material=approved_material(args);report["source_scope_verified"]=True;only_gemini_network()
        with TemporaryDirectory(prefix="angmoo-image-recognition-") as folder:
            async def bounded():
                async with asyncio.timeout(600):await run(args,material,folder,report)
            asyncio.run(bounded())
    except Exception as exc:
        report["status"]="failed";report["error_code"]=getattr(exc,"failure_class",None) or type(exc).__name__
    report["elapsed_seconds"]=round(monotonic()-started,3);args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({key:report[key] for key in ["status","physical_requests","elapsed_seconds"]}))
    return 0 if report["status"]=="completed" else 1
if __name__=="__main__":raise SystemExit(main())
