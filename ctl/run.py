"""``python -m ctl run`` -- the one door: a Python script on stdin.

Shape (see `browser-harness`): one command, the script arrives on stdin, the
library is already in the namespace, and a raw-protocol escape hatch sits next to
the typed sugar.  Nothing here invents bridge behaviour -- every helper is a thin
wrapper over :mod:`ctl.client` (``run`` / ``resp``), which is itself the same
client every other subcommand uses.

Exit codes follow `design-obs-ux.md` §14.3::

    0  the script finished and every bridge response was OK
    1  the script raised, or some bridge response carried an ``ERR``
    2  a prerequisite was not ready (no instance with --no-start, unknown
       target, ``pwsh`` missing for the element-addressed input helper)

Diagnostics (the connect-or-start decision, tracebacks, ``ERR`` lines) go to
stderr; the script's own ``print()`` owns stdout.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from . import screen as _screen
from . import shadow as _shadow
from .client import Client, discover_endpoint, resolve_pid
from .errors import CtlError, NotFoundError, PrereqNotReady, UsageError
from .lifecycle import REPO_ROOT, install as lifecycle_install, latest_run_id, make_run_id
from .parse import command_ids
from .targets import Config, load as load_config

#: One re-runnable command per error, the way every other CLI error carries one.
RUN_RETRY = "retry: python -m ctl run --target gs32 < script.py"

_CLICK_TOOL = os.path.join(REPO_ROOT, "tools", "win-click-button.ps1")
_SEND_TOOL = os.path.join(REPO_ROOT, "tools", "win-send-input.ps1")


# --------------------------------------------------------------------------- #
# Typed views
# --------------------------------------------------------------------------- #

@dataclass
class Parts:
    """The parsed ``ui.parts`` payload (``perspective`` / ``views`` / ``editors``)."""

    perspective: Optional[str]
    views: List[str]
    editors: Optional[int]
    status: str = ""
    raw: str = ""


#: The door's per-run state; ``err`` is set by ``run``/``resp``/sugar on any ERR.
class _DoorState:
    def __init__(self, run_id: str = "", port: int = 0) -> None:
        self.err = False
        self.started = False
        self.run_id = run_id
        self.port = port


# --------------------------------------------------------------------------- #
# The script namespace
# --------------------------------------------------------------------------- #

def _make_namespace(client: Client, state: _DoorState) -> Dict[str, Any]:
    """The names a script body (and a ``--helpers`` file) sees.

    Every helper closes over the one connected :class:`Client`; ``run``/``resp``
    record the ERR flag that turns into exit code 1.
    """

    def run(request: str, timeout: Optional[float] = None) -> str:
        response = client.request(str(request), timeout)
        if not response.ok:
            state.err = True
        return response.raw

    def resp(request: str, timeout: Optional[float] = None) -> Tuple[str, List[str], str]:
        response = client.request(str(request), timeout)
        if not response.ok:
            state.err = True
        return (response.status_line, list(response.payload), response.raw)

    def _body(request: str, timeout: Optional[float] = None) -> str:
        _status, payload, _raw = resp(request, timeout)
        return "\n".join(payload)

    def parts() -> Parts:
        status, payload, _raw = resp("ui.parts")
        text = "\n".join(payload)
        persp = re.search(r"^perspective id=(\S+)", text, re.M)
        editors = re.search(r"^editors=(\d+)", text, re.M)
        return Parts(perspective=persp.group(1) if persp else None,
                     views=re.findall(r"^\s*view id=(\S+)", text, re.M),
                     editors=int(editors.group(1)) if editors else None,
                     status=status, raw=text)

    def viewids(prefix: str = "") -> List[str]:
        text = _body("ui.viewids" + ((" " + prefix) if prefix else ""))
        return re.findall(r"^\s*view id=(\S+)", text, re.M)

    def persp() -> Dict[str, Any]:
        text = _body("ui.persp")
        count = re.search(r"^perspectives=(\d+)", text, re.M)
        active = re.search(r"^active=(\S+)", text, re.M)
        return {"active": active.group(1) if active else None,
                "perspectives": int(count.group(1)) if count else None,
                "ids": re.findall(r"^\s*persp id=(\S+)", text, re.M),
                "raw": text}

    def tree(depth: int) -> str:
        return _body("ui.tree %d" % int(depth))

    def commands(prefix: str = "") -> List[str]:
        """The ``cmd.list`` ids -- parsed by the one authoritative reader.

        The framing rules live in `ctl.parse.command_ids` (this door and the
        ``commands`` subcommand share them; `measurement-hygiene.md` §13.7).
        They used to be duplicated here, and this copy kept a ``"." in token``
        test that silently dropped the dot-less ids CCS registers (`undo` /
        `redo`): 805 here against the bridge's ``returned=807``.
        """
        text = _body("cmd.list" + ((" " + prefix) if prefix else ""))
        ids, _handler_only = command_ids(text.splitlines())
        return ids

    def cmd(id: str, yes: bool = False, **params: Any) -> str:
        request = ("cmd.runp %s %s" % (id, " ".join("%s=%s" % kv for kv in params.items()))
                   if params else "cmd.run %s" % id)
        if not yes:
            return "DRY-RUN %s" % request
        return run(request)

    def open_file(path: str, yes: bool = False) -> str:
        request = "ui.open %s" % path
        if not yes:
            return "DRY-RUN %s" % request
        return run(request)

    def close_view(id: str, yes: bool = False) -> str:
        request = "ui.close %s" % id
        if not yes:
            return "DRY-RUN %s" % request
        return run(request)

    def shadow(seq: Optional[int] = None):
        cfg = _shadow.for_client(client)
        if seq is None:
            return _shadow.summary(cfg)
        return _shadow.find(cfg, int(seq))

    def act_click_button(text: str, case: Optional[bool] = None,
                         title: Optional[str] = None, yes: bool = False) -> str:
        return _click_button(client, text, case, title, yes)

    def act_send_keys(key: str, title: Optional[str] = None, class_: str = "Edit",
                      index: Optional[int] = None, yes: bool = False) -> str:
        return _send_input(client, "send-keys", title, class_, index, key, None, yes)

    def act_set_text(text: str, title: Optional[str] = None, class_: str = "Edit",
                     index: Optional[int] = None, yes: bool = False) -> str:
        return _send_input(client, "set-text", title, class_, index, None, text, yes)

    def log(msg: Any) -> None:
        print(str(msg), file=sys.stderr, flush=True)

    return {
        "client": client,
        "run": run,
        "resp": resp,
        "parts": parts,
        "viewids": viewids,
        "persp": persp,
        "tree": tree,
        "commands": commands,
        "cmd": cmd,
        "open_file": open_file,
        "close_view": close_view,
        "shadow": shadow,
        "act_click_button": act_click_button,
        "act_send_keys": act_send_keys,
        "act_set_text": act_set_text,
        "log": log,
        "__name__": "__ctl_run__",
    }


# --------------------------------------------------------------------------- #
# Element-addressed input (the one helper that leaves Python)
# --------------------------------------------------------------------------- #

def _tool(argv: List[str]) -> Tuple[int, str]:
    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return (proc.returncode, (proc.stdout or "") + (proc.stderr or ""))


def _button_rows(listing: str, text: str, case: Optional[bool]) -> List[str]:
    """The *visible* Button records whose label matches ``text``.

    Parsed through :func:`ctl.screen.child_record`, so a label carrying a line break
    cannot contribute a second (or phantom) Button, and an invisible Button cannot
    make a unique label look ambiguous -- the tool's own ``MatchButtons`` filters on
    ``IsWindowVisible``, and the ordinal has to be derived from the same set.
    """
    rows: List[str] = []
    for line in listing.splitlines():
        record = _screen.child_record(line)
        if record is None or record[1] != "Button" or not record[2]:
            continue
        label = record[3]
        if (text in label) if case else (text.lower() in label.lower()):
            rows.append(line.strip())
    return rows


def _window_title(client: Client) -> str:
    """The shell to click in -- the visible dialog when one is up, else the main shell.

    The tool needs a non-empty ``-TitleLike``, and (measured, `boundaries.md`
    §A6b) the real workbench main window carries no Button: the Buttons live in
    dialogs, which are separate shells of the same process.
    """
    payload = client.request("ui.shells").payload
    rows = re.findall(
        r'shell text="([^"]*)" vis=true b=Rectangle \{(-?\d+), (-?\d+), (\d+), (\d+)\}',
        "\n".join(payload))
    if not rows:
        raise PrereqNotReady("no visible shell in run %s to address; %s"
                             % (client.run_id or "<none>", RUN_RETRY))
    main = max(rows, key=lambda row: int(row[3]) * int(row[4]))
    others = [row for row in rows if row is not main]
    return (max(others, key=lambda row: int(row[3]) * int(row[4])) if others else main)[0]


def _click_button(client: Client, text: str, case: Optional[bool],
                  title: Optional[str], yes: bool) -> str:
    """Click a Button by label inside one of the run's own windows (``BM_CLICK``).

    The window is addressed inside the run's process (dialogs belong to it too),
    so nothing depends on where it sits or on which window has the foreground.
    ``case=True`` demands a case-sensitive label match before anything is sent.
    """
    if not os.path.isfile(_CLICK_TOOL):
        raise PrereqNotReady("missing tool: %s; %s" % (_CLICK_TOOL, RUN_RETRY))
    pwsh = shutil.which("pwsh")
    if not pwsh:
        raise PrereqNotReady("pwsh not found (PowerShell 5.1 is not supported); %s" % RUN_RETRY)
    pid = resolve_pid(client.run_root, client.run_id)
    if not pid:
        raise PrereqNotReady(
            "run %s records no pid, so the IDE window cannot be addressed; %s"
            % (client.run_id or "<none>", RUN_RETRY))
    window = title if title else _window_title(client)
    base = [pwsh, "-NoProfile", "-NonInteractive", "-File", _CLICK_TOOL,
            "-TitleLike", window, "-ProcId", str(pid)]
    code, listing = _tool(base + ["-ListOnly"])
    if code != 0:
        raise NotFoundError("no visible window matching %r in pid %d (pass title=...); %s"
                            % (window, pid, RUN_RETRY))
    matches = _button_rows(listing, text, case)
    if not matches:
        raise NotFoundError("no visible Button matching %r in pid %d; %s" % (text, pid, RUN_RETRY))
    if len(matches) > 1:
        raise UsageError("ambiguous: %d Buttons match %r (addressing must be unique); %s"
                         % (len(matches), text, RUN_RETRY))
    if not yes:
        return "DRY-RUN click-button text=%r pid=%d title=%r" % (text, pid, window)
    code, output = _tool(base + ["-Text", text])
    if code != 0:
        raise CtlError("unhandled", "click-button failed: %s; %s" % (output.strip(), RUN_RETRY))
    return output.rstrip()


def _send_input(client: Client, action: str, title: Optional[str], class_: str,
                index: Optional[int], key: Optional[str], text: Optional[str],
                yes: bool) -> str:
    """Send a key or set a control's text through the run's own process.

    Keys go out as ``WM_KEYDOWN``/``WM_KEYUP`` and text as ``WM_SETTEXT`` to the
    addressed child's own HWND (`design-project.md` §18.3).  The class must resolve
    to exactly one *visible* child unless ``index`` pins one -- the same rule
    ``act_click_button`` applies to a label, and the same set the tool derives its
    own ordinal from, checked **before** anything is typed so an ambiguous field is
    never silently written.
    """
    if not os.path.isfile(_SEND_TOOL):
        raise PrereqNotReady("missing tool: %s; %s" % (_SEND_TOOL, RUN_RETRY))
    pwsh = shutil.which("pwsh")
    if not pwsh:
        raise PrereqNotReady("pwsh not found (PowerShell 5.1 is not supported); %s" % RUN_RETRY)
    # Usage errors first: a missing key/text is the caller's mistake and must not be
    # masked by "this run records no pid" (the order the CLI layer had, kept here so
    # the fail-closed rule does not depend on which entry point is used).
    if action == "send-keys" and not key:
        raise UsageError("send-keys needs key=... (RETURN / TAB / F5 / A ...); %s" % RUN_RETRY)
    if action != "send-keys" and text is None:
        raise UsageError("set-text needs text=...; %s" % RUN_RETRY)
    pid = resolve_pid(client.run_root, client.run_id)
    if not pid:
        raise PrereqNotReady(
            "run %s records no pid, so the IDE window cannot be addressed; %s"
            % (client.run_id or "<none>", RUN_RETRY))
    window = title if title else _window_title(client)
    if action == "send-keys":
        request = ("send-keys title=%r pid=%d class=%s index=%s key=%s"
                   % (window, pid, class_, index, key))
        extra = ["-Action", "key", "-Key", key]
    else:
        request = ("set-text title=%r pid=%d class=%s index=%s payload=%r"
                   % (window, pid, class_, index, text))
        extra = ["-Action", "text", "-Payload", text]
    idx = -1 if index is None else int(index)
    base = [pwsh, "-NoProfile", "-NonInteractive", "-File", _SEND_TOOL,
            "-TitleLike", window, "-ProcId", str(pid)]
    # Enumerate first (no side effect) so ambiguity fails closed before typing.
    code, listing = _tool(base + ["-Class", class_, "-Index", str(idx), "-ListOnly"])
    if code != 0:
        raise NotFoundError("no visible window matching %r in pid %d (pass title=...); %s"
                            % (window, pid, RUN_RETRY))
    matches = []
    for line in listing.splitlines():
        record = _screen.child_record(line)
        if record is not None and record[2] and record[1] == class_:
            matches.append(line.strip())
    if not matches:
        raise NotFoundError("no visible child of class %r in pid %d; %s"
                            % (class_, pid, RUN_RETRY))
    if idx < 0 and len(matches) > 1:
        raise UsageError("ambiguous: %d visible children of class %r (addressing must be "
                         "unique; pass index=); %s" % (len(matches), class_, RUN_RETRY))
    if idx >= len(matches):
        raise UsageError("index %d out of range (%d match(es)); %s"
                         % (idx, len(matches), RUN_RETRY))
    if not yes:
        return "DRY-RUN %s" % request
    code, output = _tool(base + ["-Class", class_, "-Index", str(idx)] + extra)
    if code != 0:
        raise CtlError("unhandled", "%s failed: %s; %s" % (action, output.strip(), RUN_RETRY))
    return output.rstrip()


# --------------------------------------------------------------------------- #
# Connect-or-start
# --------------------------------------------------------------------------- #

def _config_from_args(args) -> Config:
    flags = {"config": getattr(args, "config", None), "port": getattr(args, "port", None)}
    return load_config({key: value for key, value in flags.items() if value is not None})


def _target_names(args, config: Config) -> List[str]:
    raw = getattr(args, "target", None) or []
    names: List[str] = []
    for item in raw:
        for part in str(item).split(","):
            part = part.strip()
            if part and part not in names:
                names.append(part)
    return names or [config.default_target]


def _live_client(config: Config, run_id: str, port: Optional[int]) -> Optional[Client]:
    """A client for the run **only if** the bridge answers ``sys.ping``."""
    try:
        if port is not None:
            client = Client(port=int(port),
                            run_root=config.run_root, run_id=run_id)
        else:
            endpoint = discover_endpoint(config.run_root, run_id)
            client = Client(port=endpoint["port"],
                            run_root=config.run_root, run_id=run_id)
    except CtlError:
        return None
    return client if client.ping(timeout=10.0) else None


# --------------------------------------------------------------------------- #
# Script execution
# --------------------------------------------------------------------------- #

def _exit_code(result: Any) -> int:
    if result is None:
        return 0
    if isinstance(result, int):
        return result
    return 1


def _exec_source(source: str, filename: str, namespace: Dict[str, Any]) -> int:
    try:
        code = compile(source, filename, "exec")
    except SyntaxError:
        traceback.print_exc()
        return 1
    try:
        exec(code, namespace)
    except SystemExit as exc:
        return _exit_code(exc.code)
    except PrereqNotReady as exc:
        print(exc.line(), file=sys.stderr)
        return 2
    except CtlError as exc:
        print(exc.line(), file=sys.stderr)
        return 1
    except BaseException:
        traceback.print_exc()
        return 1
    return 0


def _utf8_streams() -> None:
    """Windows consoles default to a locale codec; script output must not crash."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def cmd_run(args) -> int:
    """``python -m ctl run`` -- read a script from stdin and run it against the bridge."""
    _utf8_streams()
    script = sys.stdin.read()
    if not script.strip():
        print("ERR empty script; %s" % RUN_RETRY, file=sys.stderr)
        return 1

    config = _config_from_args(args)
    names = _target_names(args, config)
    if len(names) > 1:
        print("ERR badrequest run takes a single --target, got: %s; retry: python -m ctl --help"
              % ", ".join(names), file=sys.stderr)
        return 1
    name = names[0]
    if name not in config.targets:
        print("ERR notfound no such target: %s; retry: python -m ctl targets list" % name,
              file=sys.stderr)
        return 2

    port = getattr(args, "port", None)
    run_id = getattr(args, "run_id", None) or latest_run_id(config.run_root, name) or make_run_id(name)
    state = _DoorState(run_id=run_id)

    client = _live_client(config, run_id, port)
    if client is None:
        if getattr(args, "no_start", False):
            print("ERR no instance; retry: python -m ctl install --target %s --run-id %s"
                  % (name, run_id), file=sys.stderr)
            return 2
        print("run: no live bridge for run %r -> starting an isolated instance "
              "(python -m ctl install --target %s --run-id %s)" % (run_id, name, run_id),
              file=sys.stderr)
        instance = lifecycle_install(config, name, run_id, port,
                                     bool(getattr(args, "ensure_clean", False)))
        state.run_id = instance.paths.run_id
        client = Client.from_run(config.run_root, instance.paths.run_id)
        state.started = True
        print("run: started it (pid=%s, port=%s); the script runs against this instance"
              % (instance.pid, client.port()), file=sys.stderr)
    else:
        state.run_id = client.run_id or run_id
        print("run: reusing the live bridge on 127.0.0.1:%s (run %s)"
              % (client.port(), state.run_id), file=sys.stderr)
    state.port = client.port()

    namespace = _make_namespace(client, state)
    helpers = getattr(args, "helpers", None)
    if helpers:
        try:
            with open(helpers, "r", encoding="utf-8") as handle:
                helper_source = handle.read()
        except OSError as exc:
            print("ERR notfound helpers file unreadable: %s (%s); %s"
                  % (helpers, exc, RUN_RETRY), file=sys.stderr)
            return 1
        code = _exec_source(helper_source, helpers, namespace)
        if code:
            return code

    code = _exec_source(script, "<stdin>", namespace)
    if code:
        return code
    return 1 if state.err else 0
