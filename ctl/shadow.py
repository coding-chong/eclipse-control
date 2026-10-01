"""Shadow shots -- an always-on frame ledger that nobody reads by default.

Every **write** action costs one extra frame of pixels under
``<run_root>/<run_id>/shadow/``.  The purpose is forensic: after something went
wrong, ``ctl shadow --seq N`` answers "what did the screen look like right
then?", including the cases the structured channels cannot express (the bridge
hung, the pixels changed while the window set stayed identical).

Two invariants make this layer safe to leave on (both are structural, not
best-effort):

1. **It never touches the request path.**  :func:`after` is called *after* the
   response has been built; the whole body is wrapped in one ``try/except`` and
   every failure is reported as ``WARN: shadow …`` on stderr.  Exit codes and
   response objects are produced before this module runs.
2. **It is not evidence that anything was asserted.**  No PASS/FAIL anywhere in
   this repository reads ``shadow/`` -- ``PrintWindow`` has a real
   "returned TRUE and painted nothing" failure mode, and a channel that can lie
   must never be a judge.  Frames live next to, but strictly apart from,
   ``shots/``: ``shots/`` answers "what was I asked to prove", ``shadow/``
   answers "what did the screen look like".

Which actions count as writes is **not** decided here: the bridge's own
``sys.help`` table (``name|args|write|idempotent|desc``) is the only source
(``LiveBridge.java`` single-sources that table).  It is fetched once per run; if
it cannot be fetched the whole layer degrades silently for that run -- guessing
a method list would be worse than taking no frame.

Selection of *which window* to photograph follows R11: ``pid`` ∩ ``class ∈
{SWT_Window0, #32770}`` ∩ ``vis=True`` ∩ title not a known auxiliary shell, with
the rejected classes hard-vetoed in ``tools/win-probe.ps1``.  Area is only the
tie-break *inside* the whitelist; it is never the identity.  No legal candidate
means no file and ``rc=1`` from the tool (fail closed): a frame of some
unrelated window, stored as "this is what the screen looked like", is worse than
no frame at all.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)
TOOLS_DIR = os.path.join(REPO_ROOT, "tools")
PROBE_PS1 = os.path.join(TOOLS_DIR, "win-probe.ps1")

SHADOW_DIRNAME = "shadow"
MANIFEST_NAME = "manifest.jsonl"

#: R11 whitelist, passed verbatim to `win-probe.ps1 -Class`.
WINDOW_CLASSES = "SWT_Window0,#32770"

#: Ring defaults (`design.md` §5): 20 frames / 32 MB, oldest non-promoted first.
DEFAULT_MAX_FRAMES = 20
DEFAULT_MAX_BYTES = 32 * 1024 * 1024

#: Ceiling for one probe.  The measured cost is ~0.8-1.2 s; the ceiling exists so
#: a wedged pwsh can never hold a caller for longer than this.
PROBE_TIMEOUT_S = 20.0
#: `sys.help` is one round trip on a fresh connection -- keep it short, it is
#: only needed to answer "is this method a write".
HELP_TIMEOUT_S = 8.0

DIALOG_MARKER = "dialog="

_ENV_PREFIX = "ECLIPSE_CTL_"
_REPO_CONFIG = os.path.join(os.path.expanduser("~"), ".eclipse-ctl", "config.json")

_SLUG = re.compile(r"[^A-Za-z0-9]+")


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

@dataclass
class ShadowConfig:
    """Effective shadow settings for one process (four precedence layers applied)."""

    enabled: bool = True
    only_changes: bool = False
    max_frames: int = DEFAULT_MAX_FRAMES
    max_bytes: int = DEFAULT_MAX_BYTES
    run_root: str = ""
    run_id: str = ""
    host: str = "127.0.0.1"
    port: Optional[int] = None
    token: str = ""
    pid: int = 0
    probe_script: str = PROBE_PS1
    pwsh: str = "pwsh"
    probe_timeout: float = PROBE_TIMEOUT_S
    #: Where each layer got its value from -- kept for `WARN`-level honesty.
    provenance: Dict[str, str] = field(default_factory=dict)

    def run_key(self) -> str:
        return "%s|%s" % (self.run_root, self.run_id)

    def manifest_path(self) -> str:
        return os.path.join(self.run_root, self.run_id, SHADOW_DIRNAME, MANIFEST_NAME)

    def shadow_dir(self) -> str:
        return os.path.join(self.run_root, self.run_id, SHADOW_DIRNAME)


_STATE = ShadowConfig()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _read_config_file(path: str) -> Dict[str, Any]:
    """Best-effort JSON read; a broken config file must not disable the CLI."""
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def resolve(no_shadow: Optional[bool] = None, only_changes: Optional[bool] = None,
            config_path: Optional[str] = None,
            env: Optional[Dict[str, str]] = None) -> ShadowConfig:
    """Merge flags > environment > config file > defaults (the repo-wide order).

    ``no_shadow`` / ``only_changes`` are ``None`` when the flag was not given --
    a plain ``store_true`` default of ``False`` would make "absent" and
    "explicitly off" indistinguishable and break the precedence.
    """
    env = os.environ if env is None else env
    path = (config_path or env.get(_ENV_PREFIX + "CONFIG") or _REPO_CONFIG)
    data = _read_config_file(path)

    cfg = ShadowConfig(provenance={})
    cfg.provenance.update({"enabled": "default", "only_changes": "default",
                           "max_frames": "default", "max_bytes": "default"})

    if "shadow" in data:
        cfg.enabled = _as_bool(data["shadow"])
        cfg.provenance["enabled"] = "file"
    if "shadow_only_changes" in data:
        cfg.only_changes = _as_bool(data["shadow_only_changes"])
        cfg.provenance["only_changes"] = "file"
    if "shadow_max_frames" in data:
        cfg.max_frames = _as_int(data["shadow_max_frames"], cfg.max_frames)
        cfg.provenance["max_frames"] = "file"
    if "shadow_max_bytes" in data:
        cfg.max_bytes = _as_int(data["shadow_max_bytes"], cfg.max_bytes)
        cfg.provenance["max_bytes"] = "file"

    env_keys = {
        "enabled": ("SHADOW", _as_bool),
        "only_changes": ("SHADOW_ONLY_CHANGES", _as_bool),
        "max_frames": ("SHADOW_MAX_FRAMES", None),
        "max_bytes": ("SHADOW_MAX_BYTES", None),
    }
    for name, (suffix, caster) in env_keys.items():
        raw = env.get(_ENV_PREFIX + suffix)
        if raw is None or raw == "":
            continue
        if caster is not None:
            setattr(cfg, name, caster(raw))
        else:
            setattr(cfg, name, _as_int(raw, getattr(cfg, name)))
        cfg.provenance[name] = "env"

    if only_changes is not None:
        cfg.only_changes = bool(only_changes)
        cfg.provenance["only_changes"] = "flag"
    if no_shadow is not None:
        cfg.enabled = not bool(no_shadow)
        cfg.provenance["enabled"] = "flag"

    # A budget of 0 would delete the frame that was just written; the ledger must
    # always be able to answer for the newest action.
    cfg.max_frames = max(1, int(cfg.max_frames))
    cfg.max_bytes = max(1, int(cfg.max_bytes))
    return cfg


def configure(cfg: Optional[ShadowConfig] = None, **kwargs) -> ShadowConfig:
    """Install the process-wide settings the hook in ``Client.request`` reads."""
    global _STATE
    if cfg is None:
        cfg = resolve(**kwargs)
    _STATE = cfg
    return _STATE


def current() -> ShadowConfig:
    return _STATE


def for_client(client) -> ShadowConfig:
    """Bind the process-wide settings to one live :class:`~ctl.client.Client`.

    Never raises: an unusable client simply yields a disabled config, because
    the caller is the request path this layer must not disturb.
    """
    try:
        cfg = replace(_STATE)
        cfg.run_root = getattr(client, "run_root", "") or ""
        cfg.run_id = getattr(client, "run_id", "") or ""
        cfg.host = getattr(client, "host", cfg.host) or cfg.host
        cfg.token = getattr(client, "token", "") or ""
        try:
            cfg.port = int(client.port())
        except Exception:
            cfg.port = None
        return cfg
    except Exception:
        return ShadowConfig(enabled=False, provenance={"enabled": "unavailable"})


def warn(message: str) -> None:
    """The only channel this layer is allowed to fail on."""
    print("WARN: shadow %s" % message, file=sys.stderr)


# --------------------------------------------------------------------------- #
# The hook
# --------------------------------------------------------------------------- #

#: ``run_key -> set(known write methods)`` or ``None`` when sys.help failed.
_HELP_CACHE: Dict[str, Optional[frozenset]] = {}


def after(req: str, response, cfg: Optional[ShadowConfig] = None) -> Optional[dict]:
    """Record one shadow frame for ``req`` if it was a write.  Never raises."""
    try:
        cfg = cfg or _STATE
        if not cfg.enabled:
            return None
        if not cfg.run_root or not cfg.run_id:
            return None
        method = _method_of(req)
        if not method:
            return None
        if not _is_write(cfg, method):
            return None
        return _capture(cfg, req, method, response)
    except Exception as exc:                      # never propagate: observation only
        warn("skipped %s (%s: %s)" % (_method_of(req) or "<empty request>",
                                      type(exc).__name__, exc))
        return None


def _method_of(req: str) -> str:
    text = (req or "").strip()
    if not text:
        return ""
    name = text.split()[0]
    return name if "." in name else ""


def _bridge(cfg: ShadowConfig, request: str, timeout: float) -> str:
    """One fresh connection, no retry/pinning -- this layer must stay cheap."""
    from .client import talk
    return talk(request, port=cfg.port, timeout=timeout, host=cfg.host,
                token=cfg.token, run_root=cfg.run_root, run_id=cfg.run_id)


def _write_table(cfg: ShadowConfig) -> Optional[frozenset]:
    """The bridge's write column, fetched at most once per run (R10)."""
    key = cfg.run_key()
    if key in _HELP_CACHE:
        return _HELP_CACHE[key]
    table: Optional[frozenset] = None
    try:
        raw = _bridge(cfg, "sys.help", HELP_TIMEOUT_S)
        if not raw.lstrip().upper().startswith("OK"):
            raise RuntimeError("sys.help answered %r" % raw.splitlines()[0][:80])
        table = frozenset(_parse_write_column(raw))
    except Exception as exc:
        warn("sys.help unavailable (%s); the whole layer stays off for run %s"
             % (exc, cfg.run_id or "<none>"))
    _HELP_CACHE[key] = table
    return table


#: `sys.help`'s idempotent column (bridge: `true|false|per-command|unknown`).  Used
#: as the second half of the write-column signature -- see `_parse_write_column`.
_IDEMPOTENT_VALUES = frozenset(("true", "false", "per-command", "unknown"))


def _parse_write_column(raw: str) -> List[str]:
    """``name|args|write|idempotent|desc`` rows -> the names with ``write=yes``.

    **Do not index the columns positionally.**  The ``args`` column may itself
    contain ``|``: ``cmd.runp``'s args are ``<id> <paramId|=paramName>=<value>``,
    so that row splits into 6 fields and ``fields[2]`` is ``=paramName>=<value>``
    rather than ``yes`` -- which silently dropped ``cmd.runp`` from the table and
    with it *every* parameterised command write (``ctl cmd <id> k=v`` goes through
    ``cmd.runp``; see ctl/__main__.py).  Measured 2026-10-01: the naive parse
    yielded ``{ui.open, ui.close, cmd.run}`` while the bridge's own table says
    ``cmd.runp|...|yes|...``.

    So: locate the write column as the first bare ``yes``/``no`` **followed by a
    field that looks like an idempotent value**.  That two-field signature cannot
    be forged by an argument placeholder, and it does not care how many ``|`` the
    args column contributes.
    """
    names: List[str] = []
    for line in raw.splitlines():
        fields = [f.strip() for f in line.strip().split("|")]
        if len(fields) < 3 or not fields[0] or " " in fields[0]:
            continue
        for i in range(1, len(fields) - 1):
            if fields[i].lower() in ("yes", "no"):
                if fields[i + 1].lower() not in _IDEMPOTENT_VALUES:
                    continue          # looks like prose, not the write column
                if fields[i].lower() == "yes":
                    names.append(fields[0])
                break
    if not names:
        raise RuntimeError("sys.help carried no write=yes row")
    return names


def _is_write(cfg: ShadowConfig, method: str) -> bool:
    table = _write_table(cfg)
    if table is None:                 # no table -> no guessing -> no frames
        return False
    return method in table


# --------------------------------------------------------------------------- #
# One capture
# --------------------------------------------------------------------------- #

@dataclass
class Probe:
    """What ``win-probe.ps1`` returned (``data`` is None when it said nothing)."""

    rc: int = 1
    data: Optional[dict] = None
    note: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.data and self.data.get("ok"))

    @property
    def reason(self) -> str:
        if not isinstance(self.data, dict):
            return "no-json"
        return str(self.data.get("reason") or "ok")

    @property
    def target(self) -> Optional[dict]:
        target = (self.data or {}).get("target")
        return target if isinstance(target, dict) else None


def _capture(cfg: ShadowConfig, req: str, method: str, response) -> dict:
    rows = _rows(cfg.manifest_path())
    seq = max([int(r.get("seq") or 0) for r in rows] + [0]) + 1

    previous = None
    for row in reversed(rows):
        if isinstance(row.get("windows"), dict) and row["windows"].get("hwnds"):
            previous = row
            break
    prev_hwnds = list(previous["windows"]["hwnds"]) if previous else []
    prev_sha = ""
    for row in reversed(rows):
        if row.get("sha256"):
            prev_sha = str(row["sha256"])
            break

    outcome, code = _outcome(response)
    dialog = _dialog_line(response)
    # "The read-back difference is empty" (R9-B) is operationalised as "the
    # response carried nothing to compare": this layer takes no read-back of its
    # own (it must not add bridge traffic), so a write whose answer has no
    # payload at all is precisely the case where nothing can be told apart -> keep
    # the frame.  The direction of the error is deliberate: it can only add
    # frames, never drop one.
    readback_empty = not response.payload

    if not cfg.pid:
        cfg.pid = _instance_pid(cfg)
    out_dir = cfg.shadow_dir()
    tmp = os.path.join(out_dir, ".pending-%d-%d.png" % (os.getpid(), seq))
    probe = _probe(cfg, tmp, prev_hwnds)

    windows = _window_summary(probe, prev_hwnds)
    changed = bool(probe.data and _window_changed(probe.data, prev_hwnds))

    keep = True
    if cfg.only_changes:
        # Policy B (diagnostic): the window set can only be learned by running the
        # probe, so the pwsh start is still paid -- what is saved is the stored
        # frame.  Anything that looks abnormal, or that we cannot judge from the
        # response at all, keeps its frame.
        keep = changed or outcome != "ok" or bool(dialog) or readback_empty

    row: Dict[str, Any] = {
        "seq": seq,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "method": method,
        "args": _args_of(req),
    }

    persisted = False
    if keep and os.path.isfile(tmp):
        digest = _sha256(tmp)
        size = os.path.getsize(tmp)
        if digest and digest == prev_sha:
            _unlink(tmp)
            row["same_as"] = _same_as_seq(rows, digest)
            row["sha256"] = digest
            row["bytes"] = size
        else:
            name = "%04d-%s-%s.png" % (seq, time.strftime("%H%M%S"), _slug(_title_of(probe)))
            try:
                os.replace(tmp, os.path.join(out_dir, name))
                row["shot"] = name
                row["sha256"] = digest
                row["bytes"] = size
                persisted = True
            except OSError as exc:
                # Do not leave a .pending-*.png behind when the rename fails (a
                # locked/read-only shadow dir would otherwise accumulate junk).
                _unlink(tmp)
                warn("could not store the frame (%s)" % exc)
    elif os.path.isfile(tmp):
        _unlink(tmp)

    row["windows"] = windows
    row["target"] = _target_of(probe)
    row["outcome"] = outcome
    if dialog:
        row["dialog"] = dialog
    if not probe.ok:
        row["probe"] = {"ok": False, "reason": probe.reason, "note": probe.note[:300]}

    reasons = _promote_reasons(outcome, code, dialog)
    row["promoted"] = bool(reasons)
    row["promote_reason"] = "; ".join(reasons) if reasons else None

    _append_row(cfg.manifest_path(), row)
    if persisted:
        try:
            prune(cfg)
        except Exception as exc:
            warn("prune failed (%s)" % exc)
    return row


def _outcome(response) -> Tuple[str, str]:
    if getattr(response, "ok", False):
        return "ok", ""
    code = str(getattr(response, "code", "") or "")
    status = str(getattr(response, "status_line", "") or "")
    if code == "timeout" or "ERR timeout" in status or getattr(response, "timed_out", False):
        return "timeout", code or "timeout"
    return "err", code


def _dialog_line(response) -> str:
    for line in list(getattr(response, "payload", []) or []) + [getattr(response, "raw", "")]:
        text = str(line or "").strip()
        if text.startswith(DIALOG_MARKER):
            return text[:200]
    return ""


def _promote_reasons(outcome: str, code: str, dialog: str) -> List[str]:
    reasons: List[str] = []
    if dialog:
        reasons.append(dialog)
    if outcome == "timeout":
        reasons.append("ERR timeout")
    elif outcome != "ok":
        reasons.append("outcome=%s" % (code or outcome))
    return reasons


def _args_of(req: str) -> str:
    parts = (req or "").split(None, 1)
    return parts[1].strip()[:200] if len(parts) > 1 else ""


def _slug(title: str) -> str:
    text = _SLUG.sub("_", title or "").strip("_")
    return (text[:40] or "untitled")


def _title_of(probe: Probe) -> str:
    target = probe.target or {}
    return str(target.get("title") or "")


def _target_of(probe: Probe) -> Dict[str, Any]:
    """Always the five R11 fields -- ``null`` when nothing legal was selected."""
    target = probe.target or {}
    return {
        "class": target.get("class"),
        "hwnd": target.get("hwnd"),
        "title": target.get("title"),
        "bounds": target.get("bounds"),
        "pid": target.get("pid"),
    }


def _window_summary(probe: Probe, prev_hwnds: Sequence[str]) -> Dict[str, Any]:
    data = probe.data or {}
    now = data.get("windows") if isinstance(data.get("windows"), list) else []
    hwnds = [str(w.get("hwnd")) for w in now if isinstance(w, dict) and w.get("hwnd")]
    return {
        "count": int(data.get("count") or len(hwnds)),
        "delta": _delta_text(now, prev_hwnds),
        "hwnds": hwnds,
    }


def _window_changed(data: dict, prev_hwnds: Sequence[str]) -> bool:
    now = data.get("windows") if isinstance(data.get("windows"), list) else []
    current = set(str(w.get("hwnd")) for w in now if isinstance(w, dict) and w.get("hwnd"))
    return current != set(str(h) for h in prev_hwnds)


def _delta_text(windows: Sequence[dict], prev_hwnds: Sequence[str]) -> str:
    if not prev_hwnds:
        return "baseline"
    known = set(str(h) for h in prev_hwnds)
    added = [w for w in windows if str(w.get("hwnd")) not in known]
    if not added:
        return "±0"
    if len(added) == 1:
        win = added[0]
        return '+1 %s "%s"' % (win.get("class"), win.get("title"))
    return "+%d %s" % (len(added), ", ".join(str(w.get("class")) for w in added[:3]))


# --------------------------------------------------------------------------- #
# Tool invocation
# --------------------------------------------------------------------------- #

def _decode(raw: bytes) -> str:
    text = (raw or b"").decode("utf-8", "replace")
    if "\ufffd" not in text:
        return text
    # stdout is redirected, so PowerShell may have encoded with the console code
    # page (GBK on this box); non-ASCII titles would otherwise be lost.
    for encoding in ("cp936", "mbcs", "latin-1"):
        try:
            fallback = (raw or b"").decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
        if "\ufffd" not in fallback:
            return fallback
    return text


def _probe(cfg: ShadowConfig, out_path: str, prev_hwnds: Sequence[str]) -> Probe:
    if not cfg.pid:
        # `-ProcId 0` means "any process" to the tool; without a pid the frame
        # could be some other application's dialog.  Fail closed instead.
        warn("no pid for run %s (endpoint.json); refusing to photograph any window"
             % (cfg.run_id or "<none>"))
        return Probe(1, None, "no-pid")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    argv = [cfg.pwsh, "-NoProfile", "-File", cfg.probe_script,
            "-Out", out_path, "-Class", WINDOW_CLASSES, "-ProcId", str(int(cfg.pid or 0)),
            # `-Flags 0` is deliberate and NOT configurable: this channel must not
            # perturb what it observes.  `verify/cases/resilience_modal_reset.py`
            # records an (unreproduced, explicitly "do not assert") suspicion that
            # `flags=2` / PW_RENDERFULLCONTENT makes a live SWT modal disappear --
            # and shadow probes a `#32770` by new-window priority, i.e. exactly
            # that shell.  Choosing 0 costs nothing: when a window paints blank
            # with 0, the tool retries with 2 by itself (see win-probe.ps1).
            # Do not surface this as a user-facing knob -- correctness, not taste.
            "-Flags", "0"]
    if prev_hwnds:
        argv += ["-Prev", ",".join(str(h) for h in prev_hwnds)]
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=cfg.probe_timeout)
    except FileNotFoundError as exc:
        return Probe(1, None, "pwsh not on PATH (%s)" % exc)
    except subprocess.TimeoutExpired:
        return Probe(1, None, "win-probe.ps1 timed out after %.0fs" % cfg.probe_timeout)
    except OSError as exc:
        return Probe(1, None, "win-probe.ps1 could not start (%s)" % exc)

    data = _first_json(proc.stdout)
    note = " ".join(_decode(proc.stderr).split())[:300]
    if data is None:
        warn("win-probe.ps1 produced no JSON (rc=%d): %s" % (proc.returncode, note[:200]))
    elif not data.get("ok"):
        warn("win-probe.ps1 refused: %s -- %s" % (data.get("reason"), note[:160]))
    return Probe(int(proc.returncode), data, note)


def _first_json(raw: bytes) -> Optional[dict]:
    for line in _decode(raw).splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            obj = json.loads(text)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _instance_pid(cfg: ShadowConfig) -> int:
    from .client import discover_endpoint
    try:
        endpoint = discover_endpoint(cfg.run_root, cfg.run_id)
    except Exception as exc:
        warn("no endpoint.json for run %s (%s)" % (cfg.run_id or "<none>", exc))
        return 0
    return int(endpoint.get("pid") or 0)


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #

def _rows(path: str) -> List[dict]:
    rows: List[dict] = []
    if not os.path.isfile(path):
        return rows
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                text = line.strip()
                if not text:
                    continue
                try:
                    obj = json.loads(text)
                except ValueError:
                    warn("ignoring a malformed manifest line in %s" % path)
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except OSError as exc:
        warn("manifest unreadable (%s)" % exc)
    return rows


def read_rows(cfg: ShadowConfig) -> List[dict]:
    """Every ledger row for a run, oldest first (public form of :func:`_rows`)."""
    return _rows(cfg.manifest_path())


def _append_row(path: str, row: dict) -> None:
    """Append-only, single write + flush (S2.7): never rewrite the whole file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unlink(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _same_as_seq(rows: Sequence[dict], digest: str) -> Optional[int]:
    """The seq of the *frame* carrying these pixels (R2) -- so one hop reaches the file."""
    fallback: Optional[int] = None
    for row in reversed(rows):
        if row.get("sha256") != digest:
            continue
        if row.get("shot"):
            return int(row.get("seq") or 0) or None
        if fallback is None:
            fallback = int(row.get("seq") or 0) or None
    return fallback


# --------------------------------------------------------------------------- #
# Ring, promote, lookup (also the `ctl shadow` behind-the-scenes API)
# --------------------------------------------------------------------------- #

def frame_rows(rows: Sequence[dict]) -> List[dict]:
    """Rows that own a file, oldest first."""
    return sorted([r for r in rows if r.get("shot")], key=lambda r: int(r.get("seq") or 0))


def prune(cfg: ShadowConfig) -> List[dict]:
    """Drop the oldest non-promoted frames until the ring fits.  Promoted survive."""
    path = cfg.manifest_path()
    rows = _rows(path)
    frames = frame_rows(rows)
    directory = cfg.shadow_dir()
    live: List[Tuple[dict, int]] = []
    for row in frames:
        file_path = os.path.join(directory, str(row.get("shot")))
        if not os.path.isfile(file_path):
            continue
        live.append((row, os.path.getsize(file_path)))
    if not live:
        return []

    # Promoted frames are outside the budget entirely: they are never dropped and
    # they never push anything else out (R3, `design.md` §5 "promoted 帧不计入额度").
    # Counting them would make one promoted frame silently shrink the allowance for
    # ordinary frames, which is exactly what this docstring promises not to happen.
    droppable = [item for item in live if not item[0].get("promoted")]
    count = len(droppable)
    total = sum(size for _row, size in droppable)
    newest = max(int(row.get("seq") or 0) for row, _size in live)

    deleted: List[dict] = []
    for row, size in droppable:
        if count <= cfg.max_frames and total <= cfg.max_bytes:
            break
        if int(row.get("seq") or 0) >= newest:      # never delete the newest frame
            continue
        _unlink(os.path.join(directory, str(row.get("shot"))))
        count -= 1
        total -= size
        deleted.append(row)
    return deleted


def promote(cfg: ShadowConfig, seq: int, reason: str = "manual") -> Optional[dict]:
    """Mark one frame as promoted (never pruned).  Rewrites the ledger atomically."""
    path = cfg.manifest_path()
    rows = _rows(path)
    hit = [r for r in rows if int(r.get("seq") or 0) == int(seq)]
    if not hit:
        return None
    hit[0]["promoted"] = True
    hit[0]["promote_reason"] = hit[0].get("promote_reason") or reason
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return hit[0]


def find(cfg: ShadowConfig, seq: int) -> Optional[dict]:
    for row in _rows(cfg.manifest_path()):
        if int(row.get("seq") or 0) == int(seq):
            return row
    return None


def frame_path(cfg: ShadowConfig, row: dict) -> str:
    name = row.get("shot")
    return os.path.join(cfg.shadow_dir(), str(name)) if name else ""


def open_frame(path: str) -> None:
    """Open a stored frame with the platform viewer (Windows: ``os.startfile``)."""
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(path)
    if hasattr(os, "startfile"):
        os.startfile(path)                                   # noqa: S606 - evidence viewer
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def summary(cfg: ShadowConfig) -> List[str]:
    """Human summary of the ledger: one line per action."""
    rows = _rows(cfg.manifest_path())
    path = cfg.manifest_path()
    if not rows:
        return ["no shadow records for run %s (%s)" % (cfg.run_id or "<none>", path)]
    frames = frame_rows(rows)
    kept = sum(1 for row in rows if row.get("promoted"))
    lines = ["run %s -- %d action(s), %d frame(s), %d promoted, %d/%d frames, %d/%d MB"
             % (cfg.run_id, len(rows), len(frames), kept, len(frames), cfg.max_frames,
                _live_bytes(cfg) // (1024 * 1024), cfg.max_bytes // (1024 * 1024)),
             "seq    ts                 method        outcome  promoted  frame"]
    for row in rows:
        name = row.get("shot") or ("= seq %s" % row.get("same_as") if row.get("same_as") else "-")
        lines.append("%-6s %-18s %-13s %-8s %-9s %s"
                     % (row.get("seq"), row.get("ts", "")[-8:], row.get("method", ""),
                        row.get("outcome", ""),
                        ("yes" if row.get("promoted") else ""),
                        name))
    if cfg.provenance:
        lines.append("settings: enabled=%s only_changes=%s (%s/%s), probe=%s"
                     % (cfg.enabled, cfg.only_changes,
                        cfg.provenance.get("enabled"), cfg.provenance.get("only_changes"),
                        os.path.relpath(cfg.probe_script, REPO_ROOT) if cfg.probe_script else "-"))
    return lines


def _live_bytes(cfg: ShadowConfig) -> int:
    total = 0
    for row in frame_rows(_rows(cfg.manifest_path())):
        file_path = os.path.join(cfg.shadow_dir(), str(row.get("shot")))
        if os.path.isfile(file_path):
            total += os.path.getsize(file_path)
    return total
