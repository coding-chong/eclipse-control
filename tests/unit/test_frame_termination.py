"""Frame termination is per **line**, and reads are bounded (`protocol.md` §2.2; R5-2).

``_recv_until_end`` used to break as soon as the *substring* ``b"END\\n"``
appeared anywhere in the buffer, so a payload line ending in ``END`` cut the
frame short: everything after it was dropped while the status line still read
``OK``.  The driver here is a scripted fake socket, so the chunk boundary that
exposes the defect is deterministic -- a real ``socketpair`` lets the OS coalesce
the writes and hides it.

Two follow-ups are pinned here too: a terminator must match the line
*byte-for-byte* (the bridge prefixes every payload line with two spaces, so a
console line whose text is ``END`` arrives as ``  END`` and stays payload), and
a frame that reaches the size ceiling without an ``END`` is refused rather than
returned as a half frame that would read as ``ok=True``.
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

    def test_bridge_prefixed_payload_line_whose_text_is_end_is_kept(self):
        # The bridge prefixes *every* payload line with two spaces
        # (`LiveBridge.java`: ``out.add("  " + ln)``), so a Console line whose
        # content is END arrives as "  END".  A strip()-ing terminator test
        # swallowed it and cut the frame early while the status still read OK.
        stream = [b"OK\n  text lines=3 returned=3 truncated=false\n"
                  b"  build started\n  END\n  build finished\nEND\n"]
        raw = client._recv_until_end(_ScriptedSocket(stream), 1.0)
        self.assertEqual(raw, b"OK\n  text lines=3 returned=3 truncated=false\n"
                              b"  build started\n  END\n  build finished\nEND\n")
        body = client.Response(raw.decode("utf-8")).payload
        self.assertEqual(body, ["  text lines=3 returned=3 truncated=false",
                                "  build started", "  END", "  build finished"])

    def test_crlf_terminator_line_still_ends_the_frame(self):
        # The bridge writes with PrintWriter.println, so on Windows the line is
        # "END\r\n"; only the \r may be dropped, not arbitrary whitespace.
        raw = client._recv_until_end(_ScriptedSocket([b"OK\r\nrow\r\nEND\r\n"]), 1.0)
        self.assertEqual(raw, b"OK\r\nrow\r\nEND\r\n")

    def test_lone_end_line_still_terminates_the_frame(self):
        sock = _ScriptedSocket([b"OK\n", b"payload\n", b"END\n", b"trailing junk\n"])
        raw = client._recv_until_end(sock, 1.0)
        self.assertEqual(raw, b"OK\npayload\nEND\n")
        self.assertEqual(client.Response(raw.decode("utf-8")).payload, ["payload"])

    def test_reads_stop_at_the_frame_cap(self):
        # A peer that never writes END must not grow the buffer without bound,
        # and the half frame must not come back as if it were a frame: a
        # truncated body would read as ok=True with its last line dropped (F7).
        chunk = b"x" * client._RECV_CHUNK + b"\n"
        sock = _EndlessSocket(chunk)
        with self.assertRaises(CtlError) as caught:
            client._recv_until_end(sock, 1.0)
        self.assertEqual(caught.exception.code, "internal")
        self.assertIn("truncated frame", str(caught.exception))

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
