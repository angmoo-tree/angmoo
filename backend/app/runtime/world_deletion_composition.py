"""Compose erasure with the app's existing SQL, media, FTS and graph owners."""
from app.config import settings
from app.database import SessionLocal
from app.runtime.world_deletion.canonical_erasure import ScopedWorldErasure, stop_admission
from app.runtime.world_deletion.worker import WorldDeletionWorker
from app.runtime.world_deletion.http_gate import WorldDeletionHttpGate


def configure_world_deletion(app, composition):
    from app.runtime.world_scope_streams import WorldScopeStreams
    streams = WorldScopeStreams()
    app.state.track_world_stream = streams.track
    app.state.world_deletion_notify = streams.close_world
    sessions = composition.session_factory if composition else SessionLocal
    configuration = composition.settings if composition else settings

    def index_cleanup(identifiers):
        if composition is None:
            raise ValueError("world_erasure_index_unavailable")
        composition.memory_recall_projection.erase_memory_items(identifiers)
        hybrid = composition.memory_hybrid_runtime
        # Canonical deletion is also observed by the existing hybrid owner. Its
        # scoped deletion API acknowledges vector removal before completion.
        hybrid.erase_items(identifiers)

    def graph_cleanup(world_id):
        if composition is None:
            raise ValueError("world_erasure_search_unavailable")
        if not composition.social_search_projection.erase_world(world_id):
            return False
        from app.runtime.graph_projection.process_client import borrow_process_graph_client
        client = borrow_process_graph_client(configuration)
        if client is None:
            from pathlib import Path
            if not configuration.ladybug_database_root.exists():
                return
            from app.runtime.graph_projection.process_client import graph_client_from_settings
            client = graph_client_from_settings(configuration, require_enabled=False)
            try:
                return client.erase_world(world_id)
            finally:
                client.close()
        return client.erase_world(world_id)

    from functools import partial
    from app.runtime.autonomous_activity.checkpoints import erase_activity_checkpoint
    data_root = composition.config.data_paths.root if composition else configuration.media_root_path.parent
    ports = ScopedWorldErasure(configuration.media_root_path, index_cleanup=index_cleanup, graph_cleanup=graph_cleanup,
        checkpoint_cleanup=partial(erase_activity_checkpoint, data_root))
    app.state.world_deletion_stop_admission = stop_admission
    app.state.world_deletion_worker = WorldDeletionWorker(sessions, ports)
    app.add_middleware(WorldDeletionHttpGate, sessions=sessions)
