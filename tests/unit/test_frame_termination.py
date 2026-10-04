"""Frame termination is per **line**, and reads are bounded (`protocol.md` §2.2; R5-2).

``_recv_until_end`` used to break as soon as the *substring* ``b"END\\n"``
appeared anywhere in the buffer, so a payload line ending in ``END`` cut the
frame short: everything after it was dropped while the status line still read
``OK``.  The driver here is a scripted fake socket, so the chunk boundary that
exposes the defect is deterministic -- a real ``socketpair`` lets the OS coalesce
the writes and hides it.
"""

from __future__ import annotations

import unittest

from ctl import client
from ctl.errors import CtlError


class _ScriptedSocket:
    """A socket stand-in whose ``recv`` returns fixed chunks, then EOF."""

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.reads = 0

    def recv(self, n):
        self.reads += 1
        return self.chunks.pop(0) if self.chunks else b""


class _EndlessSocket:
    """Returns the same chunk forever; fails loudly if the loop never stops."""

    def __init__(self, chunk, ceiling=1000):
        self.chunk = chunk
        self.calls = 0
        self.ceiling = ceiling

    def recv(self, n):
        self.calls += 1
        if self.calls > self.ceiling:
            raise AssertionError("receive loop never stopped; buffer is unbounded")
        return self.chunk


class FrameTerminationTest(unittest.TestCase):
    def test_payload_line_ending_in_end_is_kept(self):
        # The decoy b"END\n" is 16 bytes into the stream; the first chunk ends
        # exactly at the payload line "  build END", so the old substring test
        # broke here and returned only that first chunk.
        stream = [b"OK fine\n  build END\n", b"  more payload\nEND\n"]
        raw = client._recv_until_end(_ScriptedSocket(stream), 1.0)
        self.assertEqual(raw, b"OK fine\n  build END\n  more payload\nEND\n")
        self.assertIn(b"more payload", raw)
        self.assertTrue(raw.endswith(b"\nEND\n"))

    def test_a_payload_end_never_ends_the_frame(self):
        # One chunk, two decoy END lines in the body, one real terminator.
        raw = client._recv_until_end(
            _ScriptedSocket([b"OK\nline END\nlast END\nEND\n"]), 1.0)
        self.assertEqual(raw, b"OK\nline END\nlast END\nEND\n")

    def test_lone_end_line_still_terminates_the_frame(self):
        sock = _ScriptedSocket([b"OK\n", b"payload\n", b"END\n", b"trailing junk\n"])
        raw = client._recv_until_end(sock, 1.0)
        self.assertEqual(raw, b"OK\npayload\nEND\n")
        self.assertEqual(client.Response(raw.decode("utf-8")).payload, ["payload"])

    def test_reads_stop_at_the_frame_cap(self):
        # A peer that never writes END must not grow the buffer without bound.
        chunk = b"x" * client._RECV_CHUNK + b"\n"
        sock = _EndlessSocket(chunk)
        raw = client._recv_until_end(sock, 1.0)
        self.assertLessEqual(len(raw), client.MAX_FRAME_BYTES + len(chunk))

    def test_oversized_request_is_refused_before_connecting(self):
        # No port/run_id: if the cap were checked after connect this would raise
        # an "unhandled cannot reach bridge" instead of the cap error.
        big = "x" * (client.MAX_REQUEST_BYTES + 1)
        with self.assertRaises(CtlError) as caught:
            client.talk(big)
        self.assertEqual(caught.exception.code, "badrequest")
        self.assertIn("request cap", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
