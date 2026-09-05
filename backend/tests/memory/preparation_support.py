"""Real worker composition for preserved direct-service regression call sites."""
from functools import partial
from app.domains.memory.service import batch_preparation, batch_scheduling
from app.runtime.memory.batch_preparation import build_preparation_dependencies

deliver_candidates = partial(batch_preparation.deliver_candidates, dependencies=build_preparation_dependencies())
enqueue_scope = partial(batch_preparation.enqueue_scope, dependencies=build_preparation_dependencies())
rebuild_briefs = partial(batch_preparation.rebuild_briefs, dependencies=build_preparation_dependencies())

schedule_batches = partial(batch_scheduling.schedule_batches, dependencies=build_preparation_dependencies())
