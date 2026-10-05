"""`ctl/shadow.py` -- the ledger API (`read_rows`/`promote`/`find`/`open_frame`/`summary`).

These are the four verbs the `ctl shadow` CLI and the frame viewer sit on.  A
regression is invisible from the action path: frames keep being written and the
lookup either misses, rewrites the wrong row, or opens something that is not
there.

Safety (D2): every store is a fresh `tempfile.mkdtemp()` and the only viewer
touch is a patched `os.startfile` -- `open_frame` is exercised on its
"not a file" branch and through a stub, never against a real viewer.

Two layers of stub are deliberate and named here so the reader is not fooled:
- `open_frame`: the existence branch is judged with `os.startfile` replaced by a
  mock; the argument it received is the assertion, not a viewer window.
- `after`: `_is_write` and `_probe` are stubs.  This test judges `after`'s own
  gate (enabled? run identity? a dotted method? a write?), not the write-column
  fetch or the pwsh probe, which are other tests' business.

Shape contract (`deliverable-shape.md` C10): every expectation is this test's own
literal -- `[1, 2, 3]`, `"manual"`, `"= seq 1"`, `"3 action(s)"` -- never read
from a constant or from the row the code under test just returned.

Falsify (measured 2026-10-06, one mutation at a time, `git checkout --` between;
each reddened exactly one test -- C12):
- **M4** replace `os.replace(tmp, path)` in `promote` with `pass` ->
  `test_promote_persists_the_mark` red (`Ran 17 tests ... FAILED (errors=1)`) while
  the return-value assertions alone would have stayed green -- which is exactly why
  both the return value *and* a re-read are asserted here.
- **M3** narrow `except Exception` to `except ValueError` in `after` ->
  `test_after_swallows_a_capture_failure` red (`Ran 17 tests ... FAILED (errors=1)`).
  The mutation is deliberate: a narrowed `except` still swallows a `ValueError`, so
  only the `RuntimeError` path proves the catch is not type-specific.
- return `rows[::-1]` from `_rows` -> `test_rows_keep_their_on_disk_order` red.
- make `promote` rewrite even when nothing matched -> `test_promote_of_a_missing_seq_leaves_the_bytes_alone` red.
- drop the `if not path or not os.path.isfile(path)` guard in `open_frame` ->
  `test_open_frame_refuses_an_empty_path` red.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import tempfile
import types
import unittest
from unittest import mock

from ctl import shadow


class _Resp:
    """Stand-in for a bridge response -- `_outcome` only does attribute reads."""

    def __init__(self, ok=True, code="", payload=("ok",)):
        self.ok = ok
        self.code = code
        self.payload = list(payload)
        self.raw = ""
        self.status_line = ""


def _probe_stub():
    """A `_probe` result with nothing to see (see the module docstring)."""
    return types.SimpleNamespace(ok=True, returncode=0, reason="", note="",
                                 target=None, data={"windows": [], "hwnds": []})


class LedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        self.cfg = shadow.ShadowConfig(enabled=True, run_root=root, run_id="unit")
        os.makedirs(self.cfg.shadow_dir(), exist_ok=True)

    def _seed(self, rows):
        for row in rows:
            shadow._append_row(self.cfg.manifest_path(), row)

    def _three_rows(self):
        self._seed([
            {"seq": 1, "method": "cmd.run", "outcome": "ok"},
            {"seq": 2, "method": "cmd.run", "outcome": "ok"},
            {"seq": 3, "method": "cmd.run", "outcome": "ok"},
        ])

    # -- read_rows ---------------------------------------------------------- #

    def test_no_manifest_reads_as_no_rows(self) -> None:
        """A run that has done nothing is `[]`, not an error."""
        self.assertEqual([], shadow.read_rows(self.cfg))

    def test_rows_keep_their_on_disk_order(self) -> None:
        self._three_rows()
        rows = shadow.read_rows(self.cfg)
        self.assertEqual(3, len(rows))
        self.assertTrue(all(isinstance(r, dict) for r in rows))
        self.assertEqual([1, 2, 3], [r["seq"] for r in rows])

    # -- promote ------------------------------------------------------------ #

    def test_promote_persists_the_mark(self) -> None:
        """The returned row and the file must agree -- a return-only assert would
        pass on an in-memory edit that never reached disk."""
        self._three_rows()
        row = shadow.promote(self.cfg, 2)
        self.assertIs(True, row["promoted"])
        self.assertEqual("manual", row["promote_reason"])
        on_disk = shadow.read_rows(self.cfg)
        self.assertIs(True, on_disk[1]["promoted"])
        self.assertEqual("manual", on_disk[1]["promote_reason"])
        self.assertNotIn("promoted", on_disk[0])

    def test_promote_of_a_missing_seq_leaves_the_bytes_alone(self) -> None:
        """A miss is a no-op: no rewrite, no truncation, byte-identical file."""
        self._three_rows()
        path = self.cfg.manifest_path()
        with open(path, "rb") as fh:
            before = fh.read()
        self.assertIsNone(shadow.promote(self.cfg, 99))
        with open(path, "rb") as fh:
            self.assertEqual(before, fh.read())

    # -- find --------------------------------------------------------------- #

    def test_find_returns_the_matching_row(self) -> None:
        self._three_rows()
        row = shadow.find(self.cfg, 2)
        self.assertEqual(2, row["seq"])

    def test_find_of_a_missing_seq_is_none(self) -> None:
        self._three_rows()
        self.assertIsNone(shadow.find(self.cfg, 99))

    # -- open_frame (never the real viewer) ---------------------------------- #

    def test_open_frame_refuses_an_empty_path(self) -> None:
        with self.assertRaises(FileNotFoundError):
            shadow.open_frame("")

    def test_open_frame_refuses_a_path_that_is_not_a_file(self) -> None:
        missing = os.path.join(self.cfg.shadow_dir(), "nope.png")
        with self.assertRaises(FileNotFoundError):
            shadow.open_frame(missing)

    def test_open_frame_hands_an_existing_file_to_the_viewer(self) -> None:
        frame = os.path.join(self.cfg.shadow_dir(), "0001-120000-Box.png")
        with open(frame, "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n")
        with mock.patch.object(os, "startfile", create=True) as startfile:
            shadow.open_frame(frame)
        startfile.assert_called_once_with(frame)

    # -- after (stubs; see the module docstring) ---------------------------- #

    def test_after_is_silent_when_the_layer_is_disabled(self) -> None:
        cfg = shadow.ShadowConfig(enabled=False, run_root=self.cfg.run_root,
                                  run_id="unit")
        with mock.patch.object(shadow, "_is_write", return_value=True) as is_write:
            self.assertIsNone(shadow.after("cmd.run foo", _Resp(), cfg))
        is_write.assert_not_called()

    def test_after_is_silent_without_a_run_root(self) -> None:
        cfg = shadow.ShadowConfig(enabled=True, run_root="", run_id="unit")
        with mock.patch.object(shadow, "_is_write", return_value=True):
            self.assertIsNone(shadow.after("cmd.run foo", _Resp(), cfg))

    def test_after_is_silent_without_a_run_id(self) -> None:
        cfg = shadow.ShadowConfig(enabled=True, run_root=self.cfg.run_root, run_id="")
        with mock.patch.object(shadow, "_is_write", return_value=True):
            self.assertIsNone(shadow.after("cmd.run foo", _Resp(), cfg))

    def test_after_is_silent_for_a_read_method(self) -> None:
        with mock.patch.object(shadow, "_is_write", return_value=False):
            self.assertIsNone(shadow.after("cmd.run foo", _Resp(), self.cfg))

    def test_after_records_a_write(self) -> None:
        self.cfg.pid = os.getpid()
        with mock.patch.object(shadow, "_is_write", return_value=True), \
                mock.patch.object(shadow, "_probe", return_value=_probe_stub()):
            row = shadow.after("cmd.run foo", _Resp(), self.cfg)
        self.assertEqual(1, row["seq"])
        self.assertEqual("cmd.run", row["method"])

    def test_after_swallows_a_capture_failure(self) -> None:
        """Observation must never break the request it observes: no raise, one warn."""
        self.cfg.pid = os.getpid()
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf), \
                mock.patch.object(shadow, "_is_write", return_value=True), \
                mock.patch.object(shadow, "_probe", return_value=_probe_stub()), \
                mock.patch.object(shadow, "_capture",
                                  side_effect=RuntimeError("boom")):
            row = shadow.after("cmd.run foo", _Resp(), self.cfg)
        self.assertIsNone(row)
        self.assertIn("skipped", buf.getvalue())

    # -- summary ------------------------------------------------------------ #

    def test_summary_of_an_empty_ledger_names_the_run(self) -> None:
        lines = shadow.summary(self.cfg)
        self.assertIn("no shadow records for run unit", lines[0])

    def test_summary_counts_actions_frames_and_promotions(self) -> None:
        self._seed([
            {"seq": 1, "ts": "2026-10-06T12:00:00", "method": "cmd.run",
             "outcome": "ok", "shot": "0001-120000-Box.png"},
            {"seq": 2, "ts": "2026-10-06T12:00:01", "method": "cmd.run",
             "outcome": "ok", "same_as": 1},
            {"seq": 3, "ts": "2026-10-06T12:00:02", "method": "cmd.run",
             "outcome": "err", "promoted": True},
        ])
        lines = shadow.summary(self.cfg)
        self.assertIn("3 action(s)", lines[0])
        self.assertIn("1 frame(s)", lines[0])
        self.assertIn("1 promoted", lines[0])
        body = "\n".join(lines[1:])
        self.assertIn("= seq 1", body)
        self.assertIn("0001-120000-Box.png", body)


if __name__ == "__main__":
    unittest.main()
