"""Boundary validation at three edges the round-5 audit reproduced (R5-5/6/7).

* **R5-7** -- ``endpoint.json``'s ``port``/``pid`` are read only through
  ``discover_endpoint`` and must be type- and range-checked, never coerced:
  ``true`` is an ``int`` (``int(True) == 1``), ``3.9`` floors to 3 and ``1e10``
  addresses a port PowerShell's ``[uint32]`` cannot even express.
* **R5-5** -- a ``run_id`` becomes a path component under ``run_root``; it must be
  one directory name, so ``..\\..\\evil`` can never reach ``rmtree`` /
  ``makedirs`` / ``endpoint.json`` outside the run root.
* **R5-6** -- a ledger ``shot`` becomes a path handed to ``os.startfile``
  (``--open``) and ``os.remove`` (prune); it must stay inside ``shadow_dir``.

No IDE, no window, no network -- everything is a temp-directory file.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from ctl import client, lifecycle, shadow
from ctl.errors import EndpointNotFound, UsageError
from ctl.targets import Config
from ctl.verify.runner import Runner


class _TmpRun:
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="eclipse-ctl-boundary-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.run_id = "gs32-20261004-1200"
        os.makedirs(os.path.join(self.root, self.run_id), exist_ok=True)

    def _write_endpoint(self, payload):
        path = os.path.join(self.root, self.run_id, "endpoint.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)


class EndpointFieldValidationTest(_TmpRun, unittest.TestCase):
    """R5-7: ``discover_endpoint`` is the only reader and it validates."""

    def test_valid_endpoint_is_returned_typed(self):
        self._write_endpoint({"port": 8777, "pid": 4242})
        got = client.discover_endpoint(self.root, self.run_id)
        self.assertEqual(got["port"], 8777)
        self.assertEqual(got["pid"], 4242)

    def test_a_null_pid_is_allowed(self):
        # ``write_endpoint`` records ``None`` when the pid is unknown.
        self._write_endpoint({"port": 8777, "pid": None})
        self.assertIsNone(client.discover_endpoint(self.root, self.run_id)["pid"])

    def test_boolean_port_is_rejected(self):
        self._write_endpoint({"port": True, "pid": 4242})   # int(True) == 1
        with self.assertRaises(EndpointNotFound):
            client.discover_endpoint(self.root, self.run_id)

    def test_float_port_is_not_floored(self):
        self._write_endpoint({"port": 3.9, "pid": 4242})    # int(3.9) == 3
        with self.assertRaises(EndpointNotFound):
            client.discover_endpoint(self.root, self.run_id)

    def test_out_of_range_or_untyped_ports_are_rejected(self):
        for bad in (0, -1, 65536, 10 ** 10, "8777"):
            with self.subTest(port=bad):
                self._write_endpoint({"port": bad, "pid": 4242})
                with self.assertRaises(EndpointNotFound):
                    client.discover_endpoint(self.root, self.run_id)

    def test_boolean_or_nonpositive_pid_is_rejected(self):
        for bad in (True, 3.9, 0, -5, "4242"):
            with self.subTest(pid=bad):
                self._write_endpoint({"port": 8777, "pid": bad})
                with self.assertRaises(EndpointNotFound):
                    client.discover_endpoint(self.root, self.run_id)

    def test_shadow_reader_goes_through_the_same_validation(self):
        # shadow._instance_pid used to int()-coerce the raw field (`pid: true` -> 1);
        # it now routes through discover_endpoint, so an invalid file reads as "no pid".
        self._write_endpoint({"port": 8777, "pid": True})
        cfg = shadow.ShadowConfig(run_root=self.root, run_id=self.run_id)
        with mock.patch.object(shadow, "warn"):
            self.assertEqual(shadow._instance_pid(cfg), 0)

    def test_runner_and_live_pid_readers_go_through_the_same_validation(self):
        # `Runner.instance_pid` used to json.load + int() the field itself, so
        # `pid: true` read as 1 and the screen guard could be scoped to pid 1;
        # it now shares `resolve_pid`, as does `lifecycle.run_live_pid` (F2/R5-9).
        self._write_endpoint({"port": 8777, "pid": True})
        runner = Runner(Config(run_root=self.root), target_name="gs32",
                        run_id=self.run_id)
        self.assertEqual(runner.instance_pid(), 0)
        self.assertIsNone(lifecycle.run_live_pid(os.path.join(self.root, self.run_id)))

    def test_resolve_pid_is_the_single_numeric_reader(self):
        self._write_endpoint({"port": 8777, "pid": 4242})
        self.assertEqual(client.resolve_pid(self.root, self.run_id), 4242)
        # A missing run has no pid (0), never a guessed/coerced one.
        self.assertEqual(client.resolve_pid(self.root, "no-such-run"), 0)
        self.assertEqual(client.resolve_pid(self.root, None), 0)
        seen = []
        client.resolve_pid(self.root, "no-such-run", on_error=seen.append)
        self.assertEqual(len(seen), 1)


class RunIdPathValidationTest(unittest.TestCase):
    """R5-5: a run id is one directory name, checked before any join."""

    def test_escaping_run_ids_are_refused(self):
        for bad in ("..\\..\\Users\\Public\\evil", "../../etc", "C:\\Windows",
                    "a/b", "..", ".", "", "a b", "run\x00id", None):
            with self.subTest(run_id=bad):
                with self.assertRaises(UsageError):
                    lifecycle.run_paths("D:\\runs", bad)

    def test_the_client_path_gate_is_the_same_one(self):
        with self.assertRaises(UsageError):
            client.endpoint_path("D:\\runs", "..\\evil")
        with self.assertRaises(UsageError):
            client.write_endpoint("D:\\runs", "..\\evil", 8777)

    def test_the_shadow_path_gate_is_the_same_one(self):
        cfg = shadow.ShadowConfig(run_root="D:\\runs", run_id="..\\evil")
        with self.assertRaises(UsageError):
            cfg.shadow_dir()
        with self.assertRaises(UsageError):
            cfg.manifest_path()

    def test_a_bad_run_id_reaches_no_filesystem_write(self):
        with tempfile.TemporaryDirectory() as root:
            evil = os.path.join(os.path.dirname(root), "eclipse-ctl-evil-probe")
            with self.assertRaises(UsageError):
                lifecycle.prepare_run(lifecycle.run_paths(root, "..\\" + os.path.basename(evil)))
            self.assertFalse(os.path.exists(evil))

    def test_a_legal_run_id_still_builds_the_layout(self):
        paths = lifecycle.run_paths("D:\\runs", "gs32-20261004-1200")
        self.assertEqual(paths.endpoint,
                         os.path.join("D:\\runs", "gs32-20261004-1200", "endpoint.json"))


class ShadowFrameContainmentTest(unittest.TestCase):
    """R5-6: a manifest ``shot`` may only name a frame inside ``shadow_dir``."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="eclipse-ctl-shadow-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.run_id = "gs32-20261004-1200"
        self.shadow_dir = os.path.join(self.root, self.run_id, "shadow")
        os.makedirs(self.shadow_dir, exist_ok=True)
        self.cfg = shadow.ShadowConfig(run_root=self.root, run_id=self.run_id)

    def _manifest(self, *rows):
        with open(os.path.join(self.shadow_dir, "manifest.jsonl"), "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def test_a_shot_that_is_a_path_is_not_a_frame(self):
        for bad in ("..\\..\\evil.png", "../../evil.png", "C:\\evil.png",
                    "sub\\a.png", "a.txt", ".hidden.png", ""):
            with self.subTest(shot=bad):
                self.assertEqual(shadow.frame_path(self.cfg, {"shot": bad}), "")

    def test_a_plain_frame_name_resolves_inside_shadow_dir(self):
        got = shadow.frame_path(self.cfg, {"shot": "0001-120000-t.png"})
        self.assertEqual(got, os.path.join(self.shadow_dir, "0001-120000-t.png"))

    def test_prune_never_deletes_outside_the_shadow_dir(self):
        evil = os.path.join(self.root, "evil.png")          # two levels above shadow_dir
        with open(evil, "wb") as fh:
            fh.write(b"outside")
        with open(os.path.join(self.shadow_dir, "0002-a.png"), "wb") as fh:
            fh.write(b"inside")
        self._manifest({"seq": 1, "shot": "..\\..\\evil.png"},
                       {"seq": 2, "shot": "0002-a.png"})
        cfg = shadow.ShadowConfig(run_root=self.root, run_id=self.run_id,
                                  max_frames=1, max_bytes=1 << 20)
        deleted = shadow.prune(cfg)
        self.assertEqual([row.get("seq") for row in deleted], [])
        self.assertTrue(os.path.isfile(evil), "prune acted on a path outside shadow_dir")

    def test_live_bytes_ignores_escaping_rows(self):
        outside = os.path.join(self.root, "outside.png")
        with open(outside, "wb") as fh:
            fh.write(b"x" * 1234)
        with open(os.path.join(self.shadow_dir, "0002-a.png"), "wb") as fh:
            fh.write(b"y" * 10)
        self._manifest({"seq": 1, "shot": "..\\..\\outside.png"},
                       {"seq": 2, "shot": "0002-a.png"})
        self.assertEqual(shadow._live_bytes(self.cfg), 10)


if __name__ == "__main__":
    unittest.main()
