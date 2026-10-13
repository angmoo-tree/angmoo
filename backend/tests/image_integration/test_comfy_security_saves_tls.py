"""Real save/CAS boundaries and actual loopback TLS, with synthetic secrets."""
import asyncio
from copy import deepcopy
from datetime import UTC,datetime,timedelta
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
import ssl
import threading
from types import SimpleNamespace
import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.orm import Session
from app.domains.media.generation_contracts import ComfyOptions,ImagePreparationError,ImageSubmissionError
from app.domains.media.setting_schemas import GenerationSettingsWrite
from app.domains.identity.models import User
from app.domains.characters.models import AgentImageGenerationSetting
from image_integration.test_generation_lifecycle import configured,OWNER,CHARACTER
from image_integration.test_comfy_partner import WORKFLOW
from app.integrations.image_api import ImageHttp


def test_character_unsafe_save_rolls_back_revision_credentials_and_keeps_off_cleanup(tmp_path):
    sessions,media,_=configured(tmp_path,"comfyui","workflow")
    with sessions() as db:
        owner=db.get(User,OWNER);saved=media.read_generation(db,owner,CHARACTER)
        unsafe=ComfyOptions(base_url="http://private.example.test",partner_auth=True,workflow=WORKFLOW).model_dump(exclude_none=True)
        command=GenerationSettingsWrite(expected_revision=saved["revision"],provider="comfyui",model="workflow",auto_enabled=False,
            daily_limit=4,options=unsafe,partner_api_key="new-synthetic-key")
        with pytest.raises(ImagePreparationError,match="https_required"):media.write_generation(db,owner,CHARACTER,command)
        db.rollback();assert media.read_generation(db,owner,CHARACTER)==saved
        # Historical profile is a fixture record, not a successful unsafe save.
        row=db.get(AgentImageGenerationSetting,CHARACTER)
        row.generation_profiles_json=json.dumps({"comfyui:workflow:":{"active":True,"reference_initialized":True,"reference_enabled":False,"options":unsafe,"connection":None}})
        row.generation_auto_enabled=False;db.commit()
        off=media.read_generation(db,owner,CHARACTER)
        media.write_generation(db,owner,CHARACTER,command.model_copy(update={"partner_api_key":None,"clear_partner_api_key":True,"expected_revision":off["revision"]}))
        db.commit();assert not media.read_generation(db,owner,CHARACTER)["has_partner_api_key"]
        with pytest.raises(ImagePreparationError,match="revision_conflict"):
            media.write_generation(db,owner,CHARACTER,command.model_copy(update={"partner_api_key":None,"options":{**unsafe,"partner_auth":False}}))
        db.rollback()


def test_world_selected_key_and_settings_reject_unsafe_and_allow_off_history(tmp_path,deny_external_network):
    from world_configuration_fixture_support import seed_configuration_fixture
    from app.domains.media.models_world_policy import WorldImagePolicy
    from app.domains.media.schemas import WorldImagePolicyPatch
    from app.domains.identity.schemas import WorldCredentialWrite
    from app.runtime.world_characters import credentials,image_policy
    from app.runtime.world_characters.management import management_service
    from app.domains.identity.service import world_credentials
    engine=seed_configuration_fixture(tmp_path/"world.sqlite3")
    with Session(engine) as db:
        service=management_service(db);owner=db.get(User,"fixture-owner");row=db.get(WorldImagePolicy,"config-role-a")
        scope=dict(world_id="config-world-a",world_character_id="config-role-a",user=owner)
        unsafe=ComfyOptions(base_url="http://host.docker.internal:8188",partner_auth=True,workflow=WORKFLOW).model_dump(exclude_none=True)
        old={"profiles":{"comfyui:workflow":{"options":unsafe,"connection":None}}}
        row.generation_settings=old;db.commit();revision=row.revision
        with pytest.raises(ImagePreparationError,match="https_required"):
            credentials.write(service,**scope,purpose="image",data=WorldCredentialWrite(expected_revision=0,expected_key_revision=0,
                expected_configuration_revision=revision,provider="comfyui",model="workflow",partner_api_key="synthetic-world-key"))
        assert db.get(WorldImagePolicy,"config-role-a").revision==revision
        assert world_credentials.find(db,owner_id=owner.id,world_id="config-world-a",world_character_id="config-role-a",purpose="image") is None
        changed=deepcopy(old);changed["profiles"]["comfyui:workflow"]["options"]["base_url"]="http://192.168.0.4:8188"
        with pytest.raises(ImagePreparationError,match="https_required"):
            image_policy.write(service,**scope,data=WorldImagePolicyPatch(expected_revision=revision,generation_settings=changed))
        assert db.get(WorldImagePolicy,"config-role-a").revision==revision
        # Same inactive legacy profile survives an unrelated limit/OFF save.
        image_policy.write(service,**scope,data=WorldImagePolicyPatch(expected_revision=revision,generation_enabled=False,generation_limit=3,generation_settings=old))
        assert not db.get(WorldImagePolicy,"config-role-a").generation_enabled
    engine.dispose()


def test_selecting_an_old_unsafe_character_profile_is_activation_but_key_withdrawal_is_safe(tmp_path):
    sessions,media,_=configured(tmp_path,"comfyui","workflow")
    unsafe=ComfyOptions(base_url="http://old.example.test",partner_auth=True,workflow=WORKFLOW).model_dump(exclude_none=True)
    with sessions() as db:
        row=db.get(AgentImageGenerationSetting,CHARACTER)
        row.generation_provider="nanogpt";row.generation_model="krea-v2/turbo";row.generation_auto_enabled=False
        row.generation_profiles_json=json.dumps({"comfyui:workflow:":{"active":True,"options":unsafe,"connection":None,"reference_enabled":False,"reference_initialized":True}})
        db.commit();owner=db.get(User,OWNER)
        command=GenerationSettingsWrite(expected_revision=row.generation_revision,provider="comfyui",model="workflow",options=unsafe,auto_enabled=False,daily_limit=4,reference_enabled=False)
        with pytest.raises(ImagePreparationError,match="https_required"):media.write_generation(db,owner,CHARACTER,command)
        db.rollback()
        # A contradictory clear + replacement key cannot use the withdrawal path.
        with pytest.raises(ImagePreparationError,match="https_required"):
            media.write_generation(db,owner,CHARACTER,command.model_copy(update={"clear_partner_api_key":True,"partner_api_key":SecretStr("synthetic-new-key")}))
        db.rollback()
        media.write_generation(db,owner,CHARACTER,command.model_copy(update={"clear_partner_api_key":True}))
        db.commit();assert not media.read_generation(db,owner,CHARACTER)["has_partner_api_key"]


def test_comfy_reference_from_another_owned_character_is_rejected_without_attachment(tmp_path):
    from app.domains.characters.models import Character
    from app.domains.media.contracts import InvalidProfileMediaError
    from image_integration.test_providers import png
    sessions,media,_=configured(tmp_path,"comfyui","workflow")
    with sessions() as db:
        other=Character(id="comfy-other-scope",owner_id=OWNER,name="Other",handle="comfy_other_scope",one_liner="fixture",
            personality="fixture",speech_style="fixture",worldview="fixture",topic_preferences="fixture",safety_rules="safe",status="inactive",moderation_status="active",execution_mode="llm",persona_summary="fixture")
        db.add(other);db.flush()
        asset=media.assets.upload(db,owner_id=OWNER,scope_kind="character",scope_id=other.id,content_type="image/png",content=png(),draft=True)
        asset_id=asset.id;db.commit();owner=db.get(User,OWNER);before=media.read_generation(db,owner,CHARACTER)
        command=GenerationSettingsWrite(expected_revision=before["revision"],provider="comfyui",model="workflow",daily_limit=4,
            options=before["active_profile"]["options"],reference_enabled=False,reference_asset_id=asset_id)
        with pytest.raises(InvalidProfileMediaError):media.write_generation(db,owner,CHARACTER,command)
        db.rollback();assert media.read_generation(db,owner,CHARACTER)==before
        assert media.assets.owned(db,owner_id=OWNER,asset_id=asset_id).state=="draft"


@pytest.fixture
def tls_server(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    subject=x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME,"fixture.invalid")])
    cert=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(datetime.now(UTC)-timedelta(minutes=1)).not_valid_after(datetime.now(UTC)+timedelta(hours=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName("fixture.invalid")]),False).sign(key,hashes.SHA256())
    certfile=tmp_path/"fixture.pem";keyfile=tmp_path/"fixture-key.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM));keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path);self.send_response(307);self.send_header("Location","http://127.0.0.1:1/forbidden-downgrade");self.end_headers()
        def log_message(self,*args):pass
    server=HTTPServer(("127.0.0.1",0),Handler);context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile,keyfile)
    server.socket=context.wrap_socket(server.socket,server_side=True)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:yield server.server_port,certfile,calls
    finally:server.shutdown();server.server_close();worker.join(2)


def test_tls_untrusted_certificate_and_wrong_hostname_never_send_body(tls_server):
    port,certificate,calls=tls_server
    async def run():
        with pytest.raises(ImageSubmissionError,match="transport_error"):
            await ImageHttp().request("POST",f"https://127.0.0.1:{port}/prompt",content=b"synthetic-key-body")
        context=ssl.create_default_context(cafile=str(certificate))
        async with httpx.AsyncClient(verify=context,trust_env=False) as client:
            with pytest.raises(ImageSubmissionError,match="transport_error"):
                await ImageHttp(client).request("POST",f"https://127.0.0.1:{port}/prompt",content=b"synthetic-key-body")
    asyncio.run(run());assert calls==[]


def test_injected_follow_redirects_client_is_still_not_followed():
    seen=[]
    def respond(request):
        seen.append(str(request.url));return httpx.Response(307,headers={"Location":"http://other.test/prompt"})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond),follow_redirects=True) as client:
            response=await ImageHttp(client).request("POST","https://trusted.test/prompt",content=b"synthetic-only",error_body_limit=1024)
            assert response.status_code==307
    asyncio.run(run());assert seen==["https://trusted.test/prompt"]
