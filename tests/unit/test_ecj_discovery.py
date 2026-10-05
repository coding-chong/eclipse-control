"""``ccs12`` 的 ECJ 发现：必须落在**本产品自己的安装**里，而不是别人的树。

背景（2026-10-06 实测）：CCS 12.8.1 **不带 JDT** —— `ccs/eclipse/plugins` 下没有
`org.eclipse.jdt.core.compiler.batch_*.jar`，整个 `D:/ti/ccs1281` 也没有 javac。旧代码为此
在 `ctl/targets.py` 与 `bridge/build.py` **各写死一条 gs32 的绝对路径**当兜底，于是：

* 本机（同时装了 GS32 与 CCS）全绿；
* 只装 CCS 的机器上 `python -m ctl build --target ccs12` **exit 1**，报错里点名一棵它从未有过的
  GS32 树；`ctl install` 随后在 `find_bridge_jar` 处以 `PrereqNotReady`（exit 2）挡住。

CCS **自带**一个编译器，只是不在 `plugins/`：`<ccs_root>/xdctools_<ver>/packages/xdc/shelf/java/ecj.jar`
（`ccs/install_info/com.ti.xdctools.update.properties` 里 `Featureid=com.ti.xdctools.update`，
`Installdir=../../xdctools_3_62_01_16_core`）。`install_dir` 是 `<ccs_root>/ccs/eclipse`，
所以它**向上两层**。

这条测试用**合成树**（不依赖本机装了 CCS），钉住三件事：

1. 树内没有、祖先树有 ⇒ 必须找到祖先树那份；
2. 两处都没有 ⇒ 必须返回 ``None``（不得退化成"随便找个 jar"）；
3. 搜索面本身由**测试自己的字面量**钉住（`deliverable-shape.md` C10：闸门的测试不得以闸门
   自己的常量为准，否则把常量摘小、测试跟着一起缩，两边都看不见）。

判据的可复跑形态：``python -c "from ctl.targets import _find_ecj; print(_find_ecj(r'D:/ti/ccs1281/ccs/eclipse'))"``。
"""

from __future__ import annotations

import os
import tempfile
import unittest

from ctl.targets import ECJ_ANCESTOR_GLOBS, ECJ_TREE_GLOBS, _find_ecj

#: 搜索面必须**恰好**是这两条（`implement.md` §0 冻结的接口）。以独立字面量写死，
#: 不复用被测常量 —— 见 C10。
_REQUIRED_TREE_GLOBS = ("plugins/org.eclipse.jdt.core.compiler.batch_*.jar",)
_REQUIRED_ANCESTOR_GLOBS = ("../../xdctools_*/packages/xdc/shelf/java/ecj.jar",)

#: 合成树的形状：`<root>/ccs/eclipse` 是 `install_dir`，xdctools 是 `<root>` 的子目录。
_XDCTOOLS_JAR = ("xdctools_3_62_01_16_core", "packages", "xdc", "shelf", "java", "ecj.jar")
_TREE_ECJ = ("plugins", "org.eclipse.jdt.core.compiler.batch_3.36.0.v20231114-0937.jar")


class EcjDiscoveryTest(unittest.TestCase):
    """`_find_ecj` 必须只看本产品的树，且必须能向上找到 XDCtools 那份。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="ecj_discovery_")
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.install_dir = os.path.join(self.root, "ccs", "eclipse")
        os.makedirs(os.path.join(self.install_dir, "plugins"))

    # -- helpers ----------------------------------------------------------- #

    def _write(self, base: str, parts) -> str:
        path = os.path.join(base, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(b"PK\x05\x06" + b"\x00" * 18)  # an empty zip; contents are irrelevant
        return path

    def _xdctools_jar(self) -> str:
        return self._write(self.root, _XDCTOOLS_JAR)

    # -- the search surface is pinned independently (C10) ------------------ #

    def test_search_surface_is_exactly_the_two_surfaces(self):
        # 常量被摘小（例如只剩树内那条）时，这一条必须失败 —— 否则下面两个用例会
        # 跟着一起缩，`xdctools` 静默掉出搜索面而测试仍全绿。
        self.assertEqual(tuple(ECJ_TREE_GLOBS), _REQUIRED_TREE_GLOBS)
        self.assertEqual(tuple(ECJ_ANCESTOR_GLOBS), _REQUIRED_ANCESTOR_GLOBS)

    # -- the two surfaces, in order --------------------------------------- #

    def test_tree_ecj_wins_when_present(self):
        tree = self._write(self.install_dir, _TREE_ECJ)
        self._xdctools_jar()
        self.assertEqual(_find_ecj(self.install_dir), tree)

    def test_falls_back_to_the_products_own_xdctools(self):
        # The CCS case: nothing under plugins/, the compiler is two levels up.
        xdctools = self._xdctools_jar()
        self.assertEqual(_find_ecj(self.install_dir), xdctools)

    def test_returns_none_when_neither_surface_has_one(self):
        # Must NOT degrade into "found some other jar": a bare `None` is what makes
        # `build.py` die with a diagnosis instead of compiling against the wrong thing.
        self.assertIsNone(_find_ecj(self.install_dir))

    def test_unrelated_jar_is_not_mistaken_for_a_compiler(self):
        # A sibling of the tree that is *not* an xdctools layout must not be picked up.
        self._write(self.root, ("xdctools_3_62_01_16_core", "packages", "xdc", "shelf", "other.jar"))
        self._write(self.install_dir, ("plugins", "org.eclipse.osgi_3.17.200.jar"))
        self.assertIsNone(_find_ecj(self.install_dir))


if __name__ == "__main__":
    unittest.main()
