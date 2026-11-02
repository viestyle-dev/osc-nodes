import logging
import threading
import asyncio
import struct

from pythonosc import udp_client
import numpy as np

from nonoha_core.data_type import (
    DataType,
    PortValueType,
    PropertyDataType,
    name_to_port_value_type,
)
from nonoha_core.port import (
    PortValue,
    StaticTypeInputPort,
    StaticTypeOutputPort,
)
from nonoha_core.node import BaseNode, NodeDoc, replace_node_input_port, replace_node_output_port

from .osc_server_registry import OscServerRegistry, SharedOscServer
from . import fast_osc_message_builder

logger = logging.getLogger(__name__)


class OscUdpSendBlobNode(BaseNode):
    @classmethod
    def describe(cls, properties=None):
        return NodeDoc(
            description="Send array data as OSC blob over UDP",
            category="OSC",
            inputs={"in": "Array data to send as blob"},
            outputs={},
        )

    PROPERTIES = {
        "ip": {"description": "Destination IP address", "data_type": "str", "default_value": ""},
        "port": {"description": "Destination UDP port", "data_type": "i32", "default_value": 5000},
        "address": {"description": "OSC address pattern", "data_type": "str", "default_value": "/series"},
        "value_type": {"description": "Data type (e.g. u32, f32, i16)", "data_type": "str", "default_value": "u32"},
    }

    def __init__(self, name: str):
        super().__init__(name, "OscUdpSendBlob")

        value_type = PortValueType(DataType.Uint32)
        input_in = StaticTypeInputPort("in", [value_type])
        input_in.subscribe(id(self), self._on_input_in)

        self._ip: str | None = None
        self._port: int = 5000
        self._client: udp_client.UDPClient | None = None
        self._address = "/series"
        self._input_in = input_in
        self._value_type = value_type

        self.inputs[input_in.name] = input_in

    def set_properties(self, properties: dict[str, PropertyDataType]):
        ip = self._ip
        if "ip" in properties:
            ip = str(properties["ip"])

        port = self._port
        if "port" in properties:
            port = int(properties["port"])

        address = self._address
        if "address" in properties:
            address = str(properties["address"])

        value_type = self._value_type
        if "value_type" in properties:
            value_type_str = str(properties["value_type"])
            if not isinstance(value_type_str, str):
                raise ValueError("value_type must be a string")

            value_type = name_to_port_value_type(value_type_str)
            if value_type.shape != ():
                raise ValueError("value_type must be a scalar type")

        new_input_in = self._input_in
        if value_type != self._value_type:
            new_input_in = StaticTypeInputPort("in", [value_type])

        if new_input_in != self._input_in:
            replace_node_input_port(
                self, self._input_in, new_input_in, self._on_input_in
            )
            self._input_in = new_input_in

        new_client = self._client
        if ip != self._ip or port != self._port:
            if ip and port:
                new_client = udp_client.UDPClient(ip, port)
            else:
                new_client = None

        self._ip = ip
        self._port = port
        self._client = new_client
        self._address = address
        self._value_type = value_type

        self.properties["ip"] = ip if ip else ""
        self.properties["port"] = port
        self.properties["address"] = self._address
        self.properties["value_type"] = self._value_type.name

        if self.parent_graph is not None:
            self.parent_graph.notify_node_updated(self)

    def _on_input_in(self, values: list[PortValue]):
        if self._client is None:
            return

        value_array = values[0]
        address = self._address

        try:
            # Convert according to the data type and send as a blob
            match self._value_type.data_type:
                case DataType.Uint8:
                    typed_array = value_array.astype(">u1")  # '>u1' = big-endian uint8
                case DataType.Uint16:
                    typed_array = value_array.astype(">u2")  # '>u2' = big-endian uint16
                case DataType.Uint32:
                    typed_array = value_array.astype(">u4")  # '>u4' = big-endian uint32
                case DataType.Uint64:
                    typed_array = value_array.astype(">u8")  # '>u8' = big-endian uint64
                case DataType.Int8:
                    typed_array = value_array.astype(">i1")  # '>i1' = big-endian int8
                case DataType.Int16:
                    typed_array = value_array.astype(">i2")  # '>i2' = big-endian int16
                case DataType.Int32:
                    typed_array = value_array.astype(">i4")  # '>i4' = big-endian int32
                case DataType.Int64:
                    typed_array = value_array.astype(">i8")  # '>i8' = big-endian int64
                case DataType.Float32:
                    typed_array = value_array.astype(
                        ">f4"
                    )  # '>f4' = big-endian float32
                case DataType.Float64:
                    typed_array = value_array.astype(
                        ">f8"
                    )  # '>f8' = big-endian float64
                case DataType.Bool:
                    typed_array = value_array.astype("?")  # '?' = bool (1 byte)
                case _:
                    logger.warning(
                        f"Unsupported data type: {self._value_type.data_type}"
                    )
                    return

            # Convert to bytes
            blob_data = typed_array.tobytes()

            # Build OSC blob using fast_osc_message_builder
            blob_bytes = fast_osc_message_builder.build_osc_blob(blob_data)

            # Build message using fast_osc_message_builder
            args = [("b", blob_bytes)]
            msg_bytes = fast_osc_message_builder.build_osc_message(address, args)

            # Send message directly as bytes
            self._client._sock.sendto(
                msg_bytes, (self._client._address, self._client._port)
            )

            # logger.info(
            #     f"Sent {len(typed_array)} {self._value_type.data_type} values as blob ({len(blob_data)} bytes)"
            # )

        except Exception as e:
            logger.error(f"Failed to send OSC message: {e}")


class OscUdpReceiveBlobNode(BaseNode):
    """OSC UDP Receiver Node that receives blob data and outputs as array"""

    @classmethod
    def describe(cls, properties=None):
        return NodeDoc(
            description="Receive OSC blob data and output as array",
            category="OSC",
            inputs={},
            outputs={"out": "Received blob data as array"},
        )

    PROPERTIES = {
        "port": {"description": "Listen UDP port", "data_type": "str", "default_value": ""},
        "address": {"description": "OSC address pattern", "data_type": "str", "default_value": "/series"},
        "value_type": {"description": "Data type (e.g. i16, f32)", "data_type": "str", "default_value": "i16"},
    }

    def __init__(self, name: str, server_registry: OscServerRegistry):
        super().__init__(name, "OscUdpReceiveBlob")

        value_type = PortValueType(DataType.Int16)
        output_out = StaticTypeOutputPort("out", [value_type])

        self._port: int | None = None
        self._address: str | None = "/series"
        self._value_type = value_type
        self._output_out = output_out
        self._server_registry = server_registry
        self._callback_id = id(self)
        self._main_loop: asyncio.AbstractEventLoop | None = None

        self.outputs[output_out.name] = output_out

    def activate(self):
        self._main_loop = asyncio.get_running_loop()
        self._subscribe(self._port, self._address)

    def finalize(self):
        self._unsubscribe(self._port)

    def _subscribe(self, port: int | None, address: str | None):
        """Subscribe to OSC messages via the registry"""
        if port is None or address is None or self._main_loop is None:
            return
        server = self._server_registry.get_server(port)
        server.subscribe(address, self._callback_id, self._handle_osc_messages)

    def _unsubscribe(self, port: int | None):
        """Unsubscribe from OSC messages"""

        if port is None:
            return

        server = self._server_registry.get_server(port)
        server.unsubscribe(self._callback_id)

    def _handle_osc_messages(self, messages: list[tuple[str, list]]):
        """Handle batched OSC messages containing blob data"""
        # Process all blob messages and dispatch once

        # Extract and convert all valid blob data
        arrays = []
        for _, args in messages:
            if args and isinstance(args[0], bytes):
                array_data = self._blob_to_array(args[0])
                if array_data is not None:
                    arrays.append(array_data)

        if not arrays:
            return

        # Concatenate all arrays if multiple blobs received
        if len(arrays) == 1:
            output = arrays[0]
        else:
            output = np.concatenate(arrays)

        # Single dispatch for all data
        assert self._main_loop is not None
        self._main_loop.call_soon_threadsafe(self._output_out.dispatch, [output])

    def _blob_to_array(self, blob_data: bytes):
        """Convert blob bytes to numpy array based on value type"""
        try:
            # Determine numpy dtype based on value type
            match self._value_type.data_type:
                case DataType.Uint8:
                    dtype = ">u1"  # big-endian uint8
                    bytes_per_value = 1
                case DataType.Uint16:
                    dtype = ">u2"  # big-endian uint16
                    bytes_per_value = 2
                case DataType.Uint32:
                    dtype = ">u4"  # big-endian uint32
                    bytes_per_value = 4
                case DataType.Uint64:
                    dtype = ">u8"  # big-endian uint64
                    bytes_per_value = 8
                case DataType.Int8:
                    dtype = ">i1"  # big-endian int8
                    bytes_per_value = 1
                case DataType.Int16:
                    dtype = ">i2"  # big-endian int16
                    bytes_per_value = 2
                case DataType.Int32:
                    dtype = ">i4"  # big-endian int32
                    bytes_per_value = 4
                case DataType.Int64:
                    dtype = ">i8"  # big-endian int64
                    bytes_per_value = 8
                case DataType.Float32:
                    dtype = ">f4"  # big-endian float32
                    bytes_per_value = 4
                case DataType.Float64:
                    dtype = ">f8"  # big-endian float64
                    bytes_per_value = 8
                case _:
                    logger.warning(
                        f"Unsupported data type: {self._value_type.data_type}"
                    )
                    return None

            # Check if blob size is valid
            if len(blob_data) % bytes_per_value != 0:
                logger.warning(
                    f"Blob size {len(blob_data)} not divisible by {bytes_per_value}"
                )
                return None

            # Convert blob to numpy array
            array = np.frombuffer(blob_data, dtype=dtype)

            # Convert to native byte order for processing
            array = array.astype(array.dtype.newbyteorder("="))

            return array

        except Exception as e:
            logger.error(f"Failed to convert blob to array: {e}")
            return None

    def set_properties(self, properties: dict[str, PropertyDataType]):
        port = self._port
        if "port" in properties:
            port_value = properties["port"]
            if port_value == "" or port_value is None:
                port = None
            else:
                port = int(port_value)

        address = self._address
        if "address" in properties:
            address = str(properties["address"])
            if address == "":
                address = None

        value_type = self._value_type
        if "value_type" in properties:
            value_type_str = str(properties["value_type"])
            if not isinstance(value_type_str, str):
                raise ValueError("value_type must be a string")

            value_type = name_to_port_value_type(value_type_str)
            if value_type.shape != ():
                raise ValueError("value_type must be a scalar type")

        # Check if we need to update output port
        new_output_out = self._output_out
        if value_type != self._value_type:
            new_output_out = StaticTypeOutputPort("out", [value_type])

        if new_output_out != self._output_out:
            replace_node_output_port(self, self._output_out, new_output_out)
            self._output_out = new_output_out

        # Re-subscribe if port or address changed
        if port != self._port or address != self._address:
            self._unsubscribe(self._port)  # Unsubscribe from old port/address
            self._port = port
            self._address = address
            self._subscribe(self._port, self._address)  # Subscribe to new port/address

        self._port = port
        self._address = address
        self._value_type = value_type

        self.properties["port"] = port if port else ""
        self.properties["address"] = address if address else ""
        self.properties["value_type"] = value_type.name

        if self.parent_graph is not None:
            self.parent_graph.notify_node_updated(self)


def make_factory_osc_udp_receive_blob_node(server_registry: OscServerRegistry):
    def factory(name: str) -> OscUdpReceiveBlobNode:
        return OscUdpReceiveBlobNode(name, server_registry)

    return factory


class OscUdpSendValuesNode(BaseNode):
    @classmethod
    def describe(cls, properties=None):
        return NodeDoc(
            description="Send multiple typed values as OSC bundle over UDP",
            category="OSC",
            inputs={"values": "Typed values to send"},
            outputs={},
        )

    PROPERTIES = {
        "ip": {"description": "Destination IP address", "data_type": "str", "default_value": ""},
        "port": {"description": "Destination UDP port", "data_type": "i32", "default_value": 5000},
        "address": {"description": "OSC address pattern", "data_type": "str", "default_value": "/values"},
        "value_type_list": {"description": "Comma-separated type list (e.g. i32,f32)", "data_type": "str", "default_value": "i32,f32"},
    }

    def __init__(self, name: str):
        super().__init__(name, "OscUdpSendValues")

        value_type_list = [
            PortValueType(DataType.Int32),
            PortValueType(DataType.Float32),
        ]
        input_values = StaticTypeInputPort("values", value_type_list)
        input_values.subscribe(id(self), self._on_input_values)

        self._ip: str | None = None
        self._port: int = 5000
        self._client: udp_client.UDPClient | None = None
        self._address = "/values"
        self._input_values = input_values
        self._value_type_list = value_type_list
        self._osc_type_tags = self._get_osc_type_tags(value_type_list)

        self.inputs[input_values.name] = input_values

    def _get_osc_type_tags(self, value_type_list: list[PortValueType]):
        """Get OSC type tag characters for the given value types."""
        type_tags = []
        for value_type in value_type_list:
            match value_type.data_type:
                # Integer types
                case DataType.Int8 | DataType.Int16 | DataType.Int32:
                    type_tags.append("i")  # 32-bit int
                case DataType.Uint8 | DataType.Uint16 | DataType.Uint32:
                    type_tags.append("i")  # 32-bit int
                case DataType.Int64 | DataType.Uint64:
                    type_tags.append("h")  # 64-bit int

                # Float types
                case DataType.Float32:
                    type_tags.append("f")  # 32-bit float
                case DataType.Float64:
                    type_tags.append("d")  # 64-bit double

                # Boolean type (will be determined at runtime)
                case DataType.Bool:
                    type_tags.append("T")  # Placeholder for T/F

                case _:
                    raise ValueError(f"Unsupported data type: {value_type.data_type}")
        return type_tags

    def set_properties(self, properties: dict[str, PropertyDataType]):

        ip = self._ip
        if "ip" in properties:
            ip = str(properties["ip"])

        port = self._port
        if "port" in properties:
            port = int(properties["port"])

        address = self._address
        if "address" in properties:
            address = str(properties["address"])

        value_type_list = self._value_type_list
        if "value_type_list" in properties:
            value_type_list_str = str(properties["value_type_list"])
            if not isinstance(value_type_list_str, str):
                raise ValueError("value_type_list must be a string")

            value_type_list = [
                name_to_port_value_type(name.strip())
                for name in value_type_list_str.split(",")
            ]

            if any(value_type.shape != () for value_type in value_type_list):
                raise ValueError("value_type must be scalar (no shape)")

        new_input_values = self._input_values
        new_osc_type_tags = self._osc_type_tags
        if value_type_list != self._value_type_list:
            new_input_values = StaticTypeInputPort("values", value_type_list)
            new_osc_type_tags = self._get_osc_type_tags(value_type_list)

        if new_input_values != self._input_values:
            replace_node_input_port(
                self, self._input_values, new_input_values, self._on_input_values
            )
            self._input_values = new_input_values

        new_client = self._client
        if ip != self._ip or port != self._port:
            if ip and port:
                new_client = udp_client.UDPClient(ip, port)
            else:
                new_client = None

        self._ip = ip
        self._port = port
        self._client = new_client
        self._address = address
        self._value_type_list = value_type_list
        self._osc_type_tags = new_osc_type_tags

        self.properties["ip"] = ip if ip else ""
        self.properties["port"] = port
        self.properties["address"] = address
        self.properties["value_type_list"] = ",".join(
            (value_type.name for value_type in value_type_list)
        )

        if self.parent_graph is not None:
            self.parent_graph.notify_node_updated(self)

    def _on_input_values(self, values: list[PortValue]):
        if self._client is None:
            return

        # Get the minimum length, excluding arrays of length 1
        non_broadcast_lengths = [len(arr) for arr in values if len(arr) != 1]
        if not non_broadcast_lengths:
            # Use 1 when every array has length 1
            len_min = 1
        else:
            # Get the minimum length among arrays whose length is not 1
            len_min = min(non_broadcast_lengths)
            if any(len_array != len_min for len_array in non_broadcast_lengths):
                logger.warning("length mismatch. truncated min length")

        try:
            # Build bundle directly using fast_osc_message_builder
            messages = []

            for i in range(len_min):
                # Collect args as (type_tag, value) tuples
                args = []

                for arr, type_tag in zip(values, self._osc_type_tags):
                    # Arrays of length 1 are broadcast
                    index = 0 if len(arr) == 1 else i
                    value = arr[index]

                    # Convert value to bytes based on type tag
                    if type_tag == "i":
                        args.append(("i", struct.pack(">i", int(value))))
                    elif type_tag == "h":
                        args.append(("h", struct.pack(">q", int(value))))
                    elif type_tag == "f":
                        args.append(("f", struct.pack(">f", float(value))))
                    elif type_tag == "d":
                        args.append(("d", struct.pack(">d", float(value))))
                    elif type_tag == "T":
                        # Boolean type - no data bytes for T/F tags
                        if value:
                            args.append(("T", None))
                        else:
                            args.append(("F", None))
                    else:
                        logger.error(f"Unsupported type tag: {type_tag}")
                        return

                # Build message using fast_osc_message_builder
                msg_bytes = fast_osc_message_builder.build_osc_message(
                    self._address, args
                )
                messages.append(msg_bytes)

            # Build and send bundle
            bundle_bytes = fast_osc_message_builder.build_osc_bundle(
                messages, 1
            )  # timestamp=1 (immediately)
            self._client._sock.sendto(
                bundle_bytes, (self._client._address, self._client._port)
            )
        except Exception as e:
            logger.error(f"Failed to send OSC message: {e}")


class OscUdpReceiveValuesNode(BaseNode):
    @classmethod
    def describe(cls, properties=None):
        return NodeDoc(
            description="Receive multiple typed values from OSC messages",
            category="OSC",
            inputs={},
            outputs={"out": "Received typed values"},
        )

    PROPERTIES = {
        "port": {"description": "Listen UDP port", "data_type": "str", "default_value": ""},
        "address": {"description": "OSC address pattern", "data_type": "str", "default_value": "/values"},
        "value_type_list": {"description": "Comma-separated type list (e.g. i32,f32)", "data_type": "str", "default_value": "i32,f32"},
    }

    def __init__(self, name: str, server_registry: OscServerRegistry):
        super().__init__(name, "OscUdpReceiveValues")

        value_type_list = [
            PortValueType(DataType.Int32),
            PortValueType(DataType.Float32),
        ]
        output_out = StaticTypeOutputPort("out", value_type_list)

        self._port: int | None = None
        self._address: str | None = "/values"
        self._value_type_list = value_type_list
        self._output_out = output_out
        self._server_registry = server_registry
        self._callback_id = id(self)
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._received_buffer: list[list[PortValue]] = []
        self._buffer_lock = threading.Lock()

        self.outputs[output_out.name] = output_out

    def activate(self):
        self._main_loop = asyncio.get_running_loop()
        self._subscribe(self._port, self._address)

    def finalize(self):
        """Clean up subscriptions when node is destroyed"""
        self._unsubscribe(self._port)

    def _subscribe(self, port: int | None, address: str | None):
        """Subscribe to OSC messages via the registry"""
        if port is None or address is None or self._main_loop is None:
            return
        server = self._server_registry.get_server(port)
        server.subscribe(address, self._callback_id, self._handle_osc_messages)

    def _unsubscribe(self, port: int | None):
        """Unsubscribe from OSC messages"""
        if port is None:
            return
        server = self._server_registry.get_server(port)
        server.unsubscribe(self._callback_id)

    # Class-level dtype mapping (computed once)
    _DTYPE_MAP = {
        DataType.Bool: bool,
        DataType.Int8: np.int8,
        DataType.Int16: np.int16,
        DataType.Int32: np.int32,
        DataType.Int64: np.int64,
        DataType.Uint8: np.uint8,
        DataType.Uint16: np.uint16,
        DataType.Uint32: np.uint32,
        DataType.Uint64: np.uint64,
        DataType.Float32: np.float32,
        DataType.Float64: np.float64,
    }

    def _handle_osc_messages(self, messages: list[tuple[str, list]]):
        """Handle batched incoming OSC messages with multiple values"""
        # Filter valid messages
        expected_len = len(self._value_type_list)
        valid_args = [args for _, args in messages if len(args) == expected_len]

        batch_size = len(valid_args)
        if not batch_size:
            return

        # Pre-allocate and fill arrays in one pass
        batch_arrays: list[PortValue] = []
        for idx, value_type in enumerate(self._value_type_list):
            dtype = self._DTYPE_MAP.get(value_type.data_type)
            if dtype is None:
                logger.error(f"Unsupported type: {value_type.data_type}. Unexpected.")
                return

            # Create array from column of values
            if value_type.data_type == DataType.Bool:
                arr = np.array([bool(args[idx]) for args in valid_args], dtype=dtype)
            else:
                arr = np.array([args[idx] for args in valid_args], dtype=dtype)
            batch_arrays.append(arr)

        # Add to buffer
        with self._buffer_lock:
            self._received_buffer.append(batch_arrays)

        # Schedule dispatch to main event loop
        assert self._main_loop is not None
        self._main_loop.call_soon_threadsafe(self._process_buffer)

    def _process_buffer(self):
        """Process buffered messages and dispatch to output"""
        with self._buffer_lock:
            if not self._received_buffer:
                return

            # The buffer now contains arrays directly
            output_arrays = self._received_buffer

            # Clear buffer
            self._received_buffer = []

        # Dispatch the arrays
        for arrays in output_arrays:
            self._output_out.dispatch(arrays)

        if self.parent_graph is not None:
            self.parent_graph.flush_outputs()

    def set_properties(self, properties: dict[str, PropertyDataType]):
        port = self._port
        if "port" in properties:
            port_value = properties["port"]
            if port_value == "" or port_value is None:
                port = None
            else:
                port = int(port_value)

        address = self._address
        if "address" in properties:
            address = str(properties["address"])
            if address == "":
                address = None

        value_type_list = self._value_type_list
        if "value_type_list" in properties:
            value_type_list_str = str(properties["value_type_list"])
            if not isinstance(value_type_list_str, str):
                raise ValueError("value_type_list must be a string")

            value_type_list = [
                name_to_port_value_type(name.strip())
                for name in value_type_list_str.split(",")
            ]

            if any(value_type.shape != () for value_type in value_type_list):
                raise ValueError("value_type must be scalar (no shape)")

        # Check if we need to update output port
        new_output_out = self._output_out
        if value_type_list != self._value_type_list:
            new_output_out = StaticTypeOutputPort("out", value_type_list)

        if new_output_out != self._output_out:
            replace_node_output_port(self, self._output_out, new_output_out)
            self._output_out = new_output_out

        # Re-subscribe if port or address changed
        if port != self._port or address != self._address:
            self._unsubscribe(self._port)  # Unsubscribe from old port/address
            self._port = port
            self._address = address
            self._subscribe(self._port, self._address)  # Subscribe to new port/address

        self._value_type_list = value_type_list

        self.properties["port"] = port if port else ""
        self.properties["address"] = address if address else ""
        self.properties["value_type_list"] = ",".join(
            (value_type.name for value_type in value_type_list)
        )

        if self.parent_graph is not None:
            self.parent_graph.notify_node_updated(self)


def make_factory_osc_udp_receive_values_node(server_registry: OscServerRegistry):
    """Factory function to create OscUdpReceiveValuesNode instances with server registry"""

    def factory(name: str) -> OscUdpReceiveValuesNode:
        return OscUdpReceiveValuesNode(name, server_registry)

    return factory
