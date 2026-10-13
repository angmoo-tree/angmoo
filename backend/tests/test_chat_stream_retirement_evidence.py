"""A source proof cannot replace the stream's HTTP/auth/dependency frame."""
import ast
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "stream_retirement", Path(__file__).resolve().parents[2] / "scripts/ci/chat_forwarder_retirement.py"
)
retirement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retirement)

SOURCE = "backend/app/domains/chat/router/world_chat_response.py"
BEFORE = '''
@router.get('/worlds/{world_id}/events')
def stream_world_response_events(world_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    return stream(world_id, user, db)
def neighbor():
    return 'preserved'
'''
AFTER = BEFORE.replace('return stream(world_id, user, db)', 'return guarded_stream(world_id, user, db)')


def test_stream_delta_needs_exact_committed_body_and_keeps_other_bindings():
    before, after = (ast.parse(text).body[0] for text in (BEFORE, AFTER))
    def matches(path, symbol, old, new):
        return (path == SOURCE and symbol == 'stream_world_response_events'
                and retirement.dump(old) == retirement.dump(before)
                and retirement.dump(new) == retirement.dump(after))
    retirement.validate_world_stream_product_change(SOURCE, BEFORE, AFTER, matches)
    with pytest.raises(ValueError, match='committed body'):
        retirement.validate_world_stream_product_change(SOURCE, BEFORE, AFTER, lambda *args: False)
    with pytest.raises(ValueError, match='frame or committed body'):
        retirement.validate_world_stream_product_change(SOURCE, BEFORE, AFTER.replace('guarded_stream', 'unrecorded_stream'), matches)
    with pytest.raises(ValueError, match='frame or committed body'):
        retirement.validate_world_stream_product_change(SOURCE, BEFORE, AFTER.replace("'preserved'", "'changed'"), matches)


@pytest.mark.parametrize('change', ['get_current_user', 'get_db', 'world_id: str', '/worlds/{world_id}/events'])
def test_even_an_approved_body_cannot_change_auth_arguments_or_route(change):
    tampered = AFTER.replace(change, change + '_changed')
    with pytest.raises(ValueError, match='frame or committed body'):
        retirement.validate_world_stream_product_change(SOURCE, BEFORE, tampered, lambda *args: True)
