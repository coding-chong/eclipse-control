"""单元层：`ctl.targets.load` 的四层优先级（flag > env > file > 内置默认）。"""

import json
import os
import tempfile
import unittest
from unittest import mock

from ctl.errors import CtlError
from ctl.targets import DEFAULT_KEEP_RUNS, DEFAULT_TARGET, ENV_PREFIX, load


class ConfigPrecedence(unittest.TestCase):
    """每一层单独站一次，再逐层压上去——`provenance` 直接记谁胜出，用它断言。"""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config_path = os.path.join(tmp.name, "config.json")

    # -- helpers ----------------------------------------------------------- #

    def _write_file(self, data: dict) -> None:
        with open(self.config_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)

    def _load(self, flags=None, env=None):
        """Always pin `config` to the temp path, and wipe every `ECLIPSE_CTL_*`.

        Wiping matters: the developer's real environment would otherwise leak in
        and the precedence assertion would silently pass for the wrong reason.
        """
        effective_flags = dict(flags or {})
        effective_flags["config"] = self.config_path
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith(ENV_PREFIX)}
        clean_env.update(env or {})
        with mock.patch.dict(os.environ, clean_env, clear=True):
            return load(effective_flags)

    # -- the four layers, one at a time ------------------------------------ #

    def test_default_layer_when_nothing_is_set(self) -> None:
        cfg = self._load()
        self.assertEqual(cfg.default_target, DEFAULT_TARGET)
        self.assertEqual(cfg.keep_runs, DEFAULT_KEEP_RUNS)
        self.assertEqual(cfg.provenance["default_target"], "default")

    def test_file_layer_overrides_default(self) -> None:
        self._write_file({"default_target": "from-file", "keep_runs": 9})
        cfg = self._load()
        self.assertEqual(cfg.default_target, "from-file")
        self.assertEqual(cfg.keep_runs, 9)
        self.assertEqual(cfg.provenance["default_target"], "file")
        self.assertEqual(cfg.provenance["keep_runs"], "file")

    def test_env_layer_overrides_file(self) -> None:
        self._write_file({"default_target": "from-file"})
        cfg = self._load(env={ENV_PREFIX + "DEFAULT_TARGET": "from-env"})
        self.assertEqual(cfg.default_target, "from-env")
        self.assertEqual(cfg.provenance["default_target"], "env")

    def test_flag_layer_overrides_env_and_file(self) -> None:
        self._write_file({"default_target": "from-file"})
        cfg = self._load(
            flags={"default_target": "from-flag"},
            env={ENV_PREFIX + "DEFAULT_TARGET": "from-env"},
        )
        self.assertEqual(cfg.default_target, "from-flag")
        self.assertEqual(cfg.provenance["default_target"], "flag")

    # -- the edges that actually bite -------------------------------------- #

    def test_missing_config_file_is_not_an_error(self) -> None:
        """No file at all is the normal first-run state, not a failure."""
        self.assertFalse(os.path.isfile(self.config_path))
        cfg = self._load()
        self.assertEqual(cfg.provenance["default_target"], "default")

    def test_env_keep_runs_must_be_an_integer(self) -> None:
        with self.assertRaises(CtlError) as caught:
            self._load(env={ENV_PREFIX + "KEEP_RUNS": "not-a-number"})
        self.assertEqual(caught.exception.code, "badrequest")
        self.assertIn("KEEP_RUNS", caught.exception.message)

    def test_env_booleans_accept_the_documented_spellings(self) -> None:
        for raw, want in (("1", True), ("true", True), ("YES", True),
                          ("on", True), ("0", False), ("no", False)):
            with self.subTest(raw=raw):
                cfg = self._load(env={ENV_PREFIX + "COPY": raw})
                self.assertIs(cfg.copy, want)


if __name__ == "__main__":
    unittest.main()
