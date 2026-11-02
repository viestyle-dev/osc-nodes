import struct

import numpy as np
import pytest

from nonoha_core.data_type import DataType, PortValueType
from nonoha_core.node import NodeDoc

from osc_nodes.osc_nodes import (
    OscUdpSendBlobNode,
    OscUdpReceiveBlobNode,
    OscUdpSendValuesNode,
    OscUdpReceiveValuesNode,
)


# ── OscUdpSendBlobNode ──────────────────────────────────────────────


class TestOscUdpSendBlobNode:
    def test_describe(self):
        doc = OscUdpSendBlobNode.describe()
        assert isinstance(doc, NodeDoc)
        assert doc.category == "OSC"
        assert "in" in doc.inputs

    def test_properties_defaults(self):
        node = OscUdpSendBlobNode("test")
        assert node.properties["ip"] == ""
        assert node.properties["port"] == 5000
        assert node.properties["address"] == "/series"
        assert node.properties["value_type"] == "u32"

    def test_set_properties(self):
        node = OscUdpSendBlobNode("test")
        node.set_properties(
            {"ip": "192.168.1.1", "port": 9000, "address": "/data"}
        )
        assert node._ip == "192.168.1.1"
        assert node._port == 9000
        assert node._address == "/data"
        assert node._client is not None

    def test_value_type_change_replaces_input_port(self):
        node = OscUdpSendBlobNode("test")
        old_port = node.inputs["in"]
        node.set_properties({"value_type": "f32"})
        new_port = node.inputs["in"]
        assert new_port is not old_port
        assert node._value_type == PortValueType(DataType.Float32)

    def test_client_creation(self):
        node = OscUdpSendBlobNode("test")
        assert node._client is None
        node.set_properties({"ip": "127.0.0.1", "port": 5000})
        assert node._client is not None

    def test_client_cleared_when_ip_empty(self):
        node = OscUdpSendBlobNode("test")
        node.set_properties({"ip": "127.0.0.1", "port": 5000})
        assert node._client is not None
        node.set_properties({"ip": ""})
        assert node._client is None

    def test_send_without_client(self):
        """Dispatching without ip/port set should not raise."""
        node = OscUdpSendBlobNode("test")
        input_port = node.inputs["in"]
        input_port.dispatch([np.array([1, 2, 3], dtype=np.uint32)])

    def test_has_property_input_ports(self):
        node = OscUdpSendBlobNode("test")
        assert "@ip" in node.inputs
        assert "@port" in node.inputs
        assert "@address" in node.inputs
        assert "@value_type" in node.inputs


# ── OscUdpReceiveBlobNode ────────────────────────────────────────────


class TestOscUdpReceiveBlobNode:
    def test_describe(self):
        doc = OscUdpReceiveBlobNode.describe()
        assert isinstance(doc, NodeDoc)
        assert doc.category == "OSC"
        assert "out" in doc.outputs

    def test_properties_defaults(self, server_registry):
        node = OscUdpReceiveBlobNode("test", server_registry)
        assert node.properties["port"] == ""
        assert node.properties["address"] == "/series"
        assert node.properties["value_type"] == "i16"

    def test_value_type_change_replaces_output_port(self, server_registry):
        node = OscUdpReceiveBlobNode("test", server_registry)
        old_port = node.outputs["out"]
        node.set_properties({"value_type": "f32"})
        new_port = node.outputs["out"]
        assert new_port is not old_port
        assert node._value_type == PortValueType(DataType.Float32)

    def test_blob_to_array_int16(self, server_registry):
        node = OscUdpReceiveBlobNode("test", server_registry)
        blob = struct.pack(">3h", 100, -200, 300)
        result = node._blob_to_array(blob)
        assert result is not None
        np.testing.assert_array_equal(result, [100, -200, 300])

    def test_blob_to_array_float32(self, server_registry):
        node = OscUdpReceiveBlobNode("test", server_registry)
        node.set_properties({"value_type": "f32"})
        blob = struct.pack(">2f", 1.5, -2.5)
        result = node._blob_to_array(blob)
        assert result is not None
        np.testing.assert_array_almost_equal(result, [1.5, -2.5])

    def test_blob_to_array_invalid_size(self, server_registry):
        node = OscUdpReceiveBlobNode("test", server_registry)
        # Int16 expects 2 bytes per value; 3 bytes is invalid
        result = node._blob_to_array(b"\x00\x01\x02")
        assert result is None

    def test_has_property_input_ports(self, server_registry):
        node = OscUdpReceiveBlobNode("test", server_registry)
        assert "@port" in node.inputs
        assert "@address" in node.inputs
        assert "@value_type" in node.inputs


# ── OscUdpSendValuesNode ────────────────────────────────────────────


class TestOscUdpSendValuesNode:
    def test_describe(self):
        doc = OscUdpSendValuesNode.describe()
        assert isinstance(doc, NodeDoc)
        assert doc.category == "OSC"
        assert "values" in doc.inputs

    def test_properties_defaults(self):
        node = OscUdpSendValuesNode("test")
        assert node.properties["ip"] == ""
        assert node.properties["port"] == 5000
        assert node.properties["address"] == "/values"
        assert node.properties["value_type_list"] == "i32,f32"

    def test_set_properties(self):
        node = OscUdpSendValuesNode("test")
        node.set_properties(
            {"ip": "127.0.0.1", "port": 5000, "address": "/series", "value_type_list": "i32,f32"}
        )
        assert node._ip == "127.0.0.1"
        assert node._address == "/series"

    def test_get_osc_type_tags(self):
        node = OscUdpSendValuesNode("test")
        tags = node._get_osc_type_tags([
            PortValueType(DataType.Int32),
            PortValueType(DataType.Float32),
            PortValueType(DataType.Int64),
            PortValueType(DataType.Float64),
            PortValueType(DataType.Bool),
        ])
        assert tags == ["i", "f", "h", "d", "T"]

    def test_get_osc_type_tags_unsigned(self):
        node = OscUdpSendValuesNode("test")
        tags = node._get_osc_type_tags([
            PortValueType(DataType.Uint8),
            PortValueType(DataType.Uint16),
            PortValueType(DataType.Uint32),
            PortValueType(DataType.Uint64),
        ])
        assert tags == ["i", "i", "i", "h"]

    def test_value_type_list_change_replaces_input_port(self):
        node = OscUdpSendValuesNode("test")
        old_port = node.inputs["values"]
        node.set_properties({"value_type_list": "f64,i64"})
        new_port = node.inputs["values"]
        assert new_port is not old_port

    def test_send_values_dispatch(self):
        """Existing smoke test — dispatching without ip/port should not raise."""
        node = OscUdpSendValuesNode("test")
        node.set_properties(
            {"ip": "127.0.0.1", "port": 5000, "address": "/series", "value_type_list": "i32,f32"}
        )
        input_values = node.inputs["values"]
        input_values.dispatch(
            [
                np.array([1, 2, 3], dtype=np.int32),
                np.array([0.1, 0.2, 0.3], dtype=np.float32),
            ]
        )

    def test_has_property_input_ports(self):
        node = OscUdpSendValuesNode("test")
        assert "@ip" in node.inputs
        assert "@port" in node.inputs
        assert "@address" in node.inputs
        assert "@value_type_list" in node.inputs


# ── OscUdpReceiveValuesNode ──────────────────────────────────────────


class TestOscUdpReceiveValuesNode:
    def test_describe(self):
        doc = OscUdpReceiveValuesNode.describe()
        assert isinstance(doc, NodeDoc)
        assert doc.category == "OSC"
        assert "out" in doc.outputs

    def test_properties_defaults(self, server_registry):
        node = OscUdpReceiveValuesNode("test", server_registry)
        assert node.properties["port"] == ""
        assert node.properties["address"] == "/values"
        assert node.properties["value_type_list"] == "i32,f32"

    def test_value_type_list_change_replaces_output_port(self, server_registry):
        node = OscUdpReceiveValuesNode("test", server_registry)
        old_port = node.outputs["out"]
        node.set_properties({"value_type_list": "f64,i64"})
        new_port = node.outputs["out"]
        assert new_port is not old_port

    def test_has_property_input_ports(self, server_registry):
        node = OscUdpReceiveValuesNode("test", server_registry)
        assert "@port" in node.inputs
        assert "@address" in node.inputs
        assert "@value_type_list" in node.inputs
