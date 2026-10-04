"""Line-protocol client for the eclipse-ctl bridge.

Relocated from the verified `_legacy_client.py` slice-1 harness: the *connection
/ send / parse / timeout* capability is preserved function-for-function
(``talk`` -> :func:`talk`, ``resp`` -> :func:`resp`, ``snap`` -> :func:`snap`,
``show`` -> :func:`show`).  Three capabilities are added on top:

1. ``ERR <code> <message>`` is decomposed into ``(code, message)``; a code
   outside the frozen set collapses to ``internal`` with the original text kept.
2. The port is discovered from ``<run_root>/<run_id>/endpoint.json`` -- never
   guessed as 8777.
3. The client timeout defaults to 25 s, above the bridge's 15 s UI cap, so a
   hung UI call normally surfaces as ``ERR timeout`` from the bridge first.

Timeouts follow `design.md` §3: a timeout ends only the *wait*; it is not proof
that the request was not applied.
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
from typing import List, Optional, Tuple

from .errors import (
    ERROR_CODE_SET,
    BridgeError,
    CtlError,
    EndpointNotFound,
    FALLBACK_CODE,
)
from . import shadow

HOST = "127.0.0.1"
DEFAULT_PORT = 8777

#: Client-side deadline (design: "客户端默认 25 s").

#: 退避重连的基/上限（秒）。指数退避，封顶 RETRY_MAX。
RETRY_BASE_S = 0.5
RETRY_MAX_S = 5.0

#: 退避/钉住用到的正则（sys.env 负载）。
DEFAULT_TIMEOUT = 25.0
#: Bridge-side UI cap; the client normally receives `ERR timeout` before it
#: would time out itself (`design-project.md` §17.5).
BRIDGE_UI_TIMEOUT_MS = 15000

ENDPOINT_FILENAME = "endpoint.json"
_RECV_CHUNK = 65536

#: Frame-size ceilings.  Nothing in `protocol.md` bounds a request line or a
#: response, so a peer that never writes ``END`` (or one enormous payload line)
#: must not be able to grow this process's buffer without limit (R5-2).  The
#: values are generous next to the largest documented payload -- ``ui.console``
#: is capped at 200 000 chars bridge-side (`LiveBridge.java` ``CONSOLE_MAX_CHARS``)
#: -- and only ever stop reads/refuse a request; they never truncate a legal one.
MAX_REQUEST_BYTES = 64 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_FRAME_BYTES = 8 * 1024 * 1024


# --------------------------------------------------------------------------- #
# Endpoint discovery
# --------------------------------------------------------------------------- #

def _checked_run_id(run_id: str) -> str:
    """Reject a run id that could escape ``<run_root>`` when joined as a path.

    ``run_root``/``run_id`` become a directory in :func:`endpoint_path` and
    :func:`write_endpoint`; an unvalidated ``..\\..`` run id therefore turned
    ``discover_endpoint`` / ``write_endpoint`` into reads and writes outside the
    run root (R5-5).  The whitelist runs *before* any join, so a bad id never
    produces a path at all -- the alternative (``realpath`` after the join) would
    still build the escaping path and depend on every consumer checking.
    """
    from .lifecycle import validate_run_id  # lazy: lifecycle imports this module
    return validate_run_id(run_id)


def endpoint_path(run_root: str, run_id: str) -> str:
    return os.path.join(run_root, _checked_run_id(run_id), ENDPOINT_FILENAME)


def discover_endpoint(run_root: str, run_id: str) -> dict:
    """Read ``<run_root>/<run_id>/endpoint.json``.

    Raises :class:`EndpointNotFound` when the file is missing or malformed --
    the port is *never* guessed, otherwise a stale listener gets addressed as if
    it were the current instance (`facts-baseline.md` §9 "残留实例抢端口").
    """
    if not run_id:
        raise EndpointNotFound(
            "no run-id given, cannot locate endpoint.json; retry: python -m ctl status --target gs32")
    path = endpoint_path(run_root, run_id)
    if not os.path.isfile(path):
        raise EndpointNotFound(
            "no endpoint for run '%s' (%s); retry: python -m ctl install --target gs32 --run-id %s"
            % (run_id, path, run_id))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise EndpointNotFound(
            "endpoint.json unreadable for run '%s' (%s: %s); retry: python -m ctl install --target gs32 --run-id %s"
            % (run_id, path, exc, run_id))
    if not isinstance(data, dict) or "port" not in data:
        raise EndpointNotFound(
            "endpoint.json for run '%s' has no port field (%s); retry: python -m ctl install --target gs32 --run-id %s"
            % (run_id, path, run_id))
    port = data["port"]
    # Type-strict on purpose: ``True`` is an ``int`` (``int(True) == 1``), a float
    # like ``3.9`` would silently floor to 3, and ``1e10`` overflowed PowerShell's
    # ``[uint32]`` port -- all of which a bare ``int()`` accepted (R5-7).
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise EndpointNotFound(
            "endpoint.json for run '%s' has an out-of-range port (%r, %s); "
            "retry: python -m ctl install --target gs32 --run-id %s"
            % (run_id, port, path, run_id))
    pid = data.get("pid")
    if pid is not None and (isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0):
        raise EndpointNotFound(
            "endpoint.json for run '%s' has a non-positive pid (%r, %s); "
            "retry: python -m ctl install --target gs32 --run-id %s"
            % (run_id, pid, path, run_id))
    return data


def write_endpoint(run_root: str, run_id: str, port: int, pid: Optional[int] = None,
                   configuration: str = "") -> str:
    """Record the live instance under ``<run_root>/<run_id>/endpoint.json``."""
    directory = os.path.dirname(endpoint_path(run_root, run_id))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, ENDPOINT_FILENAME)
    payload = {
        "port": int(port),
        "pid": int(pid) if pid is not None else None,
        "configuration": configuration or "",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    return path


# --------------------------------------------------------------------------- #
# Status-line parsing
# --------------------------------------------------------------------------- #

def parse_status(line: str) -> Tuple[str, Optional[str], str]:
    """``"OK" | "ERR <code> <message>"`` -> ``(kind, code, message)``.

    ``kind`` is ``"ok"`` or ``"err"``.  A code outside the frozen set becomes
    ``internal`` and the *whole* original remainder is preserved as the message.
    """
    text = (line or "").strip()
    parts = text.split(None, 2)
    if not parts:
        return ("err", FALLBACK_CODE, "")
    head = parts[0].upper()
    if head == "OK":
        return ("ok", None, parts[1] + (" " + parts[2] if len(parts) > 2 else "") if len(parts) > 1 else "")
    if head == "ERR":
        if len(parts) < 2:
            return ("err", FALLBACK_CODE, "")
        code = parts[1]
        message = parts[2] if len(parts) > 2 else ""
        if code not in ERROR_CODE_SET:
            remainder = text[len("ERR "):]
            return ("err", FALLBACK_CODE, remainder)
        return ("err", code, message)
    # A bare exception string (legacy bridge) -> internal, text preserved.
    return ("err", FALLBACK_CODE, text)


# --------------------------------------------------------------------------- #
# Response
# --------------------------------------------------------------------------- #

class Response:
    """A parsed bridge response."""

    __slots__ = ("raw", "lines", "status_line", "payload", "elapsed", "kind",
                 "code", "message")

    def __init__(self, raw: str, elapsed: float = 0.0):
        self.raw = raw
        self.elapsed = elapsed
        self.lines = raw.splitlines()
        self.status_line = self.lines[0] if self.lines else ""
        # Mirrors the legacy `resp()` body slice: drop the status line and END.
        self.payload = self.lines[1:-1] if len(self.lines) > 1 else []
        self.kind, self.code, self.message = parse_status(self.status_line)

    @property
    def ok(self) -> bool:
        return self.kind == "ok"

    @property
    def timed_out(self) -> bool:
        return "<client timeout>" in self.raw

    @property
    def text(self) -> str:
        return "\n".join(self.payload)

    def raise_for_error(self) -> "Response":
        if not self.ok:
            raise BridgeError(self.code or FALLBACK_CODE, self.message, self.raw)
        return self

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "Response(%r, %d lines)" % (self.status_line, len(self.payload))


# --------------------------------------------------------------------------- #
# Transport (relocated verbatim from the slice-1 harness)
# --------------------------------------------------------------------------- #

def _frame_end_offset(data: bytes, start: int = 0) -> Tuple[Optional[int], int]:
    """Search ``data`` from ``start`` for a **lone** ``END`` line.

    Returns ``(end_offset, resume)``: ``end_offset`` is the byte just past the
    terminating line's ``\\n`` (``None`` while no whole ``END`` line is present),
    and ``resume`` is where the next call continues scanning.  Only a line that
    is *entirely* ``END`` (whitespace tolerated) ends a frame; a payload line
    that merely ends with those bytes -- ``"build END"`` -- does not
    (`protocol.md` §2.2: "读到 END 才算一帧结束").
    """
    pos = start
    while True:
        nl = data.find(b"\n", pos)
        if nl < 0:
            return None, pos
        if data[pos:nl].strip() == b"END":
            return nl + 1, nl + 1
        pos = nl + 1


def _recv_until_end(sock: socket.socket, timeout: float) -> bytes:
    """Read until the ``END`` **line**, mirroring the legacy receive loop.

    The legacy loop broke on the *substring* ``b"END\\n"``: a payload line that
    ended in ``END`` cut the frame short, dropping everything after it while the
    status line still read ``OK`` (R5-2).  Termination is now per line, and the
    buffer is bounded by :data:`MAX_LINE_BYTES` / :data:`MAX_FRAME_BYTES` so a
    peer that never writes ``END`` cannot grow it without limit.
    """
    data = b""
    cursor = 0
    while True:
        end, cursor = _frame_end_offset(data, cursor)
        if end is not None:
            return data[:end]
        if len(data) - cursor > MAX_LINE_BYTES or len(data) >= MAX_FRAME_BYTES:
            break
        try:
            chunk = sock.recv(_RECV_CHUNK)
        except socket.timeout:
            data += b"\n<client timeout>\n"
            break
        if not chunk:
            break
        data += chunk
    return data


def resolve_port(port: Optional[int] = None, run_root: Optional[str] = None,
                 run_id: Optional[str] = None) -> int:
    """Explicit port > endpoint.json for ``run_id`` > legacy default 8777."""
    if port is not None:
        return int(port)
    if run_id:
        return int(discover_endpoint(run_root or _default_run_root(), run_id)["port"])
    return DEFAULT_PORT


def _default_run_root() -> str:
    from .targets import DEFAULT_RUN_ROOT
    return DEFAULT_RUN_ROOT


def _parse_env(raw: str) -> dict:
    """从 `sys.env` 的负载里取 (bundle 名, protocol) —— 用来钉住「我在跟谁说话」。"""
    m = re.search(r"^bundle=(\S+)", raw, re.M)
    p = re.search(r"^protocol=(\S+)", raw, re.M)
    return {"bundle": m.group(1) if m else "<unknown>",
            "protocol": p.group(1) if p else "<unknown>"}


def talk(req: str, port: Optional[int] = None, timeout: float = DEFAULT_TIMEOUT,
         host: str = HOST, run_root: Optional[str] = None,
         run_id: Optional[str] = None) -> str:
    """Send one request line, return the raw response text.

    Faithful to the legacy behaviour: a fresh connection per call, read until
    ``END``, and the marker ``<client timeout>`` appended on socket timeout.
    """
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    payload = req.encode("utf-8")
    if len(payload) > MAX_REQUEST_BYTES:
        raise CtlError(
            "badrequest",
            "request is %d bytes, over the %d-byte request cap; "
            "retry: send a smaller request (`protocol.md` §2.1: one request = one line)"
            % (len(payload), MAX_REQUEST_BYTES))
    actual_port = resolve_port(port, run_root, run_id)
    try:
        sock = socket.create_connection((host, actual_port), timeout=timeout)
    except OSError as exc:
        raise CtlError("unhandled",
                       "cannot reach bridge on %s:%d (%s); retry: python -m ctl status --target gs32"
                       % (host, actual_port, exc))
    try:
        sock.settimeout(timeout)
        sock.sendall(payload + b"\n")
        data = _recv_until_end(sock, timeout)
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return data.decode("utf-8", "replace")


def resp(req: str, port: Optional[int] = None, timeout: float = DEFAULT_TIMEOUT,
         **kwargs) -> Tuple[str, List[str], str]:
    """-> ``(status_line, body_lines, full_text)`` (legacy shape)."""
    raw = talk(req, port=port, timeout=timeout, **kwargs)
    lines = raw.splitlines()
    return (lines[0] if lines else "<empty>", lines[1:-1] if len(lines) > 1 else [], raw)


def snap(port: Optional[int] = None, timeout: float = DEFAULT_TIMEOUT, **kwargs) -> dict:
    """Workbench snapshot: -> dict with status/raw/views/page/persp/editors.

    Parsing is byte-for-byte the legacy `snap()`.
    """
    st, b, raw = resp("ui.parts", port=port, timeout=timeout, **kwargs)
    txt = "\n".join(b)
    vset = set(re.findall(r"^\s*view id=(\S+)", txt, re.M))
    pm = re.search(r"^perspective id=(\S+)", txt, re.M)
    em = re.search(r"^editors=(\d+)", txt, re.M)
    return {
        "status": st,
        "raw": txt,
        "views": vset,
        "hasActivePage": "activePage=null" not in txt,
        "persp": pm.group(1) if pm else None,
        "editors": int(em.group(1)) if em else -1,
    }


def show(title: str, st: str, body: List[str], limit: int = 8) -> None:
    """Legacy pretty-printer (diagnostics only)."""
    print("\n--- %s\n    STATUS: %s" % (title, st), flush=True)
    for line in body[:limit]:
        print("    | %s" % line, flush=True)
    if len(body) > limit:
        print("    | ...(%d more)" % (len(body) - limit), flush=True)


# --------------------------------------------------------------------------- #
# Client object
# --------------------------------------------------------------------------- #

class Client:
    """A thin, stateless-per-request client bound to one instance.

    The port is resolved lazily on every call so a client built before
    ``install`` wrote ``endpoint.json`` still works afterwards (D4 reconnect).
    """

    def __init__(self, port: Optional[int] = None, host: str = HOST,
                 timeout: float = DEFAULT_TIMEOUT,
                 run_root: Optional[str] = None, run_id: Optional[str] = None,
                 retry: float = 0.0):
        self._port = port
        self.host = host
        self.timeout = timeout
        self.run_root = run_root
        self.run_id = run_id
        #: 连接失败时的退避重连预算（秒）。0 = 立刻失败（默认，保持一次性命令的行为）。
        self.retry = float(retry or 0.0)
        #: 首次连上时钉住的 (bundle, protocol)；重连后必须一致（D4）。
        self._pinned: Optional[dict] = None
        #: 最近一次请求是否经历过重连（供调用方/证据用）。
        self.reconnects = 0

    @classmethod
    def from_run(cls, run_root: str, run_id: str, timeout: float = DEFAULT_TIMEOUT,
                 retry: float = 0.0) -> "Client":
        endpoint = discover_endpoint(run_root, run_id)
        return cls(port=endpoint["port"], timeout=timeout,
                   run_root=run_root, run_id=run_id, retry=retry)

    def port(self) -> int:
        return resolve_port(self._port, self.run_root, self.run_id)

    def _raw(self, req: str, timeout: float) -> str:
        return talk(req, port=self._port, timeout=timeout,
                    host=self.host,
                    run_root=self.run_root, run_id=self.run_id)

    def _pin(self) -> dict:
        """首次连上时记下 (bundle, protocol)，作为 D4 重连的比对基准。"""
        env = _parse_env(self._raw("sys.env", self.timeout))
        self._pinned = env
        return env

    def talk(self, req: str, timeout: Optional[float] = None) -> str:
        t = timeout or self.timeout
        if self.retry <= 0:
            return self._raw(req, t)
        if self._pinned is None:
            self._pin()
        deadline = time.time() + self.retry
        delay = RETRY_BASE_S
        attempt = 0
        while True:
            attempt += 1
            try:
                raw = self._raw(req, t)
                break
            except CtlError:
                if time.time() >= deadline:
                    raise
                time.sleep(min(delay, max(0.0, deadline - time.time())))
                delay = min(delay * 2, RETRY_MAX_S)
        if attempt > 1:
            self.reconnects += 1
            # **重连后必须重新验身**：换了个人就停下，别带着它的状态继续跑。
            now = _parse_env(self._raw("sys.env", t))
            if now != self._pinned:
                raise CtlError(
                    "internal",
                    "reconnected to a DIFFERENT bridge: was %r, now %r; refusing to continue "
                    "(the run may have been replaced mid-flight)" % (self._pinned, now))
        return raw

    def resp(self, req: str, timeout: Optional[float] = None) -> Tuple[str, List[str], str]:
        return resp(req, port=self._port, timeout=timeout or self.timeout,
                    host=self.host,
                    run_root=self.run_root, run_id=self.run_id)

    def request(self, req: str, timeout: Optional[float] = None) -> Response:
        started = time.time()
        raw = self.talk(req, timeout=timeout)
        response = Response(raw, elapsed=time.time() - started)
        # Shadow shots (R1): purely additive observation of write actions.  It
        # runs *after* the response is built, swallows its own failures and is
        # never allowed to influence the result or the exit code -- see
        # `ctl/shadow.py` for why it is not part of the request path.
        shadow.after(req, response, shadow.for_client(self))
        return response

    def ping(self, timeout: Optional[float] = None) -> bool:
        try:
            return self.request("sys.ping", timeout=timeout).ok
        except CtlError:
            return False

    def env(self, timeout: Optional[float] = None) -> Response:
        return self.request("sys.env", timeout=timeout)
