"""New image tests never discover installed credentials or call external hosts."""
import pytest


@pytest.fixture(autouse=True)
def image_network_isolation(deny_external_network):
    yield
