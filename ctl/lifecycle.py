"""Run-id discipline, instance lifecycle, and the safety net around both.

Responsibilities (`design.md` §8, §10 G0; `design-obs-ux.md` §14.2):

* every run gets its own ``<run_root>/<run_id>/`` with a **fresh** workspace,
  its own **configuration area** (the only IDE-side directory that is written),
  its own shots/logs, and an ``endpoint.json`` describing the live instance;
* ``--ensure-clean`` clears a port listener and any process bound to the same
  configuration area / installation directory before starting;
* a recursive SHA-256 fingerprint of the configuration area is taken before and
  after, which is how "source install tree untouched" is demonstrated later.

Nothing here writes outside ``<run_root>`` and ``~/.eclipse-ctl/``.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

from . import BUNDLE_SYMBOLIC_NAME
from .client import Client, write_endpoint
from .console import Console
from .errors import CtlError, NotFoundError, PrereqNotReady
from .targets import Target, Config

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIDGE_DIR = os.path.join(REPO_ROOT, "bridge")
BRIDGE_DIST = os.path.join(BRIDGE_DIR, "dist")
BRIDGE_SOURCE = os.path.join(BRIDGE_DIR, "src", "ctl", "bridge", "LiveBridge.java")
BRIDGE_BUILD = os.path.join(BRIDGE_DIR, "build.py")

SHOTS_DIRNAME = "shots"
WORKSPACE_DIRNAME = "ws"
CONFIGURATION_DIRNAME = "configuration"
INSTALL_DIRNAME = "install"  # only used with --copy (fallback path)


# --------------------------------------------------------------------------- #
# Run identity / layout
# --------------------------------------------------------------------------- #

@dataclass
class RunPaths:
    run_root: str
    run_id: str
    workspace: str
    configuration: str
    install: str
    endpoint: str
    bridge_log: str
    console_log: str
    shots: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "run_root": self.run_root,
            "run_id": self.run_id,
            "workspace": self.workspace,
            "configuration": self.configuration,
            "install": self.install,
            "endpoint": self.endpoint,
            "bridge_log": self.bridge_log,
            "console_log": self.console_log,
            "shots": self.shots,
        }


def make_run_id(target: str, when: Optional[time.struct_time] = None) -> str:
    """``<target>-<yyyymmdd-HHMM>`` (`design.md` §10 G0)."""
    stamp = time.strftime("%Y%m%d-%H%M", when or time.localtime())
    return "%s-%s" % (target, stamp)


def run_paths(run_root: str, run_id: str) -> RunPaths:
    base = os.path.join(run_root, run_id)
    return RunPaths(
        run_root=run_root,
        run_id=run_id,
        workspace=os.path.join(base, WORKSPACE_DIRNAME),
        configuration=os.path.join(base, CONFIGURATION_DIRNAME),
        install=os.path.join(base, INSTALL_DIRNAME),
        endpoint=os.path.join(base, "endpoint.json"),
        bridge_log=os.path.join(base, "bridge.log"),
        console_log=os.path.join(base, "console.log"),
        shots=os.path.join(base, SHOTS_DIRNAME),
    )


def latest_run_id(run_root: str, target: str) -> Optional[str]:
    """Newest ``<target>-*`` run directory, so read-only commands can find it."""
    if not os.path.isdir(run_root):
        return None
    candidates = []
    for name in os.listdir(run_root):
        path = os.path.join(run_root, name)
        if os.path.isdir(path) and name.startswith(target + "-"):
            candidates.append((os.path.getmtime(path), name))
    if not candidates:
        return None
    return sorted(candidates)[-1][1]


def prepare_run(paths: RunPaths, fresh_workspace: bool = True) -> RunPaths:
    """Create the run layout; a fresh workspace is created every run."""
    if fresh_workspace and os.path.isdir(paths.workspace):
        shutil.rmtree(paths.workspace, ignore_errors=True)
    for directory in (paths.workspace, paths.configuration, paths.shots):
        os.makedirs(directory, exist_ok=True)
    return paths


# --------------------------------------------------------------------------- #
# Fingerprint
# --------------------------------------------------------------------------- #

def dir_fingerprint(path: str) -> str:
    """Recursive SHA-256 over a directory tree (paths + contents).

    Returns the literal ``"<absent>"`` when the directory does not exist.  Used
    before/after a run to prove the source configuration area was untouched.
    """
    if not os.path.isdir(path):
        return "<absent>"
    digest = hashlib.sha256()
    entries: List[str] = []
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for name in files:
            full = os.path.join(root, name)
            entries.append(os.path.relpath(full, path).replace("\\", "/"))
        for name in dirs:
            rel = os.path.relpath(os.path.join(root, name), path).replace("\\", "/")
            entries.append(rel + "/")
    for rel in sorted(entries):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        if rel.endswith("/"):
            continue
        full = os.path.join(path, rel.replace("/", os.sep))
        try:
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 16), b""):
                    digest.update(chunk)
        except OSError:
            digest.update(b"<unreadable>")
        digest.update(b"\0")
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# Ports and processes
# --------------------------------------------------------------------------- #

def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, int(port)))
            return True
        except OSError:
            return False


def pick_port(start: int, host: str = "127.0.0.1", span: int = 50) -> int:
    """First free port at or after ``start`` (`design-obs-ux.md` §14.3)."""
    for port in range(int(start), int(start) + span):
        if is_port_free(port, host):
            return port
    raise PrereqNotReady(
        "no free port in [%d, %d); retry: python -m ctl doctor --target gs32" % (start, start + span))


def _run(cmd: Sequence[str], timeout: float = 20.0) -> Tuple[int, str]:
    try:
        proc = subprocess.run(list(cmd), capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return (1, str(exc))
    text = (proc.stdout or b"").decode("utf-8", "replace") + \
           (proc.stderr or b"").decode("utf-8", "replace")
    return (proc.returncode, text)


def _pwsh(script: str, timeout: float = 30.0) -> Tuple[int, str]:
    exe = shutil.which("pwsh") or shutil.which("powershell")
    if not exe:
        return (1, "pwsh not found")
    return _run([exe, "-NoProfile", "-NonInteractive", "-Command", script], timeout=timeout)


def list_port_listeners(port: int) -> List[int]:
    """PIDs with a TCP socket in LISTEN state on ``port``."""
    if sys.platform != "win32":
        return []
    code, out = _run(["netstat", "-ano", "-p", "tcp"])
    if code != 0 and not out:
        return []
    pids: List[int] = []
    needle = ":%d " % int(port)
    for line in out.splitlines():
        upper = line.upper()
        if "LISTENING" not in upper:
            continue
        if needle not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid and pid not in pids:
            pids.append(pid)
    return pids


def list_processes() -> List[Dict[str, str]]:
    """``[{pid, cmdline}, ...]`` for every process (Windows-first, best effort)."""
    if sys.platform != "win32":
        return []
    code, out = _pwsh(
        "Get-CimInstance Win32_Process | ForEach-Object "
        "{ ($_.ProcessId.ToString()) + \"`t\" + ($_.CommandLine -replace \"`t\",' ') }")
    if code != 0:
        return []
    rows = []
    for line in out.splitlines():
        if "\t" not in line:
            continue
        pid_text, cmdline = line.split("\t", 1)
        pid_text = pid_text.strip()
        if not pid_text.isdigit():
            continue
        rows.append({"pid": pid_text, "cmdline": cmdline})
    return rows


def stop_process(pid: int, timeout: float = 10.0) -> bool:
    """Terminate a process by PID.  ``taskkill`` is invoked directly (no shell),
    which sidesteps the shell-quoting trap recorded in `facts-baseline.md` §9."""
    if sys.platform == "win32":
        code, _ = _run(["taskkill", "/F", "/PID", str(int(pid))])
        return code == 0
    try:
        os.kill(int(pid), 9)
        return True
    except OSError:
        return False


def ensure_clean(port: Optional[int] = None, configuration: str = "",
                 install_dir: str = "", dry_run: bool = False,
                 kill_same_install: bool = False) -> List[str]:
    """Clear a port listener plus processes bound to *this run's* directories.

    A process that merely shares the installation tree belongs to another
    session: with ``-configuration`` isolation it does not collide with us, so
    it is reported but **not** killed (killing it would sabotage a sibling run).
    Set ``kill_same_install`` to opt into the design's literal "same install
    directory" sweep.
    """
    actions: List[str] = []
    victims: Dict[int, str] = {}
    observed: Dict[int, str] = {}
    if port:
        for pid in list_port_listeners(int(port)):
            victims[pid] = "listening on port %d" % int(port)
    if configuration or install_dir:
        for row in list_processes():
            cmdline = (row["cmdline"] or "").replace("\\", "/")
            pid = int(row["pid"])
            if configuration and configuration.replace("\\", "/") in cmdline:
                victims.setdefault(pid, "uses configuration %s" % configuration)
            elif install_dir and install_dir.replace("\\", "/") in cmdline:
                (victims if kill_same_install else observed).setdefault(
                    pid, "shares installation %s" % install_dir)
    self_pid = os.getpid()
    for pid, reason in sorted(victims.items()):
        if pid == self_pid:
            continue
        actions.append("pid %d (%s)" % (pid, reason))
        if not dry_run:
            stop_process(pid)
    for pid, reason in sorted(observed.items()):
        if pid == self_pid:
            continue
        actions.append("observed, not killed: pid %d (%s)" % (pid, reason))
    if not dry_run and victims and port:
        deadline = time.time() + 10.0
        while time.time() < deadline and not is_port_free(int(port)):
            time.sleep(0.25)
    return actions


# --------------------------------------------------------------------------- #
# Bridge jar
# --------------------------------------------------------------------------- #

def _read_manifest_symbolic_name(jar: str) -> Tuple[str, str]:
    try:
        with zipfile.ZipFile(jar) as zf:
            raw = zf.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        return ("", "")
    unfolded: List[str] = []
    for line in raw.splitlines():
        if line.startswith(" ") and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    values: Dict[str, str] = {}
    for line in unfolded:
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return (values.get("Bundle-SymbolicName", ""), values.get("Bundle-Version", ""))


def find_bridge_jar() -> Tuple[str, str]:
    """Return ``(jar_path, version)`` for the *current* bridge bundle.

    A jar that does not declare ``eclipse-ctl.bridge`` is stale (the pre-rename
    ``livebridge`` artifact) and is deliberately rejected -- the frozen contract
    fixes the bridge identity (`design-project.md` §15.1).
    """
    candidates = sorted(glob.glob(os.path.join(BRIDGE_DIST, "*.jar")))
    stale: List[str] = []
    for jar in candidates:
        name, version = _read_manifest_symbolic_name(jar)
        if name == BUNDLE_SYMBOLIC_NAME:
            return (jar, version or "0.0.0")
        stale.append("%s (Bundle-SymbolicName=%s)" % (os.path.basename(jar), name or "<none>"))
    if stale:
        raise PrereqNotReady(
            "bridge jar is stale, none declares %s: %s; retry: python -m ctl build --target gs32"
            % (BUNDLE_SYMBOLIC_NAME, ", ".join(stale)))
    if os.path.isfile(BRIDGE_BUILD):
        raise PrereqNotReady(
            "no bridge jar built yet (%s); retry: python -m ctl build --target gs32" % BRIDGE_DIST)
    if os.path.isfile(BRIDGE_SOURCE):
        raise PrereqNotReady(
            "bridge is not buildable: %s is missing (source present); retry: python -m ctl build --target gs32"
            % BRIDGE_BUILD)
    raise PrereqNotReady(
        "bridge source missing (%s); retry: python -m ctl --help" % BRIDGE_SOURCE)


def bridge_buildable() -> Tuple[bool, str]:
    """``(ok, detail)`` for the `doctor` buildability check."""
    try:
        jar, version = find_bridge_jar()
    except PrereqNotReady as exc:
        buildable = os.path.isfile(BRIDGE_SOURCE) and os.path.isfile(BRIDGE_BUILD)
        if buildable:
            return (True, "buildable from source + bridge/build.py (no jar yet)")
        return (False, exc.message)
    return (True, "%s (Bundle-Version %s)" % (os.path.relpath(jar, REPO_ROOT), version))


# --------------------------------------------------------------------------- #
# Bridge install over the console
# --------------------------------------------------------------------------- #

def parse_env(text: str) -> Dict[str, str]:
    """Parse the ``key=value`` payload of ``sys.env``."""
    values: Dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    bundle = values.get("bundle", "")
    if bundle:
        parts = bundle.split()
        for part in parts:
            if "=" in part:
                key, value = part.split("=", 1)
                values.setdefault(key, value)
        values.setdefault("bundle.name", parts[0] if parts else "")
    return values


def wait_for_bridge(port: int, timeout: float = 120.0, poll: float = 1.0,
                    token: str = "") -> bool:
    """Poll ``sys.ping`` until the bridge answers (cold start <= 120 s)."""
    deadline = time.time() + timeout
    client = Client(port=port, token=token)
    while time.time() < deadline:
        if client.ping(timeout=3.0):
            return True
        time.sleep(poll)
    return False


def install_bundle(console: Console, jar: str, wait: float = 8.0) -> int:
    """``install file:<jar>`` then ``start <id>``; the id is read back from `ss`."""
    console.cmd("install file:%s" % jar.replace("\\", "/"), wait=wait)
    listing = console.cmd("ss", wait=wait)
    bundle_id = None
    for row in Console.parse_bundles(listing):
        if BUNDLE_SYMBOLIC_NAME in row["name"]:
            bundle_id = row["id"]
            break
    if bundle_id is None:
        raise CtlError("internal",
                       "bundle %s not present after install; retry: python -m ctl doctor --target gs32"
                       % BUNDLE_SYMBOLIC_NAME)
    console.cmd("start %d" % bundle_id, wait=wait)
    return bundle_id


def uninstall_bundle_residue(configuration: str, jar: str = "") -> List[str]:
    """Delete OSGi bundle-store directories whose ``bundleFile`` points at the bridge.

    The bridge is remembered in the *configuration area*
    (`<configuration>/org.eclipse.osgi/<id>/`), so removing that directory is
    what actually un-installs it when the process is no longer reachable.
    """
    removed: List[str] = []
    store = os.path.join(configuration, "org.eclipse.osgi")
    if not os.path.isdir(store):
        return removed
    for entry in sorted(os.listdir(store)):
        full = os.path.join(store, entry)
        if not os.path.isdir(full):
            continue
        # bundleFile 是**原样复制的 jar（二进制 zip）**，所以不能当文本搜字符串 ——
        # deflate 之后 `eclipse-ctl.bridge` 在字节流里并不连续，按文本搜会**一条都找不到**，
        # 于是 `uninstall --verify-clean` 会在残留仍在的情况下报 `[clean] configuration_clean`（假 PASS）。
        # 正确做法：把 bundleFile 当 zip 打开，读它自己的 MANIFEST。
        found = False
        for gen in sorted(os.listdir(full)) + [""]:
            marker = os.path.join(full, gen, "bundleFile") if gen else os.path.join(full, "bundleFile")
            if not os.path.isfile(marker):
                continue
            if _bundle_file_is_bridge(marker, jar):
                found = True
                break
        if found:
            shutil.rmtree(full, ignore_errors=True)
            removed.append(full)
    return removed


def _bundle_file_is_bridge(path: str, jar: str = "") -> bool:
    """True if this Equinox ``bundleFile`` is (a copy of) the ctl bridge.

    以 **zip 的 MANIFEST** 为准；压缩流里搜不到明文，故不做裸字符串匹配。
    读不开 zip 时退回到「按裸字节搜」（只对未压缩存储的 jar 有效）。
    """
    try:
        with zipfile.ZipFile(path) as z:
            try:
                manifest = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
            except KeyError:
                manifest = ""
            if BUNDLE_SYMBOLIC_NAME in manifest:
                return True
            if jar and os.path.basename(jar) in manifest:
                return True
            return any("eclipse-ctl" in n for n in z.namelist())
    except (zipfile.BadZipFile, OSError):
        try:
            with open(path, "rb") as fh:
                blob = fh.read()
        except OSError:
            return False
        return BUNDLE_SYMBOLIC_NAME.encode() in blob or b"eclipse-ctl" in blob


# --------------------------------------------------------------------------- #
# High-level lifecycle
# --------------------------------------------------------------------------- #

@dataclass
class Instance:
    """A live (or attempted) IDE instance."""

    target: Target
    paths: RunPaths
    port: int
    pid: Optional[int] = None
    bundle_id: Optional[int] = None
    jar: str = ""
    version: str = ""
    env: Dict[str, str] = field(default_factory=dict)
    console: Optional[Console] = None
    pre_fingerprint: str = ""
    post_fingerprint: str = ""
    notes: List[str] = field(default_factory=list)

    def info(self) -> Dict[str, object]:
        return {
            "target": self.target.name,
            "run_id": self.paths.run_id,
            "port": self.port,
            "pid": self.pid,
            "configuration": self.paths.configuration,
            "workspace": self.paths.workspace,
            "bundle": BUNDLE_SYMBOLIC_NAME,
            "bundle_id": self.bundle_id,
            "version": self.version,
            "jar": self.jar,
            "env": self.env,
            "pre_fingerprint": self.pre_fingerprint,
            "post_fingerprint": self.post_fingerprint,
        }


def _launch_args(target: Target, paths: RunPaths, port: int) -> List[str]:
    exe = target.launcher_path()
    if not exe or not os.path.isfile(exe):
        raise PrereqNotReady(
            "launcher not found for target %s: %s; retry: python -m ctl doctor --target %s"
            % (target.name, exe or "<unset>", target.name))
    args = [exe, "-data", paths.workspace,
            "-configuration", paths.configuration,
            "-console", "-nosplash", "-nl", "en_US"]
    # -vmargs must come last; ctl.port / ctl.log are read as system properties.
    args += ["-vmargs", "-Dctl.port=%d" % int(port), "-Dctl.log=%s" % paths.bridge_log]
    return args


def launch(target: Target, paths: RunPaths, port: int, startup_wait: float = 95.0) -> Console:
    """Start the IDE headless-ish with its own configuration area and workspace."""
    console = Console(exe=target.launcher_path(), workspace=paths.workspace,
                      configuration=paths.configuration, startup_wait=startup_wait,
                      log_path=paths.console_log)
    console.args = lambda: _launch_args(target, paths, port)  # type: ignore[assignment]
    console.start(wait=startup_wait)
    return console


def wait_for_workbench(port: int, timeout: float = 180.0, poll: float = 2.0,
                       token: str = "") -> Tuple[bool, str]:
    """Poll ``ui.parts`` until the SWT workbench answers.

    The Gogo console answers long before the UI exists, so a bridge that pings
    is not yet a bridge whose read surface works.  `ui.parts` is UI-backed and
    therefore doubles as the readiness probe (`design.md` §7, F7).
    """
    client = Client(port=port, token=token)
    deadline = time.time() + timeout
    last = "<no attempt>"
    while time.time() < deadline:
        response = client.request("ui.parts", timeout=20.0)
        if response.ok:
            return (True, response.status_line)
        last = response.status_line or "<empty>"
        time.sleep(poll)
    return (False, last)


def install(config: Config, target_name: Optional[str] = None, run_id: Optional[str] = None,
            port: Optional[int] = None, ensure_clean_requested: bool = False,
            startup_wait: float = 15.0, ping_timeout: float = 120.0,
            workbench_timeout: float = 180.0) -> Instance:
    """Full install: isolate -> build check -> launch -> hot-install -> probe.

    Raises :class:`PrereqNotReady` (exit 2) when the machine is not ready, and
    :class:`CtlError` (exit 1) when something that *did* start misbehaves.
    """
    target = config.target(target_name)
    run_id = run_id or make_run_id(target.name)
    paths = run_paths(config.run_root, run_id)
    effective_port = int(port) if port is not None else target.port

    jar, version = find_bridge_jar()  # <-- fails here (exit 2) until bridge is built

    if ensure_clean_requested:
        ensure_clean(port=effective_port, configuration=paths.configuration,
                     install_dir=target.install_dir)

    prepare_run(paths, fresh_workspace=True)
    pre_fp = dir_fingerprint(paths.configuration)

    instance = Instance(target=target, paths=paths, port=effective_port, jar=jar,
                        version=version, pre_fingerprint=pre_fp)

    console = launch(target, paths, effective_port, startup_wait=startup_wait)
    instance.console = console
    instance.pid = console.proc.pid if console.proc else None
    try:
        if not console.wait_for_prompt(timeout=max(60.0, startup_wait)):
            raise CtlError("internal",
                           "console prompt never appeared; %s" % console.diagnose())
        if console.proc is not None and console.proc.poll() is not None:
            raise CtlError("internal",
                           "IDE exited during startup; %s" % console.diagnose())
        instance.bundle_id = install_bundle(console, jar)
        if not wait_for_bridge(effective_port, timeout=ping_timeout, token=config.token):
            raise CtlError("timeout",
                           "bridge did not answer on port %d within %.0f s; retry: python -m ctl status --target %s"
                           % (effective_port, ping_timeout, target.name))
        ready, detail = wait_for_workbench(effective_port, timeout=workbench_timeout,
                                           token=config.token)
        if not ready:
            raise CtlError("noWorkbench",
                           "workbench did not become ready within %.0f s (last: %s); "
                           "retry: python -m ctl doctor --target %s" % (workbench_timeout, detail, target.name))
        instance.notes.append("workbench ready: %s" % detail)
        client = Client(port=effective_port, token=config.token)
        env_response = client.env()
        if not env_response.ok:
            raise CtlError(env_response.code or "internal", env_response.message)
        env = parse_env(env_response.text)
        instance.env = env
        reported_protocol = env.get("protocol")
        if reported_protocol and str(reported_protocol) != str(_expected_protocol()):
            raise CtlError("badrequest",
                           "protocol mismatch: bridge reports %s, client expects %s; retry: python -m ctl build --target %s"
                           % (reported_protocol, _expected_protocol(), target.name))
        write_endpoint(config.run_root, run_id, effective_port, pid=instance.pid,
                       configuration=paths.configuration, token=config.token)
        instance.post_fingerprint = dir_fingerprint(paths.configuration)
        return instance
    except Exception:
        try:
            console.close()
        except Exception:
            pass
        raise


def _expected_protocol() -> int:
    from . import PROTOCOL_VERSION
    return PROTOCOL_VERSION


def stop(instance: Instance) -> None:
    if instance.console is not None:
        instance.console.close()


def uninstall(config: Config, target_name: Optional[str] = None, run_id: Optional[str] = None,
              port: Optional[int] = None, verify_clean: bool = False) -> Dict[str, object]:
    """Stop the instance, delete the configuration-area residue, verify if asked."""
    target = config.target(target_name)
    run_id = run_id or latest_run_id(config.run_root, target.name)
    if not run_id:
        raise NotFoundError(
            "no run for target %s under %s; retry: python -m ctl install --target %s"
            % (target.name, config.run_root, target.name))
    paths = run_paths(config.run_root, run_id)
    effective_port = int(port) if port is not None else target.port
    endpoint = None
    if os.path.isfile(paths.endpoint):
        try:
            with open(paths.endpoint, "r", encoding="utf-8") as fh:
                endpoint = json.load(fh)
        except (OSError, ValueError):
            endpoint = None
    if endpoint and endpoint.get("port"):
        effective_port = int(endpoint["port"])

    stopped: List[str] = []
    if endpoint and endpoint.get("pid"):
        pid = int(endpoint["pid"])
        if stop_process(pid):
            stopped.append("pid %d" % pid)
    # Processes still holding the port/configuration go too.
    cleaned = ensure_clean(port=effective_port, configuration=paths.configuration,
                           install_dir=target.install_dir)
    stopped += [line for line in cleaned if not line.startswith("observed")]
    observed = [line for line in cleaned if line.startswith("observed")]
    removed = uninstall_bundle_residue(paths.configuration)

    result: Dict[str, object] = {
        "target": target.name,
        "run_id": run_id,
        "port": effective_port,
        "stopped": stopped,
        "observed": observed,
        "removed": removed,
        "endpoint": paths.endpoint,
    }
    if verify_clean:
        result["verify_clean"] = verify_clean_report(paths, effective_port, target)
    return result


def verify_clean_report(paths: RunPaths, port: int, target: Target) -> Dict[str, object]:
    """The four-way clean predicate (`design-project.md` §16.5`).

    **2026-10-01 修两处**（原实现有问题）：
    1. `bundle_absent` 与 `configuration_clean` 原先**是同一个表达式**（都是 `not residue`），
       于是「四判据」实为三判据，两者永远不可能分歧 —— 那是**同义反复**，不是覆盖。
       现在 `configuration_clean` 改为**更宽的真检查**：整个运行配置区里**任何**提到桥的地方
       （`config.ini` 文本 / `.manager/*` / 每个 bundleFile 的 MANIFEST）都算不干净。
    2. `no_process` 原先拿 **`target.install_dir`** 做子串匹配 ⇒ 会把**同 target 的其它实例**
       （甚至用户自己开着的那个 IDE）也算成「本 run 没清干净」。P0.4b 已证明同源多实例是**支持**的，
       所以只认 **本 run 的 `-configuration` 路径**。
    """
    residue = uninstall_bundle_residue(paths.configuration) if os.path.isdir(paths.configuration) else []
    mentions = configuration_bridge_mentions(paths.configuration) if os.path.isdir(paths.configuration) else []
    listeners = list_port_listeners(port)
    processes = []
    conf_norm = paths.configuration.replace("\\", "/")
    ws_norm = paths.workspace.replace("\\", "/")
    for row in list_processes():
        # 只认本 run 的**两个 run-unique 标识**：`-configuration <run>/configuration` 与 `-data <run>/ws`。
        # 为什么两个都要：Eclipse 的 launcher 会再起一个 JVM 子进程，子进程的 cmdline 未必原样保留
        # `-configuration`，但 `-data` 在；只认一个会有**漏报**（残留进程却没报不干净）。
        # **不要**匹配 target.install_dir：那是共享的源安装树，并行实例会互相误报（P0.4b 已证多实例支持）。
        cmdline = (row["cmdline"] or "").replace("\\", "/")
        if conf_norm in cmdline or ws_norm in cmdline:
            processes.append(row["pid"])
    return {
        "bundle_absent": not residue,
        "configuration_clean": not mentions,
        "port_released": not listeners,
        "no_process": not processes,
        "residue": residue,
        "mentions": mentions,
        "listeners": listeners,
        "processes": processes,
    }


def configuration_bridge_mentions(configuration: str) -> List[str]:
    """运行配置区里**任何**提到桥的位置（比 residue 更宽的真检查）。

    扫三处：`config.ini` 文本、`org.eclipse.osgi/.manager/*` 的文本、每个 bundleFile 的 MANIFEST。
    """
    hits: List[str] = []
    cini = os.path.join(configuration, "config.ini")
    if os.path.isfile(cini):
        try:
            text = open(cini, encoding="utf-8", errors="replace").read()
            if BUNDLE_SYMBOLIC_NAME in text or "eclipse-ctl" in text:
                hits.append(cini)
        except OSError:
            pass
    store = os.path.join(configuration, "org.eclipse.osgi")
    mgr = os.path.join(store, ".manager")
    if os.path.isdir(mgr):
        for name in sorted(os.listdir(mgr)):
            full = os.path.join(mgr, name)
            if not os.path.isfile(full):
                continue
            try:
                blob = open(full, "rb").read()
            except OSError:
                continue
            if BUNDLE_SYMBOLIC_NAME.encode() in blob or b"eclipse-ctl" in blob:
                hits.append(full)
    if os.path.isdir(store):
        for entry in sorted(os.listdir(store)):
            full = os.path.join(store, entry)
            if not os.path.isdir(full):
                continue
            for gen in sorted(os.listdir(full)) + [""]:
                marker = (os.path.join(full, gen, "bundleFile") if gen
                          else os.path.join(full, "bundleFile"))
                if os.path.isfile(marker) and _bundle_file_is_bridge(marker):
                    hits.append(marker)
    return hits


def gc(run_root: str, keep: int = 3, dry_run: bool = False) -> List[str]:
    """Remove all but the newest ``keep`` run directories."""
    removed: List[str] = []
    if not os.path.isdir(run_root):
        return removed
    runs = []
    for name in os.listdir(run_root):
        path = os.path.join(run_root, name)
        if os.path.isdir(path):
            runs.append((os.path.getmtime(path), path))
    runs.sort(reverse=True)
    for _mtime, path in runs[max(keep, 0):]:
        removed.append(path)
        if not dry_run:
            shutil.rmtree(path, ignore_errors=True)
    return removed
