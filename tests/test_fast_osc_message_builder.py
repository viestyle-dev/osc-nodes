import struct

from osc_nodes.fast_osc_message_builder import (
    build_osc_string,
    build_osc_int,
    build_osc_float,
    build_osc_double,
    build_osc_int64,
    build_osc_blob,
    build_osc_message,
    build_osc_bundle,
)


class TestBuildOscString:
    def test_basic(self):
        result = build_osc_string("hi")
        # "hi" + null = 3 bytes, padded to 4
        assert result == b"hi\x00\x00"

    def test_empty(self):
        result = build_osc_string("")
        # "" + null = 1 byte, padded to 4
        assert result == b"\x00\x00\x00\x00"

    def test_4byte_aligned(self):
        # "abc" + null = 4 bytes, already aligned
        result = build_osc_string("abc")
        assert result == b"abc\x00"

    def test_5char_needs_padding(self):
        # "hello" + null = 6 bytes, padded to 8
        result = build_osc_string("hello")
        assert result == b"hello\x00\x00\x00"

    def test_length_is_4byte_multiple(self):
        for s in ["", "a", "ab", "abc", "abcd", "abcde", "abcdef", "abcdefg"]:
            result = build_osc_string(s)
            assert len(result) % 4 == 0, f"Failed for {s!r}: len={len(result)}"


class TestBuildOscPrimitives:
    def test_int(self):
        assert build_osc_int(42) == struct.pack(">i", 42)
        assert build_osc_int(-1) == struct.pack(">i", -1)

    def test_float(self):
        assert build_osc_float(1.5) == struct.pack(">f", 1.5)

    def test_double(self):
        assert build_osc_double(3.14) == struct.pack(">d", 3.14)

    def test_int64(self):
        assert build_osc_int64(2**40) == struct.pack(">q", 2**40)


class TestBuildOscBlob:
    def test_basic(self):
        data = b"\x01\x02\x03"
        result = build_osc_blob(data)
        # 4-byte size prefix (3) + 3 data bytes + 1 padding byte = 8
        assert result[:4] == struct.pack(">i", 3)
        assert result[4:7] == data
        assert len(result) % 4 == 0

    def test_empty(self):
        result = build_osc_blob(b"")
        assert result == struct.pack(">i", 0)

    def test_aligned_data(self):
        data = b"\x01\x02\x03\x04"
        result = build_osc_blob(data)
        assert result == struct.pack(">i", 4) + data


class TestBuildOscMessage:
    def test_int_message(self):
        args = [("i", struct.pack(">i", 42))]
        msg = build_osc_message("/test", args)
        # Address + type tag + data
        assert msg[:5] == b"/test"
        assert b",i" in msg
        assert struct.pack(">i", 42) in msg

    def test_float_message(self):
        args = [("f", struct.pack(">f", 1.5))]
        msg = build_osc_message("/value", args)
        assert b",f" in msg
        assert struct.pack(">f", 1.5) in msg

    def test_multi_arg_message(self):
        args = [
            ("i", struct.pack(">i", 10)),
            ("f", struct.pack(">f", 2.5)),
        ]
        msg = build_osc_message("/data", args)
        assert b",if" in msg

    def test_bool_true(self):
        args = [("T", None)]
        msg = build_osc_message("/flag", args)
        assert b",T" in msg

    def test_bool_false(self):
        args = [("F", None)]
        msg = build_osc_message("/flag", args)
        assert b",F" in msg

    def test_message_length_is_4byte_multiple(self):
        args = [("i", struct.pack(">i", 1))]
        msg = build_osc_message("/x", args)
        assert len(msg) % 4 == 0

    def test_blob_message(self):
        blob_data = b"\xAA\xBB"
        blob = build_osc_blob(blob_data)
        args = [("b", blob)]
        msg = build_osc_message("/blob", args)
        assert b",b" in msg


class TestBuildOscBundle:
    def test_basic_bundle(self):
        msg = build_osc_message("/test", [("i", struct.pack(">i", 1))])
        bundle = build_osc_bundle([msg], timestamp=1)
        assert bundle[:8] == b"#bundle\x00"

    def test_bundle_contains_messages(self):
        msg1 = build_osc_message("/a", [("i", struct.pack(">i", 1))])
        msg2 = build_osc_message("/b", [("f", struct.pack(">f", 2.0))])
        bundle = build_osc_bundle([msg1, msg2], timestamp=1)
        # Bundle header (8) + timetag (8) + size(4)+msg1 + size(4)+msg2
        expected_len = 8 + 8 + 4 + len(msg1) + 4 + len(msg2)
        assert len(bundle) == expected_len

    def test_empty_bundle(self):
        bundle = build_osc_bundle([], timestamp=1)
        # Just header + timetag
        assert len(bundle) == 16
        assert bundle[:8] == b"#bundle\x00"
