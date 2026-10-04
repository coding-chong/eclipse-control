"""Unit: a target whose ``install_dir`` is absent gets a runnable fix command.

The built-in targets ship the *reference machine's* paths, so a fresh clone on
another machine stops on its first launch.  The diagnosis must name the command
that fixes it (``ctl targets add … --source-dir …``) instead of pointing at
``doctor``, which would only restate the same absence.
"""

import os
import tempfile
import unittest

from ctl.errors import PrereqNotReady
from ctl.lifecycle import RunPaths, _install_dir_missing, _launch_args
from ctl.targets import Target, reference_install_dir


def _target(install_dir: str) -> Target:
    return Target(
        name="gs32",
        install_dir=install_dir,
        eclipse_version="4.30.0",
        jre="23.0.2",
        java_target="17",
        product="com.gs.ui.Studio",
        default_port=8777,
        port=8777,
        launcher="GS32.exe",
        vendor_prefix="com.gs",
    )


def _paths() -> RunPaths:
    root = os.path.join("R", "probe")
    return RunPaths(
        run_root="R",
        run_id="probe",
        workspace=os.path.join(root, "ws"),
        configuration=os.path.join(root, "configuration"),
        install=os.path.join(root, "install"),
        endpoint=os.path.join(root, "endpoint.json"),
        bridge_log=os.path.join(root, "bridge.log"),
        console_log=os.path.join(root, "console.log"),
        shots=os.path.join(root, "shots"),
    )


class InstallDirDiagnosis(unittest.TestCase):
    def test_missing_install_dir_names_the_runnable_fix(self) -> None:
        absent = os.path.join(tempfile.gettempdir(), "ectl-absent-%d" % os.getpid(),
                              "install-tree")
        with self.assertRaises(PrereqNotReady) as caught:
            _launch_args(_target(absent), _paths(), 8777)
        message = str(caught.exception)
        self.assertIn("targets add", message)
        self.assertIn("--source-dir", message)
        self.assertIn(absent, message)
        self.assertTrue(message.startswith("ERR notfound"), message)

    def test_shipped_default_is_called_the_reference_machines(self) -> None:
        reference = reference_install_dir("gs32")
        self.assertTrue(reference, "gs32 must keep a built-in install_dir")
        message = str(_install_dir_missing(_target(reference)))
        self.assertIn("it is the reference machine's value", message)
        self.assertIn("python -m ctl targets add gs32 --source-dir", message)


if __name__ == "__main__":
    unittest.main()
