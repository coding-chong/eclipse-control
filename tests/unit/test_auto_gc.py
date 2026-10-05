"""单元层：``ctl.lifecycle.auto_gc`` —— 跨 run 回收的形态与八条护栏。

形状契约（``deliverable-shape.md`` **C10**）：期望值全部是**本文件自己的字面量**，
不迭代 ``auto_gc()`` 的常量或内部结构 —— 否则「分组悄悄变成全局」这类退化
测不出来（被守的规则一改，测试跟着一起松，两边都看不见）。

每个被守护的入口都配一条**变异**（``implement.md`` §S7 的账本 M1–M6）：
把那条规则拆掉，本文件必须**报红**；装回去，必须**报绿**。

全程只碰临时 ``run_root`` 的目录布局：不连桥、不开窗、不看帧（R5）。
``pid_alive`` 默认全部为假，宿主机上真在跑的进程不得渗进判据。
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from ctl.client import write_endpoint
from ctl.lifecycle import auto_gc

#: mtime 的绝对基准秒（1_700_000_000 = 2023-11-14）。用绝对量而非 ``time.time()``，
#: 排序才是确定的：**数值越大越新**。
_BASE = 1_700_000_000.0


class _AutoGcCase(unittest.TestCase):
    """一块临时 ``run_root``，外加一个「谁的 pid 活着」的开关。"""

    def setUp(self) -> None:
        self.root = tempfile.mkdtemp(prefix="eclipse-ctl-auto-gc-")
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        #: 只有在这里面的 pid 才算活着 —— 否则宿主机进程表会把判据变成环境相关。
        self.live_pids: set = set()
        patcher = mock.patch("ctl.lifecycle.pid_alive",
                             side_effect=lambda pid: pid in self.live_pids)
        patcher.start()
        self.addCleanup(patcher.stop)

    # -- helpers ----------------------------------------------------------- #

    def _mk(self, name: str, target: str = "", mtime: float = _BASE,
            pid: int = None) -> str:
        """一个 run 目录 + 它的 ``endpoint.json``；``target=""`` ⇒ 老 run（无 target）。"""
        path = os.path.join(self.root, name)
        os.makedirs(path)
        write_endpoint(self.root, name, 8777, pid=pid, target=target)
        os.utime(path, (mtime, mtime))
        return path

    def _mk_bare(self, name: str, mtime: float = _BASE, payload: str = None) -> str:
        """没有 ``endpoint.json``（``payload=None``）或写坏了的那种 run 目录。"""
        path = os.path.join(self.root, name)
        os.makedirs(path)
        if payload is not None:
            with open(os.path.join(path, "endpoint.json"), "w", encoding="utf-8") as fh:
                fh.write(payload)
        os.utime(path, (mtime, mtime))
        return path

    def _on_disk(self) -> list:
        return sorted(os.listdir(self.root))


class KeepWindowTest(_AutoGcCase):
    """护栏：保留单位是 **target**，不是全局 ``run_root``（M1 守这一条）。"""

    def test_keeps_three_per_target_not_three_overall(self) -> None:
        for step, name in enumerate(["gs32-a", "gs32-b", "gs32-c", "gs32-d", "gs32-e"]):
            self._mk(name, "gs32", mtime=_BASE + step)
        for step, name in enumerate(["ccs12-a", "ccs12-b", "ccs12-c", "ccs12-d", "ccs12-e"]):
            self._mk(name, "ccs12", mtime=_BASE + step)

        result = auto_gc(self.root, 3)

        # 10 个 run、keep=3：全局口径会删 7 个，每 target 口径只删 2 个。
        # 顺序是确定的：target 按名字升序，group 内按 mtime **降序**（与 `gc()` 同形）。
        self.assertEqual(result["removed"], ["ccs12-b", "ccs12-a", "gs32-b", "gs32-a"])
        self.assertEqual(self._on_disk(),
                         ["ccs12-c", "ccs12-d", "ccs12-e", "gs32-c", "gs32-d", "gs32-e"])
        self.assertEqual(result["failed"], [])

    def test_a_single_target_is_pruned_the_same_way(self) -> None:
        for step, name in enumerate(["gs32-a", "gs32-b", "gs32-c", "gs32-d"]):
            self._mk(name, "gs32", mtime=_BASE + step)

        result = auto_gc(self.root, 3)

        self.assertEqual(result["removed"], ["gs32-a"])
        self.assertEqual(self._on_disk(), ["gs32-b", "gs32-c", "gs32-d"])


class UnclassifiedImmunityTest(_AutoGcCase):
    """护栏 3：判不出 target 的一律不删（M3 守这一条）。

    判不出有四种形状：没 target 字段 / 没有 ``endpoint.json`` / JSON 写坏了 /
    JSON 合法但没有 ``port`` —— 四种都必须免疫，且 **keep=1**（最激进的非拒绝值）
    下也免疫：老 run 比 keep 数还多，仍然一个都不许动。
    """

    def test_legacy_and_unreadable_runs_are_never_collected(self) -> None:
        self._mk("gs32-a", "gs32", mtime=_BASE + 1)
        self._mk("gs32-b", "gs32", mtime=_BASE + 2)
        self._mk("legacy-notarget", "", mtime=_BASE - 10)            # 有文件，没 target 字段
        self._mk_bare("legacy-noendpoint", mtime=_BASE - 20)          # 连文件都没有
        self._mk_bare("legacy-corrupt", mtime=_BASE - 30,             # 文件写坏了
                      payload="{ this is not json")
        self._mk_bare("legacy-noport", mtime=_BASE - 40,              # 合法 JSON，缺 port
                      payload='{"pid": 1}')

        result = auto_gc(self.root, 1)

        self.assertEqual(result["removed"], ["gs32-a"])
        self.assertEqual(sorted(result["skipped_unclassified"]),
                         ["legacy-corrupt (no target recorded)",
                          "legacy-noendpoint (no target recorded)",
                          "legacy-noport (no target recorded)",
                          "legacy-notarget (no target recorded)"])
        self.assertEqual(self._on_disk(),
                         ["gs32-b", "legacy-corrupt", "legacy-noendpoint",
                          "legacy-noport", "legacy-notarget"])


class CurrentRunTest(_AutoGcCase):
    """护栏 2：收工的那个 run 永不删（M2 守这一条）。"""

    def test_current_run_is_protected_even_when_it_is_the_oldest(self) -> None:
        for step, name in enumerate(["gs32-a", "gs32-b", "gs32-c", "gs32-d"]):
            self._mk(name, "gs32", mtime=_BASE + step)   # gs32-a 最旧 = 本来的候选

        result = auto_gc(self.root, 3, current_run_id="gs32-a")

        self.assertEqual(result["removed"], [])
        self.assertEqual(result["protected"], ["gs32-a (current run)"])
        self.assertIn("gs32-a", self._on_disk())

    def test_current_run_still_occupies_a_keep_slot(self) -> None:
        # 4 个 run、keep=3：当前 run 若不算在保留窗口里，就会「一个都不删」——
        # 那等于悄悄把它自己的 target 少留一个。
        for step, name in enumerate(["gs32-a", "gs32-b", "gs32-c", "gs32-d"]):
            self._mk(name, "gs32", mtime=_BASE + step)   # gs32-d 最新

        result = auto_gc(self.root, 3, current_run_id="gs32-d")

        self.assertEqual(result["removed"], ["gs32-a"])
        self.assertEqual(result["protected"], ["gs32-d (current run)"])
        self.assertEqual(self._on_disk(), ["gs32-b", "gs32-c", "gs32-d"])


class LiveRunTest(_AutoGcCase):
    """护栏 1：活着的 run 永远跳过，且**不阻断**同一个 target 里的其它候选（M4）。"""

    def test_live_candidate_is_skipped_and_the_rest_still_go(self) -> None:
        self._mk("gs32-a", "gs32", mtime=_BASE + 1, pid=4242)   # 候选，但活着
        self._mk("gs32-b", "gs32", mtime=_BASE + 2, pid=4243)   # 候选
        for step, name in enumerate(["gs32-c", "gs32-d", "gs32-e"]):
            self._mk(name, "gs32", mtime=_BASE + 3 + step)
        self.live_pids.add(4242)

        result = auto_gc(self.root, 3)

        self.assertEqual(result["skipped_live"], ["gs32-a (pid 4242 still running)"])
        self.assertEqual(result["removed"], ["gs32-b"])
        self.assertIn("gs32-a", self._on_disk())
        self.assertNotIn("gs32-b", self._on_disk())


class KeepFloorTest(_AutoGcCase):
    """护栏 4：``keep < 1`` 不做，只警告（M5）。"""

    def test_keep_below_one_deletes_nothing_and_warns(self) -> None:
        for step, name in enumerate(["gs32-a", "gs32-b", "gs32-c"]):
            self._mk(name, "gs32", mtime=_BASE + step)

        for keep in (0, -1):
            with self.subTest(keep=keep):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    result = auto_gc(self.root, keep)
                self.assertEqual(result["removed"], [])
                self.assertEqual(result["skipped_live"], [])
                self.assertEqual(result["skipped_unclassified"], [])
                self.assertEqual(result["protected"], [])
                self.assertEqual(result["failed"], [])
                self.assertIn("keep=%d" % keep, err.getvalue())
                self.assertIn("WARN: auto_gc", err.getvalue())
                self.assertEqual(self._on_disk(), ["gs32-a", "gs32-b", "gs32-c"])


class FailClosedTest(_AutoGcCase):
    """护栏 5：任何异常 ⇒ 零删除，且**不向外抛**（M6）。"""

    def test_an_exception_while_classifying_deletes_nothing_and_does_not_raise(self) -> None:
        for step, name in enumerate(["gs32-a", "gs32-b", "gs32-c", "gs32-d"]):
            self._mk(name, "gs32", mtime=_BASE + step)

        err = io.StringIO()
        # 异常注入点**不是**逐 run 的 ``discover_endpoint``（那一条按设计降级成
        # unclassified，见 UnclassifiedImmunityTest），也不是活 run 检查（那一条
        # 有自己的用例）—— 是每个 run 都会走、且在**任何删除之前**的那一步。
        with mock.patch("os.path.getmtime", side_effect=OSError("boom")):
            with contextlib.redirect_stderr(err):
                result = auto_gc(self.root, 3)      # 不得抛出

        self.assertEqual(result["removed"], [])
        self.assertEqual(self._on_disk(), ["gs32-a", "gs32-b", "gs32-c", "gs32-d"])
        self.assertIn("WARN: auto_gc", err.getvalue())
        self.assertIn("boom", err.getvalue())


if __name__ == "__main__":
    unittest.main()
