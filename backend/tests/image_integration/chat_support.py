"""Synthetic real Chat service/workflow; all text providers are explicit fakes."""
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker

from chat.test_p8_l_p_evidence_response_streaming import response_session, _workflow, _Router, _Generator
from app.domains.chat.contracts import RetrievalRoute
from app.domains.chat.service.generation import GenerationService
from app.domains.chat.service.settings import MessageSettingsService
from app.domains.chat.service.threads import ThreadService
from app.domains.identity.contracts import CredentialMaterial, CredentialPurpose
from app.domains.identity.models import User
from app.domains.media.service.interpretation import write_interpretation_settings
from app.domains.media.setting_schemas import InterpretationSettingsWrite
from app.domains.social.repository.blocks import world_character_pair_is_blocked
from app.runtime.chat import scope_queries, generation_workflows
from app.runtime.chat.image_attachments import ChatImageAttachments
from app.runtime.media.composition import MediaRuntime


def synthetic_chat(folder, interpreter, *, key="synthetic-only", route=RetrievalRoute.CURRENT_CONTEXT):
    source = response_session.__wrapped__()
    db = next(source)
    sessions = sessionmaker(db.bind)
    media = MediaRuntime(sessions, SimpleNamespace(media_root_path=Path(folder)), interpreter=interpreter)
    with sessions() as setup:
        write_interpretation_settings(setup, "p-owner", InterpretationSettingsWrite(
            expected_revision=0, enabled=True, daily_limit=6, api_key=key))
        setup.commit()
    settings = MessageSettingsService()
    material = CredentialMaterial("synthetic-text", "google", "gemini-3.1-flash-lite", None,
                                  CredentialPurpose.MESSAGE_LLM, "synthetic-text-never-sent")
    settings.resolve_message_credential_material = lambda _db, _user: (None, material)
    threads = ThreadService(settings, scope_queries, world_character_pair_is_blocked)
    events, commands = [], []
    class Router(_Router):
        async def route(self, command, **kwargs):
            events.append("router")
            assert command.image_context
            return await super().route(command, **kwargs)
    class Generator(_Generator):
        async def generate(self, request):
            events.append("crg")
            assert any(item.kind.value == "current_image_analysis" for item in request.evidence.items)
            return await super().generate(request)
    router, generator = Router(route), Generator()
    class Workflows:
        capture_names = staticmethod(lambda *args, **kwargs: {})
        assert_names_current = staticmethod(lambda *args, **kwargs: None)
        today_reader = staticmethod(generation_workflows.today_reader)
        def build(self, session, _material, **kwargs):
            events.append("workflow_build")
            actual = _workflow(session, route, generator, router=router,
                today_snapshot_validator=generation_workflows.SqlAlchemyTodaySnsSnapshotValidator(session, {}))
            class Captured:
                async def run(self, command):
                    commands.append(command)
                    async for event in actual.run(command):
                        yield event
            return SimpleNamespace(workflow=Captured(), character_labels={})
    images = ChatImageAttachments(media)
    generation = GenerationService(threads, settings, Workflows(), images=images)
    return SimpleNamespace(db=db, sessions=sessions, media=media, generation=generation,
        owner=db.get(User, "p-owner"), world_id="p-world", thread_id="p-thread", source=source,
        events=events, commands=commands, router=router, generator=generator)
