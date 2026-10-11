"""Unit: every CLI error string is covered by `TROUBLESHOOTING.md` (A12).

``ctl/__main__.py::_error_string_coverage_check`` is the runnable judge for A12 --
"every failure line the CLI can print must be greppable in the troubleshooting table".
Until 2026-10-11 it existed only as a script **inside an archived task directory**: the
archive is read-only, nothing ran it, and it had gone red (`missing=4`) while the doc it
guards still claimed `coverage: PASS`.  This file is what keeps the moved judge from
quietly becoming decorative again -- the two failure modes below, in the repo's own
vocabulary:

* **C8** -- the judge must be able to *see* what it guards.  The probe below lives in a
  **subdirectory** of the scanned root, so a surface that silently reverted to "top level
  only" reddens a test instead of shrinking the judge and its guard together (C10).
* **C11** -- the matcher's precision is pinned from **both sides**: a template whose
  fragment is in the doc must stay green (the judge must not red on any new file), and one
  whose fragment is not must go red **naming that fragment**.
"""

from __future__ import annotations

import os
import unittest

from ctl.__main__ import (_ERR_TEMPLATE_EXEMPT, _ERR_TEMPLATE_MARK,
                          _error_string_coverage_check, _error_template_candidates,
                          _error_templates)

#: The repo root, as this test's own literal path walk (not the gate's `REPO_ROOT`).
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DOC = os.path.join(_ROOT, "TROUBLESHOOTING.md")
#: A **subdirectory** of the scanned root -- `ctl/verify/` is where a flat scan stops one
#: level short, so this is the exact place a "recursive" claim has to be provable.
_PROBE = os.path.join(_ROOT, "ctl", "verify", "_probe_error_coverage.py")

#: One coverage literal that the real table carries -- the "must be let through" side.
_COVERED_LITERAL = "no bridge jar built yet"
#: A fragment no row carries -- the "must be caught" side.
_UNCOVERED_LITERAL = "ERR probe never documented"


class ErrorCoverageGateTest(unittest.TestCase):
    """The judge, its precision, and its scan surface."""

    def _probe(self, literal: str) -> None:
        """Write one template into the scanned tree, removed again at cleanup.

        The file must parse and must carry the marker inside a **single** string
        constant: implicit concatenation is exactly what the judge is built to merge, so
        splitting it here would test the judge's parser with a shape no real error string
        uses.
        """
        with open(_PROBE, "w", encoding="utf-8") as fh:
            fh.write('#: probe\nPROBE = "%s; %s status"\n' % (literal, _ERR_TEMPLATE_MARK))
        self.addCleanup(lambda: os.path.exists(_PROBE) and os.remove(_PROBE))

    def test_the_real_tree_covers_every_error_string(self):
        ok, detail = _error_string_coverage_check()
        self.assertTrue(ok, detail)
        self.assertIn("template(s) from ctl", detail)
        self.assertIn("0 missing", detail)

    def test_an_undocumented_string_in_a_subdirectory_turns_it_red(self):
        """C8: the scan surface has to reach `ctl/verify/`, and a fragment that is in no
        row has to be reported by name -- a judge that only says "missing" cannot tell the
        reader which row to write."""
        self._probe(_UNCOVERED_LITERAL)
        ok, detail = _error_string_coverage_check()
        self.assertFalse(ok)
        self.assertIn("ctl/verify/_probe_error_coverage.py:2", detail)
        self.assertIn(_UNCOVERED_LITERAL, detail)

    def test_a_documented_string_in_a_subdirectory_stays_green(self):
        """C11's other side: finding a *new* file is not finding a gap.  Without this the
        test above would pass just as well on a judge that reddens on any change."""
        self._probe(_COVERED_LITERAL)
        ok, detail = _error_string_coverage_check()
        self.assertTrue(ok, detail)

    def test_dropping_a_covering_literal_turns_it_red(self):
        """A3: the judge is not vacuous -- take away the text that covers one template and
        it must red **on that template**.

        The literal is *found*, not hand-picked: the archived script's `--falsify` records
        why (its first version dropped a literal from a row that covered no template, which
        proved nothing).  Here the mutation removes **every** occurrence, so a fragment that
        happens to appear twice cannot leave the judge green and the test looking flaky.
        """
        with open(_DOC, encoding="utf-8") as fh:
            before = fh.read()
        ok, detail = _error_string_coverage_check()
        self.assertTrue(ok, detail)

        dropped = owner = None
        # Ask the judge's own helper which fragments each template can be covered by, and
        # take the first one the doc actually carries.
        for template, _loc in _error_templates():
            if any(template.startswith(e) for e in _ERR_TEMPLATE_EXEMPT):
                continue
            hits = [c for c in _error_template_candidates(template) if c in before]
            if hits:
                dropped = max(hits, key=len)
                owner = template
                break
        self.assertIsNotNone(dropped, "nothing covers anything -- the judge is broken, "
                                      "so this mutation would prove nothing")
        try:
            with open(_DOC, "w", encoding="utf-8") as fh:
                fh.write(before.replace(dropped, "[removed by the test]"))
            ok, detail = _error_string_coverage_check()
        finally:
            with open(_DOC, "w", encoding="utf-8") as fh:
                fh.write(before)
        self.assertFalse(ok, "dropped %r (it covered %r) and the judge stayed green"
                             % (dropped, (owner or "")[:70]))
        self.assertIn(dropped, detail)
        ok, detail = _error_string_coverage_check()
        self.assertTrue(ok, detail)


if __name__ == "__main__":
    unittest.main()
