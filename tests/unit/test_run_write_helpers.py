"""单元层：`ctl run` 库形态写助手的 dry-run 默认（批次 0.3）。

`act_click_button` 之后新增了 `act_send_keys` / `act_set_text`；三者形态必须一致：
``yes=False`` 默认**只打印 dry-run**、绝不落到工具的写调用，且寻址必须**先枚举**
（写下去之前就 fail closed）。这里不连真 IDE、不弹窗：用一个假 client 架住端点，
用一个被替换的 `_tool` 返回固定的枚举负载，让唯一性成立或故意不成立。

判据：
* 不带 ``yes`` ⇒ 返回 ``DRY-RUN`` 且**没有任何** ``-Action`` 写调用；
* 带 ``yes`` ⇒ 才出现 ``-Action`` 写调用；
* 同类多命中且没给 ``index`` ⇒ ``UsageError``，且**一个字节都没写出去**。
"""

import shutil
import unittest

import ctl.run as run
from ctl.errors import UsageError

LISTING = (
    "window hwnd=0x1\n"
    "-- child windows --\n"
    '  hwnd=0x2 class=Edit vis=True text="" rect=0,0,10,10\n'
)
SECOND_EDIT = '  hwnd=0x3 class=Edit vis=True text="" rect=0,0,10,10\n'


class _FakeClient:
    run_root = "."
    run_id = "fake-run"

    def request(self, req, timeout=None):  # pragma: no cover - must not be reached
        raise AssertionError("a dry-run must not ask the bridge: %s" % req)


class _Recorder:
    """A `_tool` stand-in that records argv and returns one fixed listing."""

    def __init__(self, listing=LISTING):
        self.listing = listing
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        return (0, self.listing)


class RunWriteHelperDryRun(unittest.TestCase):
    def setUp(self):
        if not shutil.which("pwsh"):
            self.skipTest("pwsh not available (element-addressed input needs it)")
        self.tool = _Recorder()
        self._tool = run._tool
        self._pid = run.resolve_pid
        run._tool = self.tool
        run.resolve_pid = lambda root, rid, on_error=None: 4242

    def tearDown(self):
        run._tool = self._tool
        run.resolve_pid = self._pid

    def _namespace(self):
        return run._make_namespace(_FakeClient(), run._DoorState(run_id="fake-run"))

    def _wrote(self):
        return any("-Action" in call for call in self.tool.calls)

    def test_act_send_keys_defaults_to_dry_run(self):
        out = self._namespace()["act_send_keys"]("RETURN", title="Fake Window")
        self.assertTrue(out.startswith("DRY-RUN "), out)
        self.assertIn("send-keys", out)
        self.assertFalse(self._wrote(), "dry-run must not send the key")

    def test_act_set_text_defaults_to_dry_run(self):
        out = self._namespace()["act_set_text"]("hello", title="Fake Window")
        self.assertTrue(out.startswith("DRY-RUN "), out)
        self.assertIn("set-text", out)
        self.assertFalse(self._wrote(), "dry-run must not set the text")

    def test_yes_reaches_the_write_call(self):
        self._namespace()["act_set_text"]("hello", title="Fake Window", yes=True)
        self.assertTrue(self._wrote(), "yes=True must reach the tool's write path")

    def test_ambiguous_class_fails_closed_before_any_write(self):
        run._tool = _Recorder(LISTING + SECOND_EDIT)
        with self.assertRaises(UsageError):
            self._namespace()["act_set_text"]("hello", title="Fake Window", yes=True)
        self.assertFalse(self._wrote(), "an ambiguous target must not be written")


if __name__ == "__main__":
    unittest.main()
