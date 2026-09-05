"""Execution paths must retain their actual global call dependencies after moves."""

import builtins
import dis
from types import CodeType

import pytest

from app.services import agent_runs


def _required_globals(code):
    for instruction in dis.get_instructions(code):
        if instruction.opname == "LOAD_GLOBAL":
            yield instruction.argval
    for value in code.co_consts:
        if isinstance(value, CodeType):
            yield from _required_globals(value)


@pytest.mark.parametrize(
    "function_name",
    ["run_community_once", "_run_resident_individual_tool_flow", "_run_resident_slot_once"],
)
def test_resident_execution_has_all_global_dependencies(function_name):
    function = getattr(agent_runs, function_name)
    missing = {
        name
        for name in _required_globals(function.__code__)
        if name not in function.__globals__ and not hasattr(builtins, name)
    }
    assert missing == set(), f"{function_name} has unresolved execution dependencies: {sorted(missing)}"
