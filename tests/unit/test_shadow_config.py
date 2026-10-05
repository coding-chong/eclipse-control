"""`ctl/shadow.py` -- `resolve` / `configure` / `current` / `for_client` (the config layers).

The whole shadow layer hangs off one object; if the precedence chain reads the
wrong layer the ledger is either silently off or silently on, and nobody sees
it until a bug is being reproduced.  These tests pin the four layers and the two
places where an unusable input must degrade instead of raising.

Safety (D1): `configure` swaps the module-global `_STATE`, so `setUp` snapshots
it and `addCleanup` puts it back -- a leaked `_STATE` would re-point every other
test in the process at this run's temp dir.  `resolve` is only ever driven with
an explicit `env=` and an explicit `config_path=`: the developer's real
`os.environ` and `~/.eclipse-ctl/config.json` are never consulted (touching them
would make the outcome depend on the machine).

Shape contract (`deliverable-shape.md` C10): every expectation is this test's own
literal -- `20`, `33554432`, `7`, `9`, `1` are written out here, never read from
`DEFAULT_MAX_FRAMES` / `DEFAULT_MAX_BYTES`.

Falsify (measured 2026-10-06, one mutation at a time, `git checkout --` between;
each reddened exactly one test -- C12):
- **M1** `if no_shadow is not None:` -> `if no_shadow:` in `resolve` ->
  `test_explicitly_on_flag_is_marked_flag` red (`Ran 13 tests ... FAILED (failures=1)`).
  Note the asymmetry, which is the point of having both tests: under this
  mutation `test_absent_flag_keeps_the_env_layer` stays **green** -- a collapsed
  guard still returns the same thing for `None` (falsy), so only the
  "explicitly False" side moves.  One test alone would not have pinned the pair.
- swap the layer order in `resolve` -> the file/env/flag override tests go red.
- remove `max(1, ...)` from either clamp -> the two clamp tests go red.
- make `for_client` re-raise instead of catching -> the bad-client test goes red.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from ctl import shadow


class _Client:
    """A minimal stand-in -- `for_client` only does attribute reads + `port()`."""

    def __init__(self, run_root="/tmp/r", run_id="unit", host="1.2.3.4", port=8999):
        self.run_root = run_root
        self.run_id = run_id
        self.host = host
        self._port = port

    def port(self):
        return self._port


class _NoPortClient(_Client):
    def port(self):
        raise RuntimeError("no socket")


class _HostileClient:
    """Any attribute read blows up -- the "unusable client" contract."""

    @property
    def run_root(self):
        raise RuntimeError("boom")


class ShadowConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        old = shadow._STATE
        self.addCleanup(setattr, shadow, "_STATE", old)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config_path = os.path.join(tmp.name, "config.json")

    # -- helpers ----------------------------------------------------------- #

    def _write_file(self, data: dict) -> None:
        with open(self.config_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def _resolve(self, **kwargs):
        """Always pin `config_path` to the temp path; never fall through to `~`."""
        kwargs.setdefault("config_path", self.config_path)
        return shadow.resolve(**kwargs)

    # -- the four layers, one at a time ------------------------------------ #

    def test_default_layer_is_marked_default(self) -> None:
        cfg = self._resolve(env={})
        self.assertIs(True, cfg.enabled)
        self.assertEqual(20, cfg.max_frames)
        self.assertEqual(33554432, cfg.max_bytes)
        self.assertEqual("default", cfg.provenance["enabled"])
        self.assertEqual("default", cfg.provenance["max_frames"])

    def test_file_layer_overrides_the_default_and_is_marked_file(self) -> None:
        self._write_file({"shadow": False, "shadow_max_frames": 7})
        cfg = self._resolve(env={})
        self.assertIs(False, cfg.enabled)
        self.assertEqual(7, cfg.max_frames)
        self.assertEqual("file", cfg.provenance["enabled"])
        self.assertEqual("file", cfg.provenance["max_frames"])
        self.assertEqual("default", cfg.provenance["only_changes"])

    def test_env_layer_overrides_the_file_and_is_marked_env(self) -> None:
        self._write_file({"shadow": False, "shadow_max_frames": 7})
        cfg = self._resolve(env={"ECLIPSE_CTL_SHADOW": "true",
                                 "ECLIPSE_CTL_SHADOW_MAX_FRAMES": "9"})
        self.assertIs(True, cfg.enabled)
        self.assertEqual(9, cfg.max_frames)
        self.assertEqual("env", cfg.provenance["enabled"])
        self.assertEqual("env", cfg.provenance["max_frames"])

    def test_flag_layer_beats_the_env_and_is_marked_flag(self) -> None:
        cfg = self._resolve(env={"ECLIPSE_CTL_SHADOW": "true"}, no_shadow=True)
        self.assertIs(False, cfg.enabled)
        self.assertEqual("flag", cfg.provenance["enabled"])

    def test_absent_flag_keeps_the_env_layer(self) -> None:
        """`no_shadow=None` means "not given" and must not touch provenance."""
        cfg = self._resolve(env={"ECLIPSE_CTL_SHADOW": "true"}, no_shadow=None)
        self.assertEqual("env", cfg.provenance["enabled"])

    def test_explicitly_on_flag_is_marked_flag(self) -> None:
        """`no_shadow=False` is distinguishable from "not given" only by provenance."""
        cfg = self._resolve(env={"ECLIPSE_CTL_SHADOW": "true"}, no_shadow=False)
        self.assertIs(True, cfg.enabled)
        self.assertEqual("flag", cfg.provenance["enabled"])

    # -- the clamps that keep the newest frame alive ------------------------ #

    def test_frame_budget_is_clamped_up_to_one(self) -> None:
        self._write_file({"shadow_max_frames": 0})
        self.assertEqual(1, self._resolve(env={}).max_frames)

    def test_byte_budget_is_clamped_up_to_one(self) -> None:
        self._write_file({"shadow_max_bytes": 0})
        self.assertEqual(1, self._resolve(env={}).max_bytes)

    # -- configure / current ------------------------------------------------ #

    def test_configure_with_an_object_installs_it_verbatim(self) -> None:
        obj = shadow.ShadowConfig(run_id="hand-built")
        self.assertIs(obj, shadow.configure(cfg=obj))
        self.assertIs(obj, shadow.current())

    def test_configure_without_an_object_builds_a_fresh_one(self) -> None:
        obj = shadow.ShadowConfig(run_id="old")
        shadow.configure(cfg=obj)
        returned = shadow.configure(env={}, config_path=self.config_path)
        self.assertIs(returned, shadow.current())
        self.assertIsNot(obj, shadow.current())

    # -- for_client: bind, or degrade without raising ----------------------- #

    def test_for_client_binds_run_identity_host_and_port(self) -> None:
        shadow.configure(cfg=shadow.ShadowConfig())
        cfg = shadow.for_client(_Client())
        self.assertEqual("/tmp/r", cfg.run_root)
        self.assertEqual("unit", cfg.run_id)
        self.assertEqual("1.2.3.4", cfg.host)
        self.assertEqual(8999, cfg.port)

    def test_for_client_without_a_port_leaves_port_none(self) -> None:
        shadow.configure(cfg=shadow.ShadowConfig())
        self.assertIsNone(shadow.for_client(_NoPortClient()).port)

    def test_an_unusable_client_degrades_instead_of_raising(self) -> None:
        shadow.configure(cfg=shadow.ShadowConfig())
        cfg = shadow.for_client(_HostileClient())
        self.assertIs(False, cfg.enabled)
        self.assertEqual("unavailable", cfg.provenance["enabled"])


if __name__ == "__main__":
    unittest.main()
