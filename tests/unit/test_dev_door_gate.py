"""``preflight`` 的「开发者门不进用户路径」闸门（`deliverable-shape.md` §6② / C5）。

`README.md` 与 `skill/` 树里**不许出现**开发者门的字面量 —— 但按**词边界**判，不按子串判。
子串形式会把报错串里的**字段名** `install_dir` 误报，而 `README.md` 逐字引用整条报错串正是
换机自救的一部分（`f891660` 引入，`A3` 要求保留）⇒ 子串判据与它不能同时成立，错的是判据。
本用例钉三件事：

1. **扫描面**（根 `README.md` / `skill/` / `skill/references/`）以**测试自己的字面量**钉住
   （`deliverable-shape.md` C10），并**逐项变异**：往每一个被扫位置各降一个真门，闸门必须变红
   且报 `file:line`；还原后必须变绿；
2. 词边界**不是顺手放宽**：`install_dir`（字段名）→ 绿（且证明该文件确实在扫描面里），
   裸词 `install` → 红；
3. `--help` 的简介逐项列出、项数与实际一致（`N1`）。

判据的可复跑形态：``python -c "from ctl.__main__ import _dev_door_leak_check as f; print(f())"``。
"""

from __future__ import annotations

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from ctl.__main__ import _DEV_DOOR_RE, _dev_door_leak_check, build_parser

#: 仓库根。本文件在 ``<root>/tests/unit/`` 下。
_ROOT = Path(__file__).resolve().parents[2]

#: 变异探针的文件名（放进被扫位置，用例结束即删）。
_PROBE = "_gate_probe_devdoor.md"

#: 一个**真的**开发者门（`ctl` 子命令 `upgrade`，在 `_DEV_DOOR_WORDS` 里）。
_VIOLATION = "跑 `python -m ctl upgrade` 即可\n"

#: 裸词 `install`（不是 `install_dir`）：必须被词边界逮住。
_BARE_INSTALL = "run install to deploy\n"

#: 字段名 `install_dir`（报错串的一部分）：必须**放过**。
_FIELD_NAME = "内置矩阵里各带一个 `install_dir`，值是参考机的路径\n"

#: 被扫位置里能用「新建探针文件」证明的目录（不动真文件）。
_SCANNED_DIRS = (("skill-root", "skill"), ("skill-references", "skill/references"))

#: 扫描面**就是**这两个既有文件：证明它们被读只能变更真文件，故逐字节备份 / 还原。
_SCANNED_FILES = (("root README", "README.md"), ("skill index", "skill/SKILL.md"))

#: `preflight --help` 的简介必须逐项列出、项数与**顺序**都一致的检查项（`N1`）。
#: 以**测试自己的字面量**钉住，而不是复用实现里的任何集合。
_PREFLIGHT_ITEMS = ("doctor", "verify", "doc/CLI command consistency",
                    "developer-door leak check", "skill/library-name consistency",
                    "stdlib-only imports", "no machine-local paths",
                    "CLI error-string coverage", "CHANGELOG")


def _scanned_count(detail: str) -> int:
    """``'12 user-face file(s) scanned'`` -> ``12``。"""
    return int(detail.split()[0])


def _append(path: Path, text: str) -> int:
    """在 ``path`` 末尾追加 ``text``，返回它落在的行号（bytes 原样，便于还原）。"""
    data = path.read_bytes()
    prefix = "" if data.endswith(b"\n") else "\n"
    path.write_bytes(data + prefix.encode("utf-8") + text.encode("utf-8"))
    return len((data.decode("utf-8") + prefix + text).splitlines())


class DevDoorGateTest(unittest.TestCase):
    def test_repo_is_clean(self):
        ok, detail = _dev_door_leak_check()
        self.assertTrue(ok, detail)
        self.assertIn("user-face file(s) scanned", detail)

    def test_word_boundary_admits_the_field_name_and_still_catches_the_door(self):
        # 判据语义本身：`install` 是门，`install_dir` 是字段名，`Install` 是另一种拼写。
        self.assertTrue(_DEV_DOOR_RE.search("跑 `python -m ctl install` 即可"))
        self.assertTrue(_DEV_DOOR_RE.search("`gc` 清掉旧 run"))
        self.assertTrue(_DEV_DOOR_RE.search(_BARE_INSTALL))
        self.assertIsNone(_DEV_DOOR_RE.search(_FIELD_NAME),
                          "`install_dir` is an error-string field name, not the door")
        self.assertIsNone(_DEV_DOOR_RE.search("Install"), "the match is case-sensitive")

    def test_every_probed_location_is_actually_scanned(self):
        # C10 逐项变异：闸门看不见哪一层，就在哪一条上失败（往**新建**文件里放）。
        for label, rel in _SCANNED_DIRS:
            with self.subTest(location=label):
                probe = _ROOT / rel / _PROBE
                probe.write_text(_VIOLATION, encoding="utf-8")
                self.addCleanup(probe.unlink, missing_ok=True)
                ok, detail = _dev_door_leak_check()
                self.assertFalse(ok, "%s/ is outside the gate's scan surface" % rel)
                self.assertIn("%s/%s:1: upgrade" % (rel, _PROBE), detail)
                probe.unlink()
                self.assertTrue(_dev_door_leak_check()[0])

    def test_readme_and_skill_index_are_actually_read(self):
        # 扫描面就是这两个文件本身 ⇒ 只能**变更真文件**再逐字节还原，不得留差异。
        for label, rel in _SCANNED_FILES:
            with self.subTest(location=label):
                path = _ROOT / rel
                original = path.read_bytes()
                self.addCleanup(path.write_bytes, original)
                lineno = _append(path, _VIOLATION)
                ok, detail = _dev_door_leak_check()
                self.assertFalse(ok, "%s is outside the gate's scan surface" % rel)
                self.assertIn("%s:%d: upgrade" % (rel, lineno), detail)
                path.write_bytes(original)
                ok, detail = _dev_door_leak_check()
                self.assertTrue(ok, "restoring the file must bring the gate back to green")
                self.assertEqual(path.read_bytes(), original)

    def test_real_door_in_the_references_layer_turns_it_red(self):
        # A2 的形状：往新层降一个真门 -> 红且报 `file:line` -> 还原 -> 绿。
        probe = _ROOT / "skill" / "references" / _PROBE
        probe.write_text(_VIOLATION, encoding="utf-8")
        self.addCleanup(probe.unlink, missing_ok=True)
        ok, detail = _dev_door_leak_check()
        self.assertFalse(ok, detail)
        self.assertIn("skill/references/%s:1: upgrade" % _PROBE, detail)
        probe.unlink()
        ok, detail = _dev_door_leak_check()
        self.assertTrue(ok, detail)

    def test_field_name_in_the_references_layer_stays_green(self):
        # `install_dir` 是字段名 -> 放过。同时证明这个文件**确实被读了**（文件数 +1），
        # 否则「放过」可能只是「压根没在扫描面里」。
        before = _scanned_count(_dev_door_leak_check()[1])
        probe = _ROOT / "skill" / "references" / _PROBE
        probe.write_text(_FIELD_NAME, encoding="utf-8")
        self.addCleanup(probe.unlink, missing_ok=True)
        ok, detail = _dev_door_leak_check()
        self.assertTrue(ok, detail)
        self.assertEqual(_scanned_count(detail), before + 1)
        probe.unlink()

    def test_bare_install_word_in_the_references_layer_turns_it_red(self):
        # 词边界没有放宽：整词 `install`（不是字段名）仍必须被逮住。
        probe = _ROOT / "skill" / "references" / _PROBE
        probe.write_text(_BARE_INSTALL, encoding="utf-8")
        self.addCleanup(probe.unlink, missing_ok=True)
        ok, detail = _dev_door_leak_check()
        self.assertFalse(ok, detail)
        self.assertIn("skill/references/%s:1: install" % _PROBE, detail)
        probe.unlink()
        self.assertTrue(_dev_door_leak_check()[0])

    def test_preflight_help_lists_every_check_with_the_right_count(self):
        # N1：旧简介漏了 `stdlib-only` / `skill/library-name` / 本次新增项。
        # 宽度放宽到 300 列，免得换行把带连字符的词切开（`developer- door`）。
        expected = " + ".join(_PREFLIGHT_ITEMS) + " (%d items)" % len(_PREFLIGHT_ITEMS)
        with mock.patch.dict(os.environ, {"COLUMNS": "300"}):
            parser = build_parser()
            top = " ".join(parser.format_help().split())
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
                parser.parse_args(["preflight", "--help"])
            own = " ".join(buf.getvalue().split())
        self.assertIn("preflight " + expected, top)
        self.assertIn(expected, own)


if __name__ == "__main__":
    unittest.main()
