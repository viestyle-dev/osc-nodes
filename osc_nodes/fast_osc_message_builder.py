import struct
from typing import Sequence


def build_osc_string(s: str) -> bytes:
    """Build OSC string (null-terminated and 4-byte aligned)"""
    s_bytes = s.encode("utf-8") + b"\x00"
    padding = (4 - len(s_bytes) % 4) % 4
    return s_bytes + (b"\x00" * padding)


def build_osc_int(i: int) -> bytes:
    """Build OSC int32"""
    return struct.pack(">i", i)


def build_osc_float(f: float) -> bytes:
    """Build OSC float32"""
    return struct.pack(">f", f)


def build_osc_double(d: float) -> bytes:
    """Build OSC double"""
    return struct.pack(">d", d)


def build_osc_int64(i: int) -> bytes:
    """Build OSC int64 (h type tag)"""
    return struct.pack(">q", i)


def build_osc_blob(b: bytes) -> bytes:
    """Build OSC blob"""
    size = len(b)
    size_bytes = struct.pack(">i", size)
    # Add padding to make total length multiple of 4
    padding = (4 - len(b) % 4) % 4
    return size_bytes + b + (b"\x00" * padding)


def build_osc_rgba(rgba: int | tuple[int, int, int, int]) -> bytes:
    """Build OSC RGBA color as 32-bit unsigned integer

    Args:
        rgba: Either a tuple of (r, g, b, a) with values 0-255,
              or a single 32-bit integer
    """
    if isinstance(rgba, tuple):
        r, g, b, a = rgba
        rgba_val = (
            ((r & 0xFF) << 24) | ((g & 0xFF) << 16) | ((b & 0xFF) << 8) | (a & 0xFF)
        )
    else:
        rgba_val = rgba
    return struct.pack(">I", rgba_val)


def build_osc_midi(midi: tuple | int) -> bytes:
    """Build OSC MIDI message as 32-bit unsigned integer

    Args:
        midi: Either a tuple of (port, status, data1, data2) with values 0-255,
              or a single 32-bit integer
    """
    if isinstance(midi, tuple):
        port, status, data1, data2 = midi
        midi_val = (
            ((port & 0xFF) << 24)
            | ((status & 0xFF) << 16)
            | ((data1 & 0xFF) << 8)
            | (data2 & 0xFF)
        )
    else:
        midi_val = midi
    return struct.pack(">I", midi_val)


def build_osc_timetag(seconds: int, fractional: int = 0) -> bytes:
    """Build OSC time tag (64-bit NTP timestamp)"""
    return struct.pack(">II", seconds, fractional)


def build_osc_message(address: str, args: Sequence[tuple[str, bytes | None]]):
    """Build OSC message directly from type tag and value pairs

    Args:
        address: OSC address pattern
        args: List of (type_tag, value) tuples where:
            - type_tag: Single character OSC type tag ('i', 'f', 'd', 'h', 's', 'b', 'T', 'F', etc.)
            - value: Bytes representation of the value, or None for types without data (T, F, N, I)

    Returns:
        Complete OSC message as bytes
    """
    msg = bytearray()
    # Start with address
    msg += build_osc_string(address)

    # Build type tag string from args
    type_tags = "".join(tag for tag, _ in args)

    # Add type tag string (with leading comma)
    msg += build_osc_string("," + type_tags)

    # Add arguments based on type tags
    in_array = False

    for tag, value in args:
        if tag == "i":
            if not isinstance(value, bytes):
                raise ValueError(f"Expected bytes for type tag 'i', got {type(value)}")
            if len(value) != 4:
                raise ValueError(
                    f"Expected 4 bytes for type tag 'i', got {len(value)} bytes"
                )
            msg += value
        elif tag == "f":
            # 32-bit float
            if not isinstance(value, bytes):
                raise ValueError(f"Expected float for type tag 'f', got {type(value)}")
            if len(value) != 4:
                raise ValueError(
                    f"Expected 4 bytes for type tag 'f', got {len(value)} bytes"
                )
            msg += value
        elif tag == "d":
            # 64-bit double
            if not isinstance(value, bytes):
                raise ValueError(f"Expected bytes for type tag 'd', got {type(value)}")
            if len(value) != 8:
                raise ValueError(
                    f"Expected 8 bytes for type tag 'd', got {len(value)} bytes"
                )
            msg += value
        elif tag == "h":
            # 64-bit integer
            if not isinstance(value, bytes):
                raise ValueError(f"Expected bytes for type tag 'h', got {type(value)}")
            if len(value) != 8:
                raise ValueError(
                    f"Expected 8 bytes for type tag 'h', got {len(value)} bytes"
                )
            msg += value
        elif tag == "s":
            # String (already in OSC format)
            if not isinstance(value, bytes):
                raise ValueError(f"Expected bytes for type tag 's', got {type(value)}")
            msg += value
        elif tag == "b":
            # Blob (already in OSC format with size prefix)
            if not isinstance(value, bytes):
                raise ValueError(f"Expected bytes for type tag 'b', got {type(value)}")
            msg += value
        elif tag == "r":
            # RGBA color (4-byte color value)
            if not isinstance(value, bytes):
                raise ValueError(f"Expected bytes for type tag 'r', got {type(value)}")
            if len(value) != 4:
                raise ValueError(
                    f"Expected 4 bytes for type tag 'r', got {len(value)} bytes"
                )
            msg += value
        elif tag == "m":
            # MIDI message (4-byte MIDI value)
            if not isinstance(value, bytes):
                raise ValueError(f"Expected bytes for type tag 'm', got {type(value)}")
            if len(value) != 4:
                raise ValueError(
                    f"Expected 4 bytes for type tag 'm', got {len(value)} bytes"
                )
            msg += value
        elif tag == "t":
            # Time tag (8-byte NTP timestamp)
            if not isinstance(value, bytes):
                raise ValueError(f"Expected bytes for type tag 't', got {type(value)}")
            if len(value) != 8:
                raise ValueError(
                    f"Expected 8 bytes for type tag 't', got {len(value)} bytes"
                )
            msg += value
        elif tag in ("T", "F"):
            # Boolean True/False - no data, just type tag
            pass
        elif tag == "N":
            # Nil - no data
            pass
        elif tag == "I":
            # Impulse/Bang - no data
            pass
        elif tag == "[":
            # Array start marker - no data
            in_array = True
        elif tag == "]":
            # Array end marker - no data
            in_array = False
        else:
            # Unknown type
            raise ValueError(f"Unknown OSC type tag: {tag}")

    return msg


def build_osc_bundle(messages: list[bytes | bytearray], timestamp: int = 1):
    """Build OSC bundle from list of message bytes

    Args:
        messages: List of OSC message bytes
        timestamp: OSC timestamp (1 = immediately)

    Returns:
        Complete OSC bundle as bytes
    """
    bundle = bytearray(b"#bundle\x00")
    bundle.extend(struct.pack(">Q", timestamp))

    for msg in messages:
        bundle.extend(struct.pack(">i", len(msg)))
        bundle.extend(msg)

    return bundle
