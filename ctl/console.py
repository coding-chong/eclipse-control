"""Gogo (Equinox) console driver -- **not** the IDE's Console view.

This module drives the *OSGi framework console* that an Eclipse-family product
exposes when launched with ``-console``: it starts the process, waits for the
``osgi>`` prompt, writes command lines to the process **stdin**, and collects
what the process writes to **stdout** (`design.md` §3 layer 1, "控制台").

Do not confuse it with the Eclipse *Console view* (the UI part that shows build
and program output) -- that one is read through the bridge's ``ui.console``
method, never here.  Which one you want:

* Gogo console (this file): ``install`` / ``start`` / ``ss`` / ``services`` ...
* Console view (bridge): what a build or a program printed.

Relocated from the slice-1 `_legacy_console.py` harness: the process handling,
prompt wait, command send and output collection are preserved; the previously
hardcoded executable / workspace paths are now constructor parameters (nothing
may be hardcoded to a machine-local scratch directory).
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from typing import List, Optional, Sequence

from .errors import CtlError, DANGEROUS_COMMANDS, DANGEROUS_FLAG_TOKENS

#: The interactive console prompt.  **实测（2026-10-01）：GS32_Studio 用的是 Felix Gogo，
#: 提示符是 `g!` 而不是 Equinox 默认的 `osgi>`**；两个都得认，否则 `install` 会一直等到
#: 超时并报 "console prompt never appeared"（旧产物踩过这个坑）。
#: 匹配规则：行首（可有空白）处的 `g!` 或 `osgi>`。
PROMPT = "osgi>"
PROMPT_RE = re.compile(r"(?:^|[\r\n])[^\S\r\n]*(?:g!|osgi>)[^\S\r\n]")

_CONSOLE_ARGS = ("-data", "%WS%", "-console", "-nosplash", "-nl", "en_US")


def command_is_dangerous(line: str) -> bool:
    """True for the console commands that must be refused by default.

    `design-project.md` §15.4 item 3: ``init`` (uninstall all bundles),
    ``close``, ``shutdown``, ``exit``, ``threads -t``, ``gc``.
    """
    text = (line or "").strip()
    if not text:
        return False
    head = text.split()[0]
    if head in DANGEROUS_COMMANDS:
        return True
    return any(text.startswith(flag) or (" " + flag) in (" " + text) for flag in DANGEROUS_FLAG_TOKENS)


class DangerousCommandRefused(CtlError):
    def __init__(self, line: str):
        super().__init__(
            "disabled",
            "dangerous console command refused: %r; retry: python -m ctl shell --target gs32 --allow-dangerous -c %r"
            % (line.strip(), line.strip()))


class Console:
    """Drive one IDE process through its ``-console`` stdin/stdout channel."""

    def __init__(self, exe: str, workspace: str, configuration: Optional[str] = None,
                 startup_wait: float = 75.0, extra_args: Optional[Sequence[str]] = None,
                 env: Optional[dict] = None, allow_dangerous: bool = False,
                 log_path: Optional[str] = None, cwd: Optional[str] = None):
        self.exe = exe
        self.workspace = workspace
        self.configuration = configuration
        self.startup_wait = startup_wait
        self.extra_args = list(extra_args or [])
        self.env = env
        self.allow_dangerous = allow_dangerous
        self.log_path = log_path
        self.cwd = cwd
        self.proc: Optional[subprocess.Popen] = None
        self.buf = bytearray()
        self._lock = threading.Lock()

    # -- lifecycle --------------------------------------------------------- #

    def args(self) -> List[str]:
        argv = [self.exe, "-data", self.workspace]
        if self.configuration:
            argv += ["-configuration", self.configuration]
        argv += ["-console", "-nosplash", "-nl", "en_US"]
        argv += self.extra_args
        return argv

    def start(self, wait: Optional[float] = None) -> "Console":
        os.makedirs(self.workspace, exist_ok=True)
        if self.log_path:
            parent = os.path.dirname(self.log_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self.proc = subprocess.Popen(
            self.args(),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=0,
            env=self.env, cwd=self.cwd)
        threading.Thread(target=self._reader, daemon=True).start()
        time.sleep(self.startup_wait if wait is None else wait)
        return self

    def _reader(self):
        while True:
            try:
                chunk = self.proc.stdout.read(1)
            except Exception:
                break
            if not chunk:
                break
            self.buf.extend(chunk)
        self._flush_log()

    def _flush_log(self):
        if not self.log_path:
            return
        try:
            with open(self.log_path, "wb") as fh:
                fh.write(bytes(self.buf))
        except OSError:
            pass

    # -- prompt ------------------------------------------------------------ #

    def wait_for_prompt(self, prompt: str = None, timeout: float = 120.0,
                        poll: float = 0.5) -> bool:
        """Wait until the console banner/prompt appears (or ``timeout``).

        默认认 ``g!``（Felix Gogo，GS32 实测）与 ``osgi>``（Equinox）两种；
        传入 ``prompt`` 时按子串匹配（保留旧行为，便于调用方覆盖）。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                text = bytes(self.buf).decode("utf-8", "replace")
            if (prompt in text) if prompt is not None else PROMPT_RE.search(text):
                return True
            if self.proc.poll() is not None:
                return False
            time.sleep(poll)
        return False

    # -- command ----------------------------------------------------------- #

    def cmd(self, line: str, wait: float = 6.0, allow_dangerous: Optional[bool] = None) -> str:
        """Send one console command, return the raw output collected.

        If the IDE has exited, ``WriteFile`` on the dead pipe surfaces as an
        ``OSError`` (EINVAL on Windows) rather than ``BrokenPipeError``; that is
        translated into an actionable error that points at the console log
        instead of leaking a traceback.
        """
        if self.proc is None:
            raise CtlError("internal", "console not started; retry: python -m ctl doctor --target gs32")
        allow = self.allow_dangerous if allow_dangerous is None else allow_dangerous
        if command_is_dangerous(line) and not allow:
            raise DangerousCommandRefused(line)
        if self.proc.poll() is not None:
            raise CtlError("internal", self.diagnose())
        with self._lock:
            self.buf.clear()
        try:
            self.proc.stdin.write(line.encode("utf-8") + b"\n")
            self.proc.stdin.flush()
        except OSError as exc:
            raise CtlError("internal", self.diagnose(exc))
        time.sleep(wait)
        with self._lock:
            text = bytes(self.buf).decode("utf-8", "replace")
        self._flush_log()
        return text

    def diagnose(self, exc: Optional[BaseException] = None) -> str:
        rc = self.proc.poll() if self.proc else None
        tail = ""
        try:
            with self._lock:
                text = bytes(self.buf).decode("utf-8", "replace")
            tail = " ; console tail: %r" % text[-300:]
            if not text and self.log_path and os.path.isfile(self.log_path):
                with open(self.log_path, "r", encoding="utf-8", errors="replace") as fh:
                    tail = " ; console tail: %r" % fh.read()[-300:]
        except OSError:
            pass
        return ("IDE process is not accepting console input (rc=%s%s)%s; log: %s; "
                "retry: python -m ctl doctor --target gs32"
                % (rc, ", %s" % exc if exc else "", tail, self.log_path or "<none>"))

    def read(self) -> str:
        with self._lock:
            return bytes(self.buf).decode("utf-8", "replace")

    def close(self, timeout: float = 20.0):
        if self.proc is None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=timeout)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass

    # -- parsing ----------------------------------------------------------- #

    @staticmethod
    def parse_bundles(ss_output: str) -> List[dict]:
        """Parse `ss` rows.  **实测 GS32/Equinox 的形态是 `id<TAB>STATE<ws>name`（三列）**：

            350\tINSTALLED   eclipse-ctl.bridge_0.1.0

        部分 Equinox 版本会在 state 后多一列 start level（`id state level name`），
        两种都得认 —— 用 `toks[2]` 是不是纯数字来区分。以前写死四列的正则
        (`(\\d+) (\\S+) (\\d+) (\\S+)`) 对本机形态**一行都匹配不上**，导致
        `install_bundle` 读不到 bundle id 并报 "bundle ... not present after install"。
        """
        rows = []
        for line in ss_output.splitlines():
            toks = line.split()
            if len(toks) < 3 or not toks[0].isdigit():
                continue                      # 跳过 "Framework is launched." / "Master=305" / 空行
            state = toks[1]
            rest = toks[2:]
            if len(rest) >= 2 and rest[0].isdigit():
                level, name = int(rest[0]), " ".join(rest[1:])
            else:
                level, name = None, " ".join(rest)
            rows.append({"id": int(toks[0]), "state": state, "level": level, "name": name})
        return rows
