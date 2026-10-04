"""``preflight`` 的「文档-子命令」门禁：扫描面必须覆盖**整棵** ``skill/``。

``A9``（R9 / `deliverable-shape.md` C8）：``R4`` 把深度搬进 ``skill/references/``，
而旧扫描面是**单层**的 ``skill/*.md`` ⇒ 新层会整片落在闸门视野之外。这条测试把「看得见」
变成机械判据 —— 往**每一个**被扫位置各放一个不存在的子命令探针，门禁**必须**变红
并报出 ``file:line``；探针删掉后**必须**变绿。

判据的可复跑形态：``python -c "from ctl.__main__ import _doc_command_consistency as f; print(f())"``。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from ctl.__main__ import _doc_command_consistency, _doc_commands

#: 仓库根。本文件在 ``<root>/tests/unit/`` 下。
_ROOT = Path(__file__).resolve().parents[2]

#: 变异探针的文件名（放进被扫位置，用例结束即删）。
_PROBE = "_gate_probe_docs.md"

#: 一个不存在的子命令（`SUBCOMMANDS` 里没有它）。
_BAD_SUBCOMMAND = "gateprobe-nosuch"

_VIOLATION = "跑 `python -m ctl %s` 即可\n" % _BAD_SUBCOMMAND

#: 门禁必须覆盖的位置（``deliverable-shape.md`` C8 / C10）。以**独立字面量**钉住，
#: 而不是复用实现里的 glob：否则扫描面被改回单层时，测试会跟着一起缩、仍报绿。
_SCANNED = (
    ("root", ""),
    ("skill-root", "skill"),
    ("skill-references", "skill/references"),
    ("recipes", "recipes"),
)


class DocCommandGateTest(unittest.TestCase):
    def test_repo_is_consistent(self):
        ok, detail = _doc_command_consistency()
        self.assertTrue(ok, detail)
        self.assertIn("doc file(s) scanned", detail)

    def test_doc_commands_carry_line_numbers(self):
        # `file:line` 是 A9 要求的报错形状；提取必须带行号（两行各命中一次）。
        self.assertEqual(_doc_commands("a\n`python -m ctl run`\nb"), [("run", 2)])
        self.assertEqual(_doc_commands("`ctl parts` then `python -m ctl tree 2`"),
                         [("parts", 1), ("tree", 1)])

    def test_every_scanned_location_is_actually_scanned(self):
        # 逐个位置造变异、逐个还原：门禁看不见哪一层，就在那一条上失败。
        for label, rel in _SCANNED:
            with self.subTest(location=label):
                probe = _ROOT / (rel + "/" if rel else "") / _PROBE
                probe.write_text(_VIOLATION, encoding="utf-8")
                self.addCleanup(probe.unlink, missing_ok=True)
                ok, detail = _doc_command_consistency()
                self.assertFalse(ok, "%s/ is outside the gate's scan surface" % (rel or "<root>"))
                self.assertIn(_BAD_SUBCOMMAND, detail)
                where = ("%s/%s" % (rel, _PROBE)) if rel else _PROBE
                self.assertIn("%s:1" % where, detail)
                probe.unlink()

    def test_references_layer_is_inside_the_surface(self):
        # A9 的核心：新层 `skill/references/` 必须与 `skill/SKILL.md` 同在一个门里。
        probe = _ROOT / "skill" / "references" / _PROBE
        probe.write_text(_VIOLATION, encoding="utf-8")
        self.addCleanup(probe.unlink, missing_ok=True)
        ok, detail = _doc_command_consistency()
        self.assertFalse(ok, detail)
        self.assertIn("skill/references/%s:1" % _PROBE, detail)
        probe.unlink()
        ok, detail = _doc_command_consistency()
        self.assertTrue(ok, detail)


if __name__ == "__main__":
    unittest.main()
