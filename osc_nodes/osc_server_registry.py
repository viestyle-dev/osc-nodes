from typing import Callable, TypeAlias, Optional, List, Any, Generator
import threading
import logging
import re

import pythonosc.dispatcher
from pythonosc import osc_server, osc_bundle, osc_message
from pythonosc.parsing import osc_types

logger = logging.getLogger(__name__)

# (list of (address: str, args: list))
OscMessageCallback: TypeAlias = Callable[[list[tuple[str, list]]], None]

# (
#   list of (timestamp: float, list of (address: str, args: list)),
# )
OscDispatcherCallback: TypeAlias = Callable[
    [list[tuple[float, list[tuple[str, list]]]]], None
]


class OscDispatcher(pythonosc.dispatcher.Dispatcher):
    # Custom dispatcher to handle bundles and messages
    # Based on python-osc' Dispatcher class

    def __init__(self, callback: OscDispatcherCallback):
        super().__init__()
        self._callback = callback

    def _extract_bundle_messages(
        self, bundle: osc_bundle.OscBundle, parent_timestamp: float | None = None
    ) -> List[tuple[float, List[tuple[str, list]]]]:
        """Recursively extract messages from bundle and nested bundles
        Returns: List of (timestamp, [(address, args), ...]) tuples
        """
        result = []
        messages = []
        bundle_timestamp = bundle.timestamp

        # Use parent timestamp if bundle has IMMEDIATELY timestamp
        if parent_timestamp is not None and bundle_timestamp == osc_types.IMMEDIATELY:
            effective_timestamp = parent_timestamp
        else:
            effective_timestamp = bundle_timestamp

        for content in bundle:
            if isinstance(content, osc_message.OscMessage):
                # Direct message in this bundle
                messages.append((content.address, content.params))
            elif isinstance(content, osc_bundle.OscBundle):
                # Recursively process nested bundle
                nested_results = self._extract_bundle_messages(
                    content, effective_timestamp
                )
                result.extend(nested_results)

        # Add messages from this bundle level
        if messages:
            result.append((effective_timestamp, messages))

        return result

    def call_handlers_for_packet(self, data: bytes, client_address=None) -> List[Any]:
        # Reference: call_handlers_for_packet() in python-osc's Dispatcher class

        try:
            # Check if this is a bundle
            if osc_bundle.OscBundle.dgram_is_bundle(data):
                # Parse bundle and recursively extract all messages
                bundle = osc_bundle.OscBundle(data)

                # Extract all messages with their timestamps
                timestamp_messages = self._extract_bundle_messages(bundle)

                # Call the dispatcher callback with all messages
                self._callback(timestamp_messages)
            # Single message - use default handler directly
            elif osc_message.OscMessage.dgram_is_message(data):
                msg = osc_message.OscMessage(data)
                self._callback([(osc_types.IMMEDIATELY, [(msg.address, msg.params)])])

            else:
                logger.warning("Received invalid OSC packet")

        except Exception as e:
            logger.error(f"Error processing OSC packet: {e}")

        return []  # Return empty list for compatibility


class SharedOscServer:
    def __init__(self, port: int):
        self._port = port
        # Address -> list of callbacks (for fast iteration)
        self._callbacks: dict[str, list[OscMessageCallback]] = {}
        # callback_id -> (address, index)
        self._indices: dict[int, tuple[str, int]] = {}
        self._lock = threading.Lock()

        # OSC server components
        self._dispatcher = OscDispatcher(self._handle_messages)
        self._server: Optional[osc_server.ThreadingOSCUDPServer] = None
        self._server_thread: Optional[threading.Thread] = None

        self._start_server()

    def _start_server(self):
        """Start the OSC server"""
        try:
            # Create and start server
            self._server = osc_server.ThreadingOSCUDPServer(
                ("0.0.0.0", self._port), self._dispatcher
            )

            self._server_thread = threading.Thread(
                target=self._server.serve_forever, daemon=True
            )
            self._server_thread.start()

            logger.info(f"Shared OSC server started on port {self._port}")

        except Exception as e:
            logger.error(f"Failed to start shared OSC server on port {self._port}: {e}")
            self._server = None
            raise

    def subscribe(self, address: str, callback_id: int, callback: OscMessageCallback):
        """Subscribe a callback to an address (one address per callback_id)"""
        with self._lock:
            # Remove existing subscription if any (callback_id can only have one address)
            if callback_id in self._indices:
                self.unsubscribe(callback_id)

            # Initialize address list if new
            if address not in self._callbacks:
                self._callbacks[address] = []

            # Add callback to list
            self._callbacks[address].append(callback)
            self._indices[callback_id] = (address, len(self._callbacks[address]) - 1)

    def unsubscribe(self, callback_id: int):
        """Unsubscribe a callback

        Args:
            callback_id: ID of the callback to remove
        """
        with self._lock:
            if callback_id not in self._indices:
                return

            address, index = self._indices[callback_id]
            callbacks = self._callbacks[address]
            last_index = len(callbacks) - 1

            # Swap with last element if not already last
            if index != last_index:
                callbacks[index] = callbacks[last_index]
                # Find and update the moved callback's index
                for cid, (addr, idx) in self._indices.items():
                    if addr == address and idx == last_index:
                        self._indices[cid] = (address, index)
                        break

            # Remove last element
            callbacks.pop()
            del self._indices[callback_id]

            # Clean up if no more callbacks for this address
            if not callbacks:
                del self._callbacks[address]

    def _get_address_pattern(self, address: str):
        escaped_address_pattern = re.escape(address)
        pattern = escaped_address_pattern.replace("\\?", "\\w?")
        # '*' in the OSC Address Pattern matches any sequence of zero or more
        # characters.
        pattern = pattern.replace("\\*", "[\\w|\\+]*")
        # The rest of the syntax in the specification is like the re module so
        # we're fine.
        pattern = f"{pattern}$"
        pattern_compiled = re.compile(pattern)
        return pattern_compiled

    def _handle_messages(
        self, message_groups: list[tuple[float, list[tuple[str, list]]]]
    ):
        """Handle incoming OSC messages (called in server thread)"""

        # key: registered_address
        # value: list of (address, args) tuples
        targeted_addresses: dict[str, list[tuple[str, list]]] = {}

        for timestamp, messages in message_groups:
            # print(f"Timestamp: {timestamp}")
            for address, args in messages:
                pattern = self._get_address_pattern(address)

                with self._lock:
                    for registered_address, callbacks in self._callbacks.items():
                        if pattern.match(registered_address) or (
                            ("*" in registered_address)
                            and re.match(
                                registered_address.replace("*", "[^/]*?/*"), address
                            )
                        ):
                            targeted_addresses.setdefault(
                                registered_address, []
                            ).append((address, args))

        # Dispatch messages
        with self._lock:
            for registered_address, messages in targeted_addresses.items():
                callbacks = self._callbacks.get(registered_address, [])
                for callback in callbacks:
                    callback(messages)

    def shutdown(self):
        if self._server is None:
            return

        self._server.shutdown()
        if self._server_thread:
            self._server_thread.join(timeout=2.0)
        logger.info(f"Shared OSC server on port {self._port} shutdown")


class OscServerRegistry:
    def __init__(self):
        self.servers: dict[int, SharedOscServer] = {}

    def finalize(self):
        for server in self.servers.values():
            server.shutdown()
        self.servers.clear()

    def get_server(self, port: int) -> SharedOscServer:
        """Get or create a server for the specified port"""
        if port not in self.servers:
            self.servers[port] = SharedOscServer(port)
        return self.servers[port]
