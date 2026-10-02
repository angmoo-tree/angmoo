"""Explicit local suite network boundary; live checks run in another process."""
import pytest


@pytest.fixture(autouse=True)
def offline_suite_network_boundary(deny_external_network):
    yield
