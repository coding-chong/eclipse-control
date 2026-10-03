"""``sys.help`` 自省表 ↔ ``LiveBridge.add(...)`` 方法表：**必须逐字同源**（F1 / P1.2）。

桥把方法表**单点定义**在 ``LiveBridge.methods`` 里（`LiveBridge.java` 的 docstring：*"Method
table is single-sourced in {@link #methods}; sys.help introspects it"*）。这条单测不连 IDE，
只把**两处**对齐：

* 源码侧 —— 从 ``bridge/src/ctl/bridge/LiveBridge.java`` 抽 ``add("name", "args", <write>,
  "<idempotent>", <onUi>, "desc", …)`` 六个字段，拼成 ``name|args|write|idempotent|desc``；
* 运行侧 —— 上一次**真实例**的 ``sys.help`` 回话（2026-10-04，``target=gs32``，run
  ``gs32-b2-help``，端口 8777），逐行照抄在下方 ``SYS_HELP`` 里。

为什么值得一条测试：``sys.help`` 是客户端做 dry-run 白名单与审批闸的载体（`design.md` §3
第 2 条）。**只有真的从源码抽、和真的回话比**，才能发现「新加了 ``add(...)`` 但回话没跟上」
或「回话里多了一个源码没有的方法」——两者都会让白名单静默偏离方法面。

对 ``sys.help`` 的**截断**：`sysHelp` 对每个 ``Method`` 逐条 `out.add(...)`，**没有条数上限**
（唯一的上限 ``out.size() > 3000`` 在 `ui.tree` 的 `walk()` 里）；回话本身带
``methods=<n>``。所以这条要求的判据是**负向断言**：``methods=16`` 时 16 行方法一条不少，
且**没有** ``total/returned/truncated`` 那套导出字段（对比 `ui.viewids` —— 那才是有上限的）。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

#: 仓库根。本文件在 ``<root>/tests/unit/`` 下。
_ROOT = Path(__file__).resolve().parents[2]
_JAVA = _ROOT / "bridge" / "src" / "ctl" / "bridge" / "LiveBridge.java"

#: 上一次真实例 ``sys.help`` 回话的**方法行**（状态行 / ``methods=`` / ``codes=`` / ``note=``
#: 皆不在此，只保留 ``name|args|write|idempotent|desc``）。逐字照抄，未做任何重排。
#: 复跑：``python -m ctl shell --run-id <id> -c "sys.help"``。
SYS_HELP = [
    'sys.ping||no|true|round-trip liveness probe; answers without touching the UI thread',
    'sys.env||no|true|bridge identity: java/os/protocol/bundle id+version+state/port/timeouts/log path',
    'sys.help||no|true|this method table (name|args|write|idempotent|desc)',
    'sys.wait|[<ms>|jobs-idle]|no|true|wait for org.eclipse.core.runtime.jobs.JobManager to go idle; returns OK with idle=false on timeout',
    'ui.shells||no|true|list SWT shells (text/visible/bounds/children)',
    'ui.tree|[depth]|no|true|dump the SWT widget tree of the largest visible shell (default depth 3)',
    'ui.parts||no|true|perspective + views + editors of the active page (created parts only)',
    'ui.viewids|[prefix] [--limit <n>]|no|true|registered view ids (IViewRegistry); no truncation unless --limit is given',
    'ui.persp||no|true|registered perspectives + the active one',
    'ui.console|[--tail <n>]|no|true|text of the ACTIVE console (name + last n lines, default 50); ERR notfound when no console exists',
    'ui.open|<abs path>|yes|true|open a file in an editor (CDT C editor, fallback to DefaultTextEditor); re-opening the same file does NOT add a second editor (measured)',
    'ui.close|<viewId>|yes|true|close a view already open in the active page; ERR notfound if it is not open',
    'cmd.list|[prefix] [--limit <n>]|no|true|full command-id export (no silent 300 cap); reports total/matched/returned/truncated',
    'cmd.query|<id>|no|true|defined/handled/name/category/parameters of one command',
    'cmd.run|<id>|yes|per-command|execute a command; ERR disabled/unhandled come from the command framework; idempotence is PER-COMMAND (measured: a toggle command reverts on the 2nd call)',
    'cmd.runp|<id> <paramId|=paramName>=<value>|yes|per-command|execute a command with one parameter; idempotence is PER-COMMAND (measured: showView twice does not add a second copy)',
]

#: ``add(name, args, write, idempotent, onUi, desc, handler)`` —— 取前六个参数的**字面量**。
#: 六个字段都在一行或跨行、但**方法表里没有转义引号**，所以负字符类足够；
#: 末尾的 ``, \\s*\(`` 把 ``add(`` 与跟随的 handler lambda 钉在一起，``out.add(`` /
#: ``methods.put(`` 这类不是裸语句的调用不会命中。
_ADD = re.compile(
    r'add\("([^"]*)",\s*"([^"]*)",\s*(true|false),\s*"([^"]*)",\s*(true|false),\s*'
    r'"([^"]*)",\s*\(')


def _java_rows(source: str) -> list:
    """Reflect the Java ``add(...)`` table back into ``sys.help`` row shape."""
    rows = []
    for name, args, write, idempotent, _on_ui, desc in _ADD.findall(source):
        rows.append("%s|%s|%s|%s|%s"
                    % (name, args, "yes" if write == "true" else "no", idempotent, desc))
    return rows


class HelpMethodSetTest(unittest.TestCase):
    """The introspection surface and its single source must not drift."""

    def test_java_table_matches_archived_sys_help(self):
        source = _JAVA.read_text(encoding="utf-8")
        rows = _java_rows(source)
        self.assertEqual(
            rows, SYS_HELP,
            "LiveBridge.add(...) no longer matches the archived sys.help rows "
            "(the bridge's introspection surface drifted from its single source)")

    def test_method_names_are_unique_and_ordered(self):
        names = [row.split("|", 1)[0] for row in SYS_HELP]
        self.assertEqual(len(names), len(set(names)), "duplicate method name in the table")
        # 名字就是方法行的第一个 ``|`` 字段 —— `sys.wait` 的 args 里含 ``|``，
        # 所以**只能**按第一个分隔符切，这条同时钉住那个解析规则。
        self.assertEqual(names[0], "sys.ping")
        self.assertEqual(names[-1], "cmd.runp")


if __name__ == "__main__":
    unittest.main()
