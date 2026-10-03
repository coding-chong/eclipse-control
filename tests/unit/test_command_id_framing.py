"""单元层：`cmd.list` 的 id 块框定契约（`ctl.parse.command_ids`）。

这个洞曾经只修在**一个**调用方上 —— `ctl/__main__.py:_fetch_command_ids` 修好了，
`ctl/run.py` 的门还留着旧的 `"." in token` 启发式，于是在 CCS 上库返回 805、桥自报
807（丢的正是 `undo` / `redo` 两条**不带点**的合法 id）。GS32 的命令恰好全带点，
所以「两个目标都跑过」也照样漏掉。

所以这里不连真 IDE，用手写的合成负载把契约钉死：

* 块内逐行照抄 —— 不带点的 id 一个都不能少（这才是 failing-before / passing-after 的载体）；
* 结算行 / `handlerOnly` / `caveat` 行，一个都不能混进 ids；
* 两个调用方对同一段负载必须给出**一致**的 ids。

负载形状逐字抄自桥的真实回话（`ctl/__main__.py` 的 docstring 与 `research` 记录）。
"""

import unittest

from ctl.parse import command_ids

#: 真实回话的负载（`Response.payload`：状态行与终止行之间的正文）。
PAYLOAD = [
    "ICommandService via IWorkbench.getService -> true",
    "  org.eclipse.ui.file.save",
    "  org.eclipse.ui.edit.undo",
    "  undo",
    "  redo",
    "  com.ti.ccstudio.debug.launch",
    "  com.gs.chipsetting.commands.config",
    "definedCommandIds total=6 matched(prefix=)=6 returned=6 truncated=false",
    "handlerOnly registry=ok total=1 inactiveContributors=0 (handler without a <command> declaration; not in getDefinedCommandIds)",
    "  + com.gs.chipsetting.commands.opthandler",
    "caveat=handler-only ids cannot be enumerated through ICommandService; this section is a best-effort scan of plugin.xml",
]

#: 块内那 6 行，逐行照抄 —— 顺序即回话里的顺序。
IDS = [
    "org.eclipse.ui.file.save",
    "org.eclipse.ui.edit.undo",
    "undo",
    "redo",
    "com.ti.ccstudio.debug.launch",
    "com.gs.chipsetting.commands.config",
]
HANDLER_ONLY = ["com.gs.chipsetting.commands.opthandler"]
SETTLEMENT = PAYLOAD[7]


class _FakeResponse:
    """Just enough of `ctl.client.Response` for both callers."""

    def __init__(self, payload):
        self.payload = list(payload)
        self.status_line = "OK"
        self.ok = True
        self.raw = "\n".join(["OK"] + list(payload) + ["END"])


class _FakeClient:
    def __init__(self, payload):
        self.payload = list(payload)

    def request(self, req, timeout=None):
        return _FakeResponse(self.payload)


class _FakeTarget:
    name = "fake"


class CommandIdFraming(unittest.TestCase):
    """`ctl.parse.command_ids` 的契约；调用方一致性也在这里对拍。"""

    # -- 主路径：不带点的 id 必须活着 -------------------------------------- #

    def test_dotless_ids_survive_next_to_dotted_ones(self):
        ids, _handler_only = command_ids(PAYLOAD)
        self.assertEqual(ids, IDS)
        self.assertIn("undo", ids)
        self.assertIn("redo", ids)
        # 块内行数 = 返回条数：一行都不能被启发式吞掉。
        self.assertEqual(len(ids), 6)

    def test_the_dot_heuristic_would_have_dropped_them(self):
        """这就是 failing-before：点号判据会把 `undo` / `redo` 静默删掉。"""
        dot_filtered = [i for i in IDS if "." in i]
        self.assertEqual(len(dot_filtered), 4)
        self.assertNotIn("undo", dot_filtered)
        self.assertNotIn("redo", dot_filtered)
        ids, _ = command_ids(PAYLOAD)
        self.assertGreaterEqual(len([i for i in ids if "." not in i]), 2)

    # -- 三类非 id 的行都不许漏进去 ---------------------------------------- #

    def test_settlement_row_is_not_an_id(self):
        ids, _handler_only = command_ids(PAYLOAD)
        self.assertNotIn(SETTLEMENT, ids)
        self.assertEqual([i for i in ids if "=" in i], [])
        self.assertEqual([i for i in ids if "definedCommandIds" in i], [])

    def test_handler_only_rows_are_returned_separately(self):
        ids, handler_only = command_ids(PAYLOAD)
        self.assertEqual(handler_only, HANDLER_ONLY)
        for command_id in handler_only:
            self.assertNotIn(command_id, ids)

    def test_caveat_line_never_reaches_either_list(self):
        ids, handler_only = command_ids(PAYLOAD)
        stray = [row for row in ids + handler_only if "caveat" in row]
        self.assertEqual(stray, [])

    # -- 两个调用方对同一段负载给出一致结果 -------------------------------- #

    def test_both_callers_agree_with_the_reader(self):
        expected_ids, expected_handler = command_ids(PAYLOAD)

        from ctl.__main__ import _fetch_command_ids

        main_ids, total, main_handler = _fetch_command_ids(
            _FakeClient(PAYLOAD), _FakeTarget(), "fake-run")
        self.assertEqual(main_ids, expected_ids)
        self.assertEqual(main_handler, expected_handler)
        # `total=` 仍由 __main__ 自己认结算行解析；语义不许动。
        self.assertEqual(total, 6)

        from ctl.run import _DoorState, _make_namespace

        namespace = _make_namespace(_FakeClient(PAYLOAD), _DoorState(run_id="fake-run"))
        self.assertEqual(namespace["commands"](), expected_ids)

    # -- 兜底：签名行缺失 / 顺序颠倒时保守，但不许按点号过滤 ---------------- #

    def test_missing_head_never_yields_the_settlement_row(self):
        payload = [line for line in PAYLOAD if "ICommandService" not in line]
        ids, _handler_only = command_ids(payload)
        self.assertNotIn(SETTLEMENT, ids)
        self.assertEqual([i for i in ids if " " in i or "=" in i], [])
        self.assertIn("undo", ids)

    def test_reversed_signature_lines_fall_back_conservatively(self):
        payload = [PAYLOAD[7]] + PAYLOAD[1:7] + [PAYLOAD[0]]
        ids, _handler_only = command_ids(payload)
        self.assertNotIn(SETTLEMENT, ids)
        self.assertEqual([i for i in ids if " " in i or "=" in i], [])
        self.assertEqual(ids, IDS)


if __name__ == "__main__":
    unittest.main()
