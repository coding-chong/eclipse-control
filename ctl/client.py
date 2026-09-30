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

HOST = "127.0.0.1"
DEFAULT_PORT = 8777

#: Client-side deadline (design: "客户端默认 25 s").
DEFAULT_TIMEOUT = 25.0
#: Bridge-side UI cap; the client normally receives `ERR timeout` before it
#: would time out itself (`design-project.md` §17.5).
BRIDGE_UI_TIMEOUT_MS = 15000

ENDPOINT_FILENAME = "endpoint.json"
_RECV_CHUNK = 65536


# --------------------------------------------------------------------------- #
# Endpoint discovery
# --------------------------------------------------------------------------- #

def endpoint_path(run_root: str, run_id: str) -> str:
    return os.path.join(run_root, run_id, ENDPOINT_FILENAME)


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
    try:
        data["port"] = int(data["port"])
    except (TypeError, ValueError):
        raise EndpointNotFound(
            "endpoint.json for run '%s' has a non-numeric port (%s)" % (run_id, path))
    return data


def write_endpoint(run_root: str, run_id: str, port: int, pid: Optional[int] = None,
                   configuration: str = "", token: str = "") -> str:
    """Record the live instance under ``<run_root>/<run_id>/endpoint.json``."""
    directory = os.path.join(run_root, run_id)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, ENDPOINT_FILENAME)
    payload = {
        "port": int(port),
        "token": token or "",
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

def _recv_until_end(sock: socket.socket, timeout: float) -> bytes:
    """Read until the ``END`` line, mirroring the legacy receive loop."""
    data = b""
    while b"END\n" not in data:
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


def talk(req: str, port: Optional[int] = None, timeout: float = DEFAULT_TIMEOUT,
         host: str = HOST, token: str = "", run_root: Optional[str] = None,
         run_id: Optional[str] = None) -> str:
    """Send one request line, return the raw response text.

    Faithful to the legacy behaviour: a fresh connection per call, read until
    ``END``, and the marker ``<client timeout>`` appended on socket timeout.
    """
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    actual_port = resolve_port(port, run_root, run_id)
    try:
        sock = socket.create_connection((host, actual_port), timeout=timeout)
    except OSError as exc:
        raise CtlError("unhandled",
                       "cannot reach bridge on %s:%d (%s); retry: python -m ctl status --target gs32"
                       % (host, actual_port, exc))
    try:
        sock.settimeout(timeout)
        if token:
            sock.sendall(("auth " + token).encode("utf-8") + b"\n")
            auth = _recv_until_end(sock, timeout)
            auth_kind, _, auth_msg = parse_status(auth.decode("utf-8", "replace").splitlines()[0]
                                                  if auth.splitlines() else "")
            if auth_kind != "ok":
                raise BridgeError("badrequest", "authentication failed: %s" % auth_msg)
        sock.sendall(req.encode("utf-8") + b"\n")
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
                 timeout: float = DEFAULT_TIMEOUT, token: str = "",
                 run_root: Optional[str] = None, run_id: Optional[str] = None):
        self._port = port
        self.host = host
        self.timeout = timeout
        self.token = token
        self.run_root = run_root
        self.run_id = run_id

    @classmethod
    def from_run(cls, run_root: str, run_id: str, timeout: float = DEFAULT_TIMEOUT,
                 token: str = "") -> "Client":
        endpoint = discover_endpoint(run_root, run_id)
        return cls(port=endpoint["port"], timeout=timeout,
                   token=token or endpoint.get("token") or "",
                   run_root=run_root, run_id=run_id)

    def port(self) -> int:
        return resolve_port(self._port, self.run_root, self.run_id)

    def talk(self, req: str, timeout: Optional[float] = None) -> str:
        return talk(req, port=self._port, timeout=timeout or self.timeout,
                    host=self.host, token=self.token,
                    run_root=self.run_root, run_id=self.run_id)

    def resp(self, req: str, timeout: Optional[float] = None) -> Tuple[str, List[str], str]:
        return resp(req, port=self._port, timeout=timeout or self.timeout,
                    host=self.host, token=self.token,
                    run_root=self.run_root, run_id=self.run_id)

    def request(self, req: str, timeout: Optional[float] = None) -> Response:
        started = time.time()
        raw = self.talk(req, timeout=timeout)
        return Response(raw, elapsed=time.time() - started)

    def ping(self, timeout: Optional[float] = None) -> bool:
        try:
            return self.request("sys.ping", timeout=timeout).ok
        except CtlError:
            return False

    def env(self, timeout: Optional[float] = None) -> Response:
        return self.request("sys.env", timeout=timeout)
