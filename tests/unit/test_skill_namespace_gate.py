"""``preflight`` 的「skill ↔ `ctl run` 命名空间」门禁（R7 / A7）。

skill 教 agent 调的名字必须**真的存在**：``skill/`` 树下每个 ``name(…)`` 形状的
反引号名字都要能在 ``ctl/run.py::_make_namespace`` 里找到。本用例钉两件事：

1. 正常仓报绿，且任务点名的三个观测装置确实在命名空间里（``see`` / ``windows`` /
   ``close_window``）—— 用**测试自己的字面量**，而不是照抄实现里的任何集合
   （`deliverable-shape.md` **C10**：把某个名字从命名空间摘掉，必须在这里变红）；
2. **逐项变异**：往 ``skill/`` 的每一层各放一个不存在的 ``name(…)``，门禁必须变红并报出
   ``file:line``；删掉后必须变绿。

判据的可复跑形态：``python -c "from ctl.__main__ import _skill_namespace_consistency as f; print(f())"``。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from ctl.__main__ import _skill_calls, _skill_namespace_consistency
from ctl.run import _DoorState, _make_namespace

#: 仓库根。本文件在 ``<root>/tests/unit/`` 下。
_ROOT = Path(__file__).resolve().parents[2]

#: 变异探针的文件名（放进被扫位置，用例结束即删）。
_PROBE = "_gate_probe_skill.md"

#: 一个**不在**命名空间里的名字（下划线小写，正落在被检查的形状里）。
_BOGUS = "zzz_gate_probe"

_VIOLATION = "调用 `%s()` 看界面\n" % _BOGUS

#: 任务点名、必须可用的库函数（`P1`）。以独立字面量钉住：命名空间少一个，这里就红。
_REQUIRED_NAMES = ("see", "windows", "close_window")

#: 门禁必须覆盖的位置（``deliverable-shape.md`` C8）。同样独立字面量。
_SCANNED = (("skill-root", "skill"), ("skill-references", "skill/references"))


class SkillNamespaceGateTest(unittest.TestCase):
    def test_repo_is_consistent(self):
        ok, detail = _skill_namespace_consistency()
        self.assertTrue(ok, detail)
        self.assertIn("skill file(s) scanned", detail)

    def test_required_names_exist_in_the_namespace(self):
        # 被守护集合不许静默缩水（C10）：这三个名字没了，无论 skill 怎么写都得红。
        namespace = set(_make_namespace(None, _DoorState()).keys())
        for name in _REQUIRED_NAMES:
            with self.subTest(name=name):
                self.assertIn(name, namespace)

    def test_skill_calls_are_line_aware_and_lowercase_only(self):
        # `name(` 才是库函数；带大写的名字（SWT/Java 方法）不是，也不该被读成库函数。
        self.assertEqual(_skill_calls("a\n`see()` and `getChildren()`"), [("see", 2)])
        self.assertEqual(_skill_calls("`cmd(id, yes=True)`"), [("cmd", 1)])

    def test_every_skill_location_is_actually_scanned(self):
        for label, rel in _SCANNED:
            with self.subTest(location=label):
                probe = _ROOT / rel / _PROBE
                probe.write_text(_VIOLATION, encoding="utf-8")
                self.addCleanup(probe.unlink, missing_ok=True)
                ok, detail = _skill_namespace_consistency()
                self.assertFalse(ok, "%s/ is outside the gate's scan surface" % rel)
                self.assertIn(_BOGUS, detail)
                self.assertIn("%s/%s:1" % (rel, _PROBE), detail)
                probe.unlink()

    def test_bogus_name_turns_it_red_then_green_again(self):
        # A7 的形状：改坏 skill 里的库函数名 -> 红且报 `file:line` -> 还原 -> 绿。
        probe = _ROOT / "skill" / "references" / _PROBE
        probe.write_text(_VIOLATION, encoding="utf-8")
        self.addCleanup(probe.unlink, missing_ok=True)
        ok, detail = _skill_namespace_consistency()
        self.assertFalse(ok, detail)
        self.assertIn("skill/references/%s:1: %s" % (_PROBE, _BOGUS), detail)
        probe.unlink()
        ok, detail = _skill_namespace_consistency()
        self.assertTrue(ok, detail)


if __name__ == "__main__":
    unittest.main()
