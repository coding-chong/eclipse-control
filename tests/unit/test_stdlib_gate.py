"""``preflight`` 的 stdlib 门禁：`_stdlib_only_check()` 必须真能看见非标准库 import。

`R11'.3`（依赖策略）此前**只有纪律、没有门禁** —— 全仓唯一提到「只用标准库」的地方是
`ctl/__init__.py:11` 与 `ctl/targets.py:9` 两行 docstring，而 `_cmd_preflight` 只做
`doctor` / `verify --all` / 文档-命令一致性 / `CHANGELOG` 版次四项，没有一项会因
`import requests` 变红（`prd.md` §6 第 11 条，2026-10-04 实测）。

这条测试钉住三件事：

1. **正常仓报绿** —— `_stdlib_only_check()` 返回 `(True, …)`；
2. **三个目录都在扫描面内** —— 往 `ctl/` / `bridge/` / `tools/` 各放一个 `import requests`
   探针文件，门禁必须变红并报出 `file:line`（探针在 `addCleanup` 里删除，跑完还原）；
3. **包内与相对 import 不误报** —— `from . import x`（相对）与 `from ctl.run import y`
   （包内）都不得被当成第三方依赖。

判据的可复跑形态：``python -c "from ctl.__main__ import _stdlib_only_check as f; print(f())"``。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from ctl.__main__ import _STDLIB_ONLY_DIRS, _import_roots, _stdlib_only_check

#: 仓库根。本文件在 ``<root>/tests/unit/`` 下。
_ROOT = Path(__file__).resolve().parents[2]

#: 变异探针的文件名（放在被扫描目录的顶层，用例结束即删）。
_PROBE = "_gate_probe_nonstdlib.py"

#: 一条项目永远不会接受的非标准库 import（`requests` 不在 `sys.stdlib_module_names`）。
_VIOLATION = "import requests\n"


class StdlibOnlyGateTest(unittest.TestCase):
    """The gate must be green on the real repo and red on a real violation."""

    def test_repo_is_stdlib_only(self):
        ok, detail = _stdlib_only_check()
        self.assertTrue(ok, detail)
        self.assertIn("module(s) scanned", detail)

    def test_every_scanned_dir_is_actually_scanned(self):
        # 探针放在哪个被扫目录，门禁都必须看得见 —— 否则「bridge/、tools/ 也扫」
        # 只是一句空话。逐个目录造变异，逐个还原。
        for root_dir in _STDLIB_ONLY_DIRS:
            with self.subTest(root_dir=root_dir):
                probe = _ROOT / root_dir / _PROBE
                probe.write_text(_VIOLATION, encoding="utf-8")
                self.addCleanup(probe.unlink, missing_ok=True)
                ok, detail = _stdlib_only_check()
                self.assertFalse(ok, "%s/ is outside the gate's scan surface" % root_dir)
                self.assertIn("requests", detail)
                self.assertIn(_PROBE, detail)
                probe.unlink()

    def test_relative_and_in_package_imports_are_not_flagged(self):
        source = (
            "from . import sibling\n"
            "from ctl.run import cmd_run\n"
            "import os\n"
            "def f():\n"
            "    from urllib.parse import quote\n"
            "    return quote\n"
        )
        roots = _import_roots(source)
        # 相对 import 被跳过；根名按源码行序给出，包内 ``ctl`` 与标准库第四、五行。
        self.assertEqual(roots, [("ctl", 2), ("os", 3), ("urllib", 5)])


if __name__ == "__main__":
    unittest.main()
