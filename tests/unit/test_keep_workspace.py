"""``--keep-workspace``: the workspace survives install, and the flag is wired.

A project must be importable by the IDE *before* it starts: the bridge's write
surface (``ui.close`` / ``ui.open`` / ``cmd.run`` / ``cmd.runp``) has no text
input, so a project can never be imported into a running IDE.  The only seat for
it is the run workspace (``-data``), which ``install`` used to wipe on every run.

Three layers, tested separately (``measurement-hygiene.md`` §13.7 -- a contract
that holds at one layer says nothing about the layer below it):

1. ``prepare_run`` itself -- the primitive;
2. ``lifecycle.install`` -- the primitive is actually reached with the right
   polarity (mutation: delete the ``not`` at ``ctl/lifecycle.py:742``);
3. the CLI -- ``--keep-workspace`` reaches ``install``, and ``upgrade`` refuses
   to inherit it (mutations: drop the argument, drop the call-site wiring, drop
   ``upgrade``'s explicit pin).

Every expectation below is this test's own literal (``deliverable-shape.md``
C10): no production constant is iterated, so shrinking the feature cannot shrink
the assertions along with it.

No IDE, no network -- a temp directory, a sentinel file, and mocks.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from ctl import lifecycle
from ctl.__main__ import _cmd_install, _cmd_upgrade, build_parser
from ctl.targets import Config


class _EnvResponse:
    """The smallest thing ``install`` reads off ``Client.env()``."""

    ok = True
    text = "protocol=1"


def _fake_console() -> mock.MagicMock:
    console = mock.MagicMock()
    console.proc = None
    console.wait_for_prompt.return_value = True
    return console


def _instance_stub() -> mock.MagicMock:
    """An ``Instance`` good enough for ``_cmd_install``'s print path."""
    instance = mock.MagicMock()
    instance.info.return_value = {"env": {"protocol": "1"}, "run_id": "r",
                                  "configuration": "c", "workspace": "w",
                                  "port": 8777, "version": "0.2.0"}
    instance.paths.endpoint = "/tmp/endpoint.json"
    return instance


class _InstallHarness:
    """Drive the real ``lifecycle.install`` with the IDE boundary mocked out."""

    def __init__(self, test: unittest.TestCase) -> None:
        self.root = tempfile.mkdtemp(prefix="eclipse-ctl-workspace-")
        test.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.run_id = "gs32-20261006-1200"
        self.paths = lifecycle.run_paths(self.root, self.run_id)
        self.sentinel = os.path.join(self.paths.workspace, ".metadata", "keep-me.txt")
        os.makedirs(os.path.dirname(self.sentinel), exist_ok=True)
        with open(self.sentinel, "w", encoding="utf-8") as fh:
            fh.write("pre-seeded project")
        self.config = Config(run_root=self.root)

    def run(self, **kwargs):
        client = mock.MagicMock()
        client.env.return_value = _EnvResponse()
        with mock.patch.object(lifecycle, "list_port_listeners", return_value=[]), \
                mock.patch.object(lifecycle, "launch", return_value=_fake_console()), \
                mock.patch.object(lifecycle, "install_bundle", return_value=581), \
                mock.patch.object(lifecycle, "wait_for_bridge", return_value=True), \
                mock.patch.object(lifecycle, "wait_for_workbench",
                                  return_value=(True, "ui.parts OK")), \
                mock.patch.object(lifecycle, "Client", return_value=client):
            return lifecycle.install(self.config, "gs32", self.run_id,
                                     startup_wait=0.0, ping_timeout=0.0,
                                     workbench_timeout=0.0, **kwargs)


class PrepareRunTest(unittest.TestCase):
    """Layer 1: the primitive.  Mutation M3f (default flipped) reddens this."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="eclipse-ctl-workspace-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paths = lifecycle.run_paths(self.root, "gs32-20261006-1200")
        # A pre-seeded project, before any install runs: the `.metadata` shape
        # is what Eclipse writes for a workspace that already holds a project.
        self.sentinel = os.path.join(self.paths.workspace, ".metadata", "keep-me.txt")
        os.makedirs(os.path.dirname(self.sentinel), exist_ok=True)
        with open(self.sentinel, "w", encoding="utf-8") as fh:
            fh.write("pre-seeded project")

    def test_keep_workspace_leaves_the_existing_files_in_place(self):
        lifecycle.prepare_run(self.paths, fresh_workspace=False)
        self.assertTrue(os.path.isfile(self.sentinel),
                        "fresh_workspace=False deleted a pre-seeded workspace file")
        self.assertTrue(os.path.isdir(self.paths.configuration))
        self.assertTrue(os.path.isdir(self.paths.shots))

    def test_fresh_workspace_wipes_it(self):
        lifecycle.prepare_run(self.paths, fresh_workspace=True)
        self.assertFalse(os.path.exists(self.sentinel),
                         "fresh_workspace=True left a file from the previous workspace")
        self.assertTrue(os.path.isdir(self.paths.workspace),
                        "the workspace directory itself must be recreated")

    def test_the_default_is_a_fresh_workspace(self):
        # The omitted argument must behave exactly like `fresh_workspace=True`;
        # `install()` relies on this when `--keep-workspace` is not given.
        lifecycle.prepare_run(self.paths)
        self.assertFalse(os.path.exists(self.sentinel),
                         "prepare_run() default no longer wipes the workspace")


class InstallWiringTest(unittest.TestCase):
    """Layer 2: ``install`` reaches the primitive with the right polarity.

    Mutation M3c (delete the ``not`` at ``ctl/lifecycle.py:742``) must redden
    ``test_keep_workspace_true_survives_a_real_install``; mutation M3d (flip
    ``install``'s default) must redden the default test.
    """

    def test_keep_workspace_true_survives_a_real_install(self):
        harness = _InstallHarness(self)
        harness.run(keep_workspace=True)
        self.assertTrue(
            os.path.isfile(harness.sentinel),
            "install(keep_workspace=True) still wiped the workspace: the flag never "
            "reaches prepare_run() (ctl/lifecycle.py:742)")

    def test_the_default_install_still_wipes(self):
        harness = _InstallHarness(self)
        harness.run()
        self.assertFalse(
            os.path.exists(harness.sentinel),
            "install() without keep_workspace no longer wipes the workspace")

    def test_keep_workspace_false_wipes(self):
        harness = _InstallHarness(self)
        harness.run(keep_workspace=False)
        self.assertFalse(
            os.path.exists(harness.sentinel),
            "install(keep_workspace=False) must behave exactly like the default")


class CliWiringTest(unittest.TestCase):
    """Layer 3: the parser and the two lifecycle commands.

    Mutations M3a (drop the ``--keep-workspace`` argument) and M3b (drop the
    call-site wiring at ``ctl/__main__.py:758``) must redden here; M3e (drop
    ``upgrade``'s explicit pin at ``ctl/__main__.py:856``) must redden
    ``test_upgrade_never_keeps_the_workspace``.
    """

    def test_parser_defaults_to_wiping(self):
        args = build_parser().parse_args(["install"])
        self.assertIs(args.keep_workspace, False,
                      "install must wipe the workspace unless --keep-workspace is given")

    def test_parser_accepts_the_flag(self):
        args = build_parser().parse_args(["install", "--keep-workspace"])
        self.assertIs(args.keep_workspace, True,
                      "--keep-workspace must set keep_workspace=True")

    def _install_namespace(self, keep_workspace: bool):
        args = build_parser().parse_args(["install"])
        args.keep_workspace = keep_workspace
        return args

    def test_cmd_install_passes_the_flag_through(self):
        for wanted in (True, False):
            with self.subTest(keep_workspace=wanted):
                instance = _instance_stub()
                with mock.patch("ctl.__main__.lifecycle_install",
                                return_value=instance) as install_call:
                    with contextlib.redirect_stdout(io.StringIO()):
                        _cmd_install(self._install_namespace(wanted))
                self.assertEqual(install_call.call_args.args[5], wanted,
                                 "the CLI flag never reached lifecycle.install")

    def test_upgrade_never_keeps_the_workspace(self):
        # `upgrade` reuses `_cmd_install`; a rebuild is a controlled restart and
        # must wipe exactly as it always has.  The namespace is poisoned with
        # True on purpose: the pin has to survive a caller that sets it.
        #
        # Patch `_cmd_install` itself, not `lifecycle_install`: this assertion is
        # about `upgrade`'s own pin, so it must not depend on the shared call-site
        # wiring (a mutation there is `test_cmd_install_passes_the_flag_through`'s
        # job -- `deliverable-shape.md` C12).
        args = build_parser().parse_args(["upgrade"])
        args.keep_workspace = True
        with mock.patch("ctl.__main__._build_bridge", return_value=0), \
                mock.patch("ctl.__main__.lifecycle_uninstall", return_value={}), \
                mock.patch("ctl.__main__._cmd_install", return_value=0) as install_call:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                _cmd_upgrade(args)
        delegated = install_call.call_args.args[0]
        self.assertIs(delegated.keep_workspace, False,
                      "upgrade inherited --keep-workspace; it must pin a fresh workspace")


if __name__ == "__main__":
    unittest.main()
