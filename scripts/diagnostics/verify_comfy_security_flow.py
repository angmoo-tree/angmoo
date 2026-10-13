"""Synthetic HTTP fixture around real Angmoo media services and workers.

Only the external scene writer and ComfyUI are deterministic. No Angmoo API,
analyzer, credential, admission, renderer, worker or result route is stubbed.
Every actor has autonomy OFF. A fixture driver delivers one new routine scene
to the same admit_post entry used by routine_posts after the UI enables images.
"""
from pathlib import Path
from datetime import UTC, datetime
from io import BytesIO
import argparse
import asyncio
import base64
import json
import sys
import threading
from contextlib import asynccontextmanager
from types import SimpleNamespace

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/"backend"))
OWNER="comfy-fixture-owner"
WORLD="019f2000-0000-7000-8000-000000000000"
TOKEN="synthetic-comfy-browser-session-only"
CASES={name:f"019f2000-0000-7000-8000-00000000000{i}" for i,name in enumerate(
    ("text-next","reference-next","text-static","reference-static"),1)}


def mock_app():
    from fastapi import FastAPI, Request, Response
    from PIL import Image
    app=FastAPI();jobs={};audit={name:{"prompt":0,"history":0,"view":0,"upload":0,"scene":0} for name in CASES}
    @app.get("/scene/{name}")
    def scene(name:str):
        assert name in CASES
        audit[name]["scene"]+=1
        return {"scene":"reading at a desk","title":f"Synthetic {name}","body":"Synthetic scene body."}
    @app.get("/comfy/system_stats")
    def stats():return {"system":{"os":"synthetic-external"}}
    @app.get("/comfy/object_info")
    def info():return {"CheckpointLoaderSimple":{"input":{"required":{"ckpt_name":[[f"fixture-{name}.safetensors" for name in CASES]]}}}}
    @app.post("/comfy/upload/image")
    def upload():raise AssertionError("placeholder_reference_must_not_upload")
    @app.post("/comfy/prompt")
    async def prompt(request:Request):
        payload=await request.json();assert set(payload)=={"prompt","extra_data"}
        assert payload["extra_data"]=={"api_key_comfy_org":"synthetic-partner-key"}
        assert "authorization" not in request.headers
        graph=payload["prompt"];name=graph["1"]["inputs"]["ckpt_name"].removeprefix("fixture-").removesuffix(".safetensors")
        assert name in CASES
        reference=name.startswith("reference")
        expected=json.loads((REPO/f"backend/app/domains/media/samples/comfy-api-{'reference' if reference else 'text'}.json").read_text("utf-8"))
        replacements={"%model%":f"fixture-{name}.safetensors","%prompt%":"ink, short hair, reading at a desk",
            "%negative_prompt%":"blur","%width%":512,"%height%":512,"%steps%":20,"%scale%":7,
            "%sampler%":"euler","%scheduler%":"normal","%seed%":17,"%denoise%":.65 if reference else 1}
        def replace(value):
            if isinstance(value,str):return replacements.get(value,value)
            if isinstance(value,list):return [replace(item) for item in value]
            if isinstance(value,dict):return {key:replace(item) for key,item in value.items()}
            return value
        expected=replace(expected)
        if reference:
            encoded=graph["8"]["inputs"]["image"]
            assert isinstance(encoded,str) and not encoded.startswith("data:")
            with Image.open(BytesIO(base64.b64decode(encoded,validate=True))) as image:
                assert image.format=="PNG" and image.size==(16,16) and image.getpixel((0,0))[:3]==(0,255,0)
                assert not image.info
            expected["8"]["inputs"]["image"]=encoded
        assert graph==expected
        assert all(type(graph["4"]["inputs"][field]) is int for field in ("seed","steps"))
        assert isinstance(graph["4"]["inputs"]["cfg"],(int,float))
        audit[name]["prompt"]+=1;assert audit[name]["prompt"]==1
        receipt=f"synthetic-receipt-{name}";jobs[receipt]=name
        return {"prompt_id":receipt,"node_errors":{"7":{"class_type":"SaveImage","errors":[
            {"type":"fixture_warning","message":"<img src=x onerror=window.fixture_xss=1>"}]}}}
    @app.get("/comfy/history/{receipt}")
    def history(receipt:str):
        name=jobs[receipt];audit[name]["history"]+=1
        if audit[name]["history"]==1:return {receipt:{"status":{"completed":False,"status_str":"running"},"outputs":{}}}
        # Deliberately reverse numeric insertion order. JS ordering picks 7,
        # including its first image rather than its second or output node 6.
        return {receipt:{"status":{"completed":True,"status_str":"success"},"outputs":{
            "19":{"images":[{"filename":"wrong.png","type":"output","subfolder":""}]},
            "7":{"images":[{"filename":name+".png","type":"output","subfolder":""},
                {"filename":"wrong-batch.png","type":"output","subfolder":""}]}}}}
    @app.get("/comfy/view")
    def view(filename:str,type:str,subfolder:str=""):
        name=filename.removesuffix(".png");assert name in CASES and type=="output" and not subfolder
        audit[name]["view"]+=1
        output=BytesIO();Image.new("RGB",(16,16),(255,0,0) if name.startswith("text") else (0,0,255)).save(output,"PNG")
        return Response(output.getvalue(),media_type="image/png")
    @app.get("/audit")
    def read_audit():return audit  # Counts only: no payload/key/base64.
    return app


def seed(app):
    from app.core.security import hash_token
    from app.domains.identity.models import User, AuthSession, InstallationIdentity
    from app.domains.identity.models_environment import LocalEnvironment
    from app.domains.worlds.models import World, WorldMembership, OwnerDefaultWorld
    from app.domains.characters.models import Character
    from app.domains.world_characters.models import WorldCharacter, CharacterWorldBinding, CharacterActiveWorld
    from app.domains.routines.models import AgentActivitySetting
    from app.runtime.world_characters.creation_configuration import initialize_created_world_character
    from app.domains.media.setting_schemas import GenerationSettingsWrite
    from app.domains.media.models_world_policy import WorldImagePolicy
    from app.domains.identity.service import world_credentials
    from app.domains.identity.schemas import WorldCredentialWrite
    media=app.state.media_runtime
    with app.state.runtime_composition.session_factory() as db:
        assert db.get(User,OWNER) is None,"fixture_root_already_used"
        owner=User(id=OWNER,display_name="Comfy fixture owner",display_name_normalized="comfy fixture owner",
            profile_setup_completed=True,ui_language="en",privacy_policy_version="fixture",terms_version="fixture")
        db.add(owner);db.flush()
        installation=db.get(InstallationIdentity,"local-installation")
        installation.owner_user_id,installation.bootstrap_state,installation.claimed_at=OWNER,"claimed",datetime.now(UTC)
        db.add(LocalEnvironment(owner_id=OWNER,installation_id=installation.installation_id,
            preferred_language="en-US",timezone="UTC",confirmed_at=datetime.now(UTC),environment_revision=1))
        db.add(AuthSession(token_hash=hash_token(TOKEN),user_id=OWNER,auth_method="local_owner",created_at=datetime.now(UTC)))
        db.add(World(id=WORLD,slug="comfy-fixture",owner_user_id=OWNER,name="Comfy fixture",visibility="private",
            status="published",readiness_status="publish_ready",setting_description="Synthetic setting. "*20,
            daily_life_description="Synthetic ordinary routine. "*20,contract_version="world-v1",contract_hash="a"*64,create_idempotency_key="fixture-world"))
        db.flush();db.add(WorldMembership(id="comfy-membership",world_id=WORLD,user_id=OWNER,role="owner",status="active"))
        db.add(OwnerDefaultWorld(owner_id=OWNER,world_id=WORLD));db.flush()
        old=json.loads((REPO/"backend/app/domains/media/samples/comfy-text.json").read_text("utf-8"))
        for name,identifier in CASES.items():
            character=Character(id=identifier,owner_id=OWNER,name=name,handle=name.replace("-","_"),one_liner="Synthetic fixture",
                personality="calm",speech_style="calm",worldview="synthetic",topic_preferences="routine",safety_rules="safe",
                status="active",moderation_status="active",execution_mode="llm",persona_summary="synthetic")
            db.add(character)
            db.flush()
            role=WorldCharacter(id="actor-"+name,world_id=WORLD,character_id=identifier,membership_id="comfy-membership",
                role_key="no_specific_role",status="active",autonomous_enabled=False,control_mode="autonomous",world_contract_hash="a"*64)
            db.add(role)
            db.add(AgentActivitySetting(character_id=identifier,auto_enabled=False))
            db.add(CharacterWorldBinding(character_id=identifier,world_id=WORLD));db.flush()
            db.add(CharacterActiveWorld(character_id=identifier,world_character_id=role.id,selected_at=datetime.now(UTC),idempotency_key="fixture-"+name,version=1))
            db.flush();initialize_created_world_character(db,character=character,world_character=role)
            original={"base_url":"http://localhost:3442/comfy","partner_auth":True,"workflow":{**old["workflow"],"output_node":"6"},
                "values":{"model":"","seed":17,"clip_skip":-1}}
            media.write_generation(db,owner,identifier,GenerationSettingsWrite(expected_revision=0,provider="comfyui",model="workflow",
                options=original,auto_enabled=False,daily_limit=4,installation_daily_limit=12,appearance="short hair",style="ink",negative="blur",
                reference_enabled=False,partner_api_key="synthetic-partner-key"))
            world_credentials.save(db,owner_id=OWNER,world_id=WORLD,world_character_id=role.id,purpose="image",
                data=WorldCredentialWrite(expected_revision=0,expected_key_revision=0,provider="comfyui",model="workflow",partner_api_key="synthetic-partner-key"))
            db.get(WorldImagePolicy,role.id).generation_settings={"appearance":"short hair","style":"ink","negative":"blur",
                "reference_enabled":False,"profiles":{"comfyui:workflow":{"options":original,"connection":None}}}
        db.commit()


async def deliver_scenes(app):
    """Fixed external scene-writer seam, then actual app admission/worker."""
    import httpx
    from app.domains.social.models.posts import Post
    from app.domains.characters.models import AgentImageGenerationSetting
    sessions=app.state.runtime_composition.session_factory;done=set()
    async with httpx.AsyncClient(trust_env=False) as client:
        while True:
            for name,identifier in CASES.items():
                if name in done:continue
                with sessions() as db:
                    row=db.get(AgentImageGenerationSetting,identifier)
                    enabled=bool(row and row.generation_auto_enabled)
                if not enabled:continue
                draft=(await client.get(f"http://127.0.0.1:3442/scene/{name}")).json()
                with sessions() as db:
                    post=Post(id="post-"+name,author_user_id=OWNER,author_character_id=identifier,author_name=name,
                        world_id=WORLD,author_world_character_id="actor-"+name,title=draft["title"],body=draft["body"])
                    db.add(post);db.flush()
                    intent=app.state.media_runtime.admit_post(db,post=post,owner_id=OWNER,character_id=identifier,
                        draft=SimpleNamespace(_image_prompt=draft["scene"],_image_error=None))
                    assert intent is not None and intent.state=="queued",f"fixture_admission_failed:{getattr(intent,'reason',None)}"
                    db.commit()
                done.add(name)
            await asyncio.sleep(.2)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--origin",choices=("http://127.0.0.1:3440","http://127.0.0.1:3441"),default="http://127.0.0.1:3440")
    args=parser.parse_args();root=args.root.resolve()
    marker=root/".synthetic-comfy-security"
    if root.exists() and any(root.iterdir()):raise RuntimeError("fresh_synthetic_root_required")
    root.mkdir(parents=True,exist_ok=True);marker.touch()
    from app.config import settings
    settings.APP_ENV="development";settings.BROWSER_SESSION_ALLOWED_ORIGINS=args.origin
    settings.MEDIA_ROOT=str(root/"media")
    from app.runtime.contributor_backend import create_contributor_runtime_app
    app=create_contributor_runtime_app(data_root=root,frontend_origin=args.origin)
    if args.origin.endswith(":3441"):
        # Contributor mode normally uses Next's same-origin proxy. The static
        # browser fixture needs CORS for this one exact synthetic origin; its
        # real session, CSRF, owner and media-scope checks remain unchanged.
        from starlette.middleware.cors import CORSMiddleware
        app.add_middleware(CORSMiddleware,allow_origins=[args.origin],allow_credentials=True,
            allow_methods=["GET","POST","PUT","PATCH","DELETE"],allow_headers=["content-type","x-angmoo-frontend-origin"])
    seed(app)
    original=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with original(application):
            driver=asyncio.create_task(deliver_scenes(application))
            try:yield
            finally:
                driver.cancel()
                try:await driver
                except asyncio.CancelledError:pass
    app.router.lifespan_context=lifespan
    import uvicorn
    threading.Thread(target=lambda:uvicorn.run(mock_app(),host="127.0.0.1",port=3442,log_level="warning"),daemon=True).start()
    uvicorn.run(app,host="127.0.0.1",port=3443,log_level="warning")


if __name__=="__main__":main()
