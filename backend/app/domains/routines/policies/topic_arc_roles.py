"""Validate the permitted role sequence for independent and feed-seeded arcs."""

from typing import Literal
from app.domains.routines.contracts.topic_arcs import TopicArcStepRole


def _validate_topic_arc_step_roles(
    steps: list[TopicArcStepRole], *, arc_source: Literal["independent", "post_seed"]
) -> None:
    if arc_source == "post_seed":
        if len(steps) < 1 or len(steps) > 3:
            raise ValueError("post_seed topic arc must have 1 to 3 steps")
        if len(steps) == 1:
            if steps[0].role != "standalone":
                raise ValueError("single-step post_seed topic arc must be standalone")
            return
        if steps[0].role != "setup":
            raise ValueError("first post_seed topic arc step must be setup")
        if steps[-1].role != "conclusion":
            raise ValueError("last post_seed topic arc step must be conclusion")
        for step in steps[1:-1]:
            if step.role != "development":
                raise ValueError("middle post_seed topic arc step must be development")
        return
    if len(steps) < 2 or len(steps) > 5:
        raise ValueError("independent topic arc must have 2 to 5 steps")
    if steps[0].role != "setup":
        raise ValueError("first independent topic arc step must be setup")
    if steps[-1].role != "conclusion":
        raise ValueError("last independent topic arc step must be conclusion")
    for step in steps[1:-1]:
        if step.role != "development":
            raise ValueError("middle independent topic arc steps must be development")
