"""A slow fresh deletion fence must not stall the async stream loop."""
import asyncio
import threading
from types import SimpleNamespace

from app.domains.chat.router import world_chat_response


def test_scope_check_owns_session_off_loop_and_fences_next_chunk(monkeypatch):
    from app.domains.worlds.service import deletion
    opened=[];closed=[];checks=[];stream_closed=[]
    loop_thread=threading.get_ident()
    class Scope:
        def __enter__(self):
            self.thread=threading.get_ident();opened.append(self.thread)
            assert self.thread != loop_thread
            return self
        def __exit__(self,*args):
            assert threading.get_ident()==self.thread
            closed.append(self.thread)
    def deleting(session,world):
        assert session.thread==threading.get_ident() and world=='world'
        checks.append(world)
        return len(checks)>1
    async def stream(*args,**kwargs):
        try:
            for sequence in (1,2):
                yield SimpleNamespace(protocol_version='v1',request_id='request',request_scope_hash='scope',generation_id='generation',attempt_number=1,sequence=sequence,event_type=SimpleNamespace(value='delta'),payload={'text':'synthetic'})
        finally:stream_closed.append(True)
    monkeypatch.setattr(deletion,'is_deleting',deleting)
    monkeypatch.setattr(world_chat_response.browser_session,'require_local_frontend_request',lambda *a,**kw:None)
    composition=SimpleNamespace(memory_recall_service=None,settings=object(),session_factory=Scope)
    request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime_composition=composition)))
    service=SimpleNamespace(get_world_response_request=lambda *a:SimpleNamespace(state='accepted'),stream_world_response=stream)
    response=world_chat_response.stream_world_response_events('world','thread','request',request,object(),object(),service)
    async def consume():return [chunk async for chunk in response.body_iterator]
    chunks=asyncio.run(consume())
    assert len(chunks)==1  # The second chunk was rechecked and withheld.
    assert len(opened)==len(closed)==2 and stream_closed==[True]
