from types import SimpleNamespace

from app.domains.routines.service import writing_results as agent_writing


def test_writing_composition_stream_params_omit_sampling_parameters() -> None:
    params = agent_writing._writing_stream_params(SimpleNamespace())

    assert params == {}
