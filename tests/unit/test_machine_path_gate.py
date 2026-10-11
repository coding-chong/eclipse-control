"""Unit: a case may not embed a machine-local absolute path.

``ctl/__main__.py::_machine_path_check`` is the runnable judge for the case layer's own
promise -- "every value is an install-relative or a measured fact, never a
machine-local absolute path".  Until 2026-10-07 nothing checked it, and
``_DEFAULT_C2000WARE = "D:/ti/c2000/C2000Ware_5_04_00_00"`` shipped as a silent
fallback that made every other machine fail with a directory it never chose.

The two failure modes this file guards, in the repo's own vocabulary:

* **C10** -- the scanned set is pinned by *this* file's literal, not by the gate's own
  constant, so weakening ``_MACHINE_PATH_DIRS`` reddens a test instead of silently
  shrinking the gate and its guard together.
* **C11** -- the pattern's precision is pinned from both sides: a real machine path
  must be caught, and a legal spelling that merely *looks* like one must be let
  through.  Only reporting "it is green now" cannot distinguish "fixed" from
  "loosened".
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
import unittest.mock as mock

from ctl import __main__ as ctl_main
from ctl.__main__ import _MACHINE_PATH_DIRS, _MACHINE_PATH_EXEMPT, _machine_path_check

#: The scanned set, as this test's own literal (`deliverable-shape.md` C10).  Widened
#: 2026-10-11 from the case layer to the shipped trees: `ctl` covers `ctl/verify/cases`
#: as well, so the earlier set is a subset of this one.
_REQUIRED_DIRS = ("ctl", "bridge", "tools")

#: The exemption table, as this test's own literal (C10 again): a value added or changed
#: there must be a deliberate edit here too, or the exemption would be free to grow.
_EXEMPT_LITERAL = (
    ("ctl/targets.py", "D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2"),
    ("ctl/targets.py", "D:/ti/ccs1281/ccs/eclipse"),
)


class MachinePathGateTest(unittest.TestCase):
    """The gate, its precision, and its scan surface."""

    def _package(self, source: str) -> str:
        """A throwaway package holding one module, so the gate's red is proven
        without ever polluting the real tree."""
        root = tempfile.mkdtemp(prefix="eclipse-ctl-machine-path-")
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        with open(os.path.join(root, "c.py"), "w", encoding="utf-8") as fh:
            fh.write(source)
        return root

    def test_the_scanned_set_is_pinned_independently(self):
        self.assertEqual(tuple(_MACHINE_PATH_DIRS), _REQUIRED_DIRS)

    def test_the_real_tree_is_clean(self):
        ok, detail = _machine_path_check()
        self.assertTrue(ok, detail)
        self.assertIn("scanned", detail)

    def test_a_literal_machine_path_is_caught(self):
        root = self._package(
            'PROBE = "D:/ti/ccs1281/ccs/ccs_base/common/uscif/xds100serial.exe"\n')
        ok, detail = _machine_path_check((root,))
        self.assertFalse(ok)
        self.assertIn("c.py:1", detail)
        self.assertIn("D:/ti/ccs1281", detail)

    def test_a_docstring_mention_is_allowed(self):
        """A measured fact and a rerun recipe live in docstrings, and
        `measurement-hygiene` §13.10 requires those to stay verbatim -- so the unit
        is the string constant, not the token."""
        root = self._package(
            '"""Measured 2026-10-07 with install_dir = ``D:/ti/ccs1281/ccs/eclipse``."""\n'
            "X = 1\n")
        ok, detail = _machine_path_check((root,))
        self.assertTrue(ok, detail)

    def test_a_bare_drive_root_is_not_flagged(self):
        """C11's "must be let through" side: `C:/` is how a drive letter is spelled in
        prose, not a machine-local directory."""
        root = self._package('SEP = "C:/"\n')
        ok, detail = _machine_path_check((root,))
        self.assertTrue(ok, detail)

    def test_a_regex_metasequence_is_not_a_machine_path(self):
        """C11's "must be let through" side, measured 2026-10-09 (GS32 board case): a
        readelf regex spelled with `\\s` after the letter `s` and a colon contains the
        three characters `s:\\`, which a bare `[A-Za-z]:[\\\\/]` reads as a drive.  The
        2026-10-09 fix is in the pattern (a drive letter opens a token), not in the
        case's spelling -- so this stays green *and* the row below still reddens."""
        root = self._package('PAT = r"Class:\\s+(.+?)\\s*$"\n')
        ok, detail = _machine_path_check((root,))
        self.assertTrue(ok, detail)

    def test_a_url_literal_is_not_a_machine_path(self):
        """The same false-positive class, in its most common spelling: `https://` has
        `s:` followed by `//`."""
        root = self._package('DOC = "see https://example.com/foo for the format"\n')
        ok, detail = _machine_path_check((root,))
        self.assertTrue(ok, detail)

    def test_a_drive_letter_opening_a_token_is_still_caught(self):
        """The "must be caught" side of the lookbehind: `D:/…` after punctuation."""
        root = self._package('ELF = "D:/ProgramFiles/GS32Prog/x.exe"\n')
        ok, detail = _machine_path_check((root,))
        self.assertFalse(ok)
        self.assertIn("c.py:1", detail)
        self.assertIn("D:/ProgramFiles", detail)

    def test_an_install_relative_literal_is_not_flagged(self):
        """The shape the resolver is supposed to produce."""
        root = self._package('REL = "c2000/C2000Ware_5_04_00_00"\n')
        ok, detail = _machine_path_check((root,))
        self.assertTrue(ok, detail)

    def test_a_path_containing_a_space_is_caught(self):
        """C11's "must be caught" side, measured 2026-10-11: `C:/Program Files/…` is the
        commonest Windows install root there is, and the pattern could not see it -- the
        path segment could not cross the space, so no second separator was ever found.
        Two such literals had shipped in `_find_bash` (`C:/Program Files/Git/bin/bash.exe`)
        while this gate reported the tree green."""
        root = self._package('BIN = "C:/Program Files/Git/bin/bash.exe"\n')
        ok, detail = _machine_path_check((root,))
        self.assertFalse(ok)
        self.assertIn("c.py:1", detail)
        self.assertIn("C:/Program Files/Git/", detail)

    def test_the_exemptions_are_pinned_independently(self):
        self.assertEqual(tuple(_MACHINE_PATH_EXEMPT), _EXEMPT_LITERAL)

    def test_the_reference_defaults_are_exempted_by_value(self):
        """C10/C12 on the exemption itself, both sides in one test: with the table as
        shipped, the shipped tree is green on exactly those two literals; with the table
        emptied, the same tree reddens *on those two* -- so the exemption is what carries
        them, and it is carrying only them."""
        ok, detail = _machine_path_check(("ctl",))
        self.assertTrue(ok, detail)
        self.assertIn("exempt", detail)
        with mock.patch.object(ctl_main, "_MACHINE_PATH_EXEMPT", ()):
            ok, detail = _machine_path_check(("ctl",))
        self.assertFalse(ok, detail)
        self.assertIn("D:/ProgramFiles/GS32_Studio_v1.2.5.2/", detail)
        self.assertIn("D:/ti/ccs1281/ccs/", detail)
        self.assertNotIn("C:/Program Files", detail)


if __name__ == "__main__":
    unittest.main()
