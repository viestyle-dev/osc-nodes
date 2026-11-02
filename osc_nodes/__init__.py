import logging
from nonoha_core.node_registry import NodeRegistry
from .osc_nodes import (
    OscUdpSendBlobNode,
    OscUdpSendValuesNode,
    make_factory_osc_udp_receive_blob_node,
    make_factory_osc_udp_receive_values_node,
)

from .osc_server_registry import OscServerRegistry

logger = logging.getLogger(__name__)

_server_registry: OscServerRegistry | None = None


def initialize():
    global _server_registry
    if _server_registry is None:
        _server_registry = OscServerRegistry()

    return _server_registry


def register_nodes(registry: NodeRegistry):
    server_registry = initialize()

    logger.info("osc-nodes plugin loaded")

    registry.register_node("OscUdpSendBlob", OscUdpSendBlobNode)
    registry.register_node(
        "OscUdpReceiveBlob", make_factory_osc_udp_receive_blob_node(server_registry)
    )

    registry.register_node("OscUdpSendValues", OscUdpSendValuesNode)
    registry.register_node(
        "OscUdpReceiveValues", make_factory_osc_udp_receive_values_node(server_registry)
    )


def finalize():
    logger.info("osc-nodes plugin finalized")

    global _server_registry

    if _server_registry is not None:
        _server_registry.finalize()
