import pytest

from osc_nodes.osc_server_registry import OscServerRegistry


@pytest.fixture
def server_registry():
    registry = OscServerRegistry()
    yield registry
    registry.finalize()
