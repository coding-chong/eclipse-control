"""`ctl/shadow.py::_capture` -- the promoted-frame announcement (缺口⑤, 2026-10-05).

A failed write action pins its frame (`_promote_reasons`), and before this change
nothing on any channel said so: the frame was filed and the caller was never
pointed at it.  The layer's only output channel is `warn()` -> stderr (its
docstring: "The only channel this layer is allowed to fail on").

Shape contract (`deliverable-shape.md` C10): every expectation below is this
test's **own literal**.  Nothing is read from `_promote_reasons` or any other
constant of the code under test -- otherwise weakening the guard would silently
weaken its guard too.

Falsify: delete the `if reasons:` block in `_capture` and re-run.  The two
"names the frame" tests must go red; `test_a_clean_action_says_nothing` stays
green (it asserts the absence, so it cannot detect a removal).
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import os
import tempfile
import types
import unittest
from unittest import mock

from ctl import shadow


class _Resp:
    """Stand-in for a bridge response -- `_capture` only does attribute reads."""

    def __init__(self, ok, code="", payload=None, raw=""):
        self.ok = ok
        self.code = code
        self.payload = payload or []
        self.raw = raw
        self.status_line = ""


def _capture(ok, code="", payload=None, seeded_rows=(), tmp_bytes=None):
    """Run one `_capture` against a throwaway store; -> (row, captured stderr).

    `_probe` is stubbed: this test is about what the layer *says*, not about
    what it can see, and shelling out to pwsh would make it a different test.
    """
    root = tempfile.mkdtemp()
    cfg = shadow.ShadowConfig(enabled=True, run_root=root, run_id="unit-run", pid=os.getpid())
    os.makedirs(cfg.shadow_dir(), exist_ok=True)
    for row in seeded_rows:
        shadow._append_row(cfg.manifest_path(), row)
    seq = max([int(r.get("seq") or 0) for r in seeded_rows] + [0]) + 1
    if tmp_bytes is not None:
        with open(os.path.join(cfg.shadow_dir(), ".pending-%d-%d.png" % (os.getpid(), seq)), "wb") as fh:
            fh.write(tmp_bytes)
    probe = types.SimpleNamespace(ok=True, returncode=0, reason="", note="", target=None,
                                  data={"windows": [], "hwnds": []})
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf), mock.patch.object(shadow, "_probe", return_value=probe):
        row = shadow._capture(cfg, "cmd run foo", "cmd.run", _Resp(ok, code=code, payload=payload))
    return row, buf.getvalue()


class PromotedFrameAnnouncementTest(unittest.TestCase):
    def test_a_failed_action_names_the_frame_on_stderr(self) -> None:
        """The gap itself: a pinned frame must be reachable from the failure."""
        row, err = _capture(False, code="unhandled")
        self.assertTrue(row["promoted"])
        self.assertIn("promoted frame 1", err)
        self.assertIn("python -m ctl shadow --run-id unit-run --seq 1", err)

    def test_a_clean_action_says_nothing(self) -> None:
        """No promotion, no line -- the channel must not become routine noise."""
        row, err = _capture(True, payload=["ok"])
        self.assertFalse(row["promoted"])
        self.assertEqual("", err)

    def test_the_pointer_names_the_frame_that_owns_the_file(self) -> None:
        """Identical pixels live on an *earlier* seq -- pointing at `seq` would be a dead pointer."""
        pixels = b"\x89PNG\r\n\x1a\nunit-test-pixels"
        digest = hashlib.sha256(pixels).hexdigest()
        row, err = _capture(False, code="unhandled", tmp_bytes=pixels,
                            seeded_rows=[{"seq": 1, "shot": "0001-x.png", "sha256": digest}])
        self.assertEqual(1, row.get("same_as"))
        self.assertIn("--seq 1", err)
        self.assertNotIn("--seq 2", err)


if __name__ == "__main__":
    unittest.main()
