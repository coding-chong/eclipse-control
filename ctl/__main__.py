"""``python -m ctl`` -- the eclipse-ctl command line.

The subcommand set is exactly the table in `design-obs-ux.md` §14.3; nothing is
invented here.  Exit codes are three-state (`design-obs-ux.md` §14.3):

* ``0`` success
* ``1`` failure -- a definite FAIL, including usage errors and lookups that do
  not exist (an ``ERR notfound`` line is printed)
* ``2`` prerequisite not ready -- the environment never got far enough to run

stdout carries results only; every diagnostic goes to stderr.
"""

from __future__ import annotations

import argparse
import ast
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

from . import PROTOCOL_VERSION, __version__
from . import shadow
from .client import BRIDGE_UI_TIMEOUT_MS, Client, discover_endpoint
from .console import command_is_dangerous
from .errors import (
    CtlError,
    EndpointNotFound,
    NotFoundError,
    PrereqNotReady,
    UsageError,
)
from .lifecycle import (
    BRIDGE_BUILD,
    REPO_ROOT,
    _run,
    bridge_buildable,
    gc as lifecycle_gc,
    install as lifecycle_install,
    is_port_free,
    latest_run_id,
    list_port_listeners,
    list_processes,
    run_paths,
    uninstall as lifecycle_uninstall,
)
from .parse import command_ids
from .run import cmd_run as cmd_run_door
from .targets import (
    Config,
    Target,
    add_target,
    list_targets,
    load,
    remove_target,
)

#: Subcommands, in the order of the §14.3 table (used for `--help` and the
#: doc/CLI consistency check in `preflight`).
SUBCOMMANDS = (
    "doctor",
    "install",
    "uninstall",
    "upgrade",
    "status",
    "targets",
    "commands",
    "recipes",
    "gc",
    "tree",
    "parts",
    "viewids",
    "persp",
    "cmd",
    "open",
    "close",
    "shell",
    "verify",
    "build",
    "preflight",
    "shadow",
    # The one door (`deliverable-shape.md` §7): a script on stdin, the library
    # pre-imported.  Every other subcommand above stays exactly as it was.
    "run",
)

#: Retry hint appended to every bridge-originated error (`A12`: each CLI error
#: string must carry a re-runnable command).
RETRY_HINTS: Dict[str, str] = {
    "timeout": 'python -m ctl shell --run-id <run_id> -c "sys.ping"',
    "notfound": 'python -m ctl commands --json',
    "disabled": "python -m ctl doctor --target <target>",
    "unhandled": 'python -m ctl commands find --text "Reset Perspective"',
    "noWorkbench": "python -m ctl status --target <target>",
    "busy": "python -m ctl status --target <target>",
    "badrequest": 'python -m ctl commands find --text "Reset Perspective"',
    "internal": "python -m ctl doctor --target <target>",
}

RECIPE_ORDER = ("view-and-shot", "open-sources", "build-and-console", "diag-when-hung", "record")
RECIPES_DIR = os.path.join(REPO_ROOT, "recipes")

_BASH_PLACEHOLDER = re.compile(r"<[A-Za-z_][A-Za-z0-9_\-]*>")


# --------------------------------------------------------------------------- #
# Argument parsing scaffold
# --------------------------------------------------------------------------- #

class CtlParser(argparse.ArgumentParser):
    """ArgumentParser that reports errors as ``ERR`` lines with exit code 1."""

    def error(self, message: str):  # noqa: D401 - argparse override
        code = "notfound" if "invalid choice" in message else "badrequest"
        print("ERR %s %s; retry: python -m ctl --help" % (code, message), file=sys.stderr)
        raise SystemExit(1)


def _common() -> argparse.ArgumentParser:
    parent = CtlParser(add_help=False)
    parent.add_argument("--target", action="append", metavar="NAME[,NAME]",
                        help="target name; repeatable and comma separated (default: default_target)")
    parent.add_argument("--run-id", dest="run_id", metavar="ID",
                        help="run instance id (default: <target>-<yyyymmdd-HHMM>, or the newest run)")
    parent.add_argument("--retry", type=float, default=0.0, metavar="SECONDS",
                        help="retry with exponential backoff for up to SECONDS when the "
                             "bridge cannot be reached; 0 = fail immediately (default). "
                             "After a reconnect the bridge is re-checked with sys.env and a "
                             "different bundle/protocol aborts the command (D4)")

    parent.add_argument("--port", type=int, help="override the bridge port")
    parent.add_argument("--ensure-clean", dest="ensure_clean", action="store_true",
                        help="clear a same-port listener and same-configuration processes first")
    parent.add_argument("--json", action="store_true", help="machine-readable output")
    parent.add_argument("--config", metavar="PATH", help="config file (default: ~/.eclipse-ctl/config.json)")
    # Shadow shots (R7).  `default=None` on purpose: a plain store_true default of
    # False cannot be told apart from "the flag was not given", and the
    # precedence (flag > env > file > default) depends on that distinction.
    parent.add_argument("--no-shadow", dest="no_shadow", action="store_true", default=None,
                        help="do not record a shadow frame after write actions "
                             "(the ledger is on by default: ctl shadow --run-id <id>)")
    parent.add_argument("--shadow-only-changes", dest="shadow_only_changes",
                        action="store_true", default=None,
                        help="keep a shadow frame only when the window set changed, the "
                             "action failed, a dialog appeared or the answer carried nothing")
    return parent


def _write_opts() -> argparse.ArgumentParser:
    parent = CtlParser(add_help=False)
    parent.add_argument("--yes", action="store_true",
                        help="actually send the write (otherwise dry-run)")
    return parent


def _gc_opts() -> argparse.ArgumentParser:
    """`gc`'s own option set -- deliberately **no** `--run-id`/`--port`/`--retry`.

    `gc` prunes the whole ``<run_root>``; it previously inherited ``--run-id``
    and silently ignored it, so passing it looked like scoping while every other
    session's runs were being deleted (2026-10-01).  An option that cannot be
    honoured must not be accepted.
    """
    parent = CtlParser(add_help=False)
    parent.add_argument("--config", metavar="PATH", help="config file (default: ~/.eclipse-ctl/config.json)")
    parent.add_argument("--json", action="store_true", help="machine-readable output")
    parent.add_argument("--keep", type=int, metavar="N",
                        help="how many of the newest run directories to keep (default: from config)")
    parent.add_argument("--yes", action="store_true",
                        help="actually delete; without it gc only prints what it would delete")
    parent.add_argument("--force-live", dest="force_live", action="store_true",
                        help="also delete runs whose recorded pid is still alive (default: skip them)")
    return parent


def build_parser() -> CtlParser:
    common = _common()
    write = _write_opts()

    parser = CtlParser(
        prog="ctl",
        description="eclipse-ctl -- control an Eclipse-family IDE from the outside.",
        epilog="Exit codes: 0 success, 1 failure (incl. ERRs), 2 prerequisite not ready.",
    )
    sub = parser.add_subparsers(dest="command", title="subcommands")

    def add(name: str, help_text: str, parents=(common,)) -> CtlParser:
        return sub.add_parser(name, help=help_text, parents=list(parents))

    # -- lifecycle ---------------------------------------------------------- #
    add("doctor", "self-check: 8 checks, every one with a verdict")
    add("install", "isolate -> hot-install the bridge -> probe -> write endpoint.json")
    add("uninstall", "stop the instance, remove configuration-area residue, verify clean")
    add("upgrade", "rebuild the bridge and bring the instance back up")
    p_status = add("status", "bridge / protocol version, port, workbench state")
    p_targets = add("targets", "manage the target matrix")
    p_commands = add("commands", "export the Eclipse command table")
    p_recipes = add("recipes", "list / run usage recipes")
    add("gc", "prune old run directories (destructive; needs --yes)", parents=(_gc_opts(),))
    p_tree = add("tree", "dump the SWT widget tree")
    add("parts", "list the workbench parts (views / editors / perspective)")
    p_viewids = add("viewids", "list registered view ids")
    add("persp", "list perspectives and the active one")
    p_cmd = add("cmd", "execute an Eclipse command (write; needs --yes)", parents=(common, write))
    p_open = add("open", "open a file in the editor (write; needs --yes)", parents=(common, write))
    p_close = add("close", "close a view (write; needs --yes)", parents=(common, write))
    p_shell = add("shell", "interactive / one-shot bridge shell")
    add("verify", "acceptance cases")
    add("build", "compile and package the bridge jar")
    add("preflight", "doctor + verify + doc/CLI consistency + CHANGELOG entry")
    p_shadow = add("shadow", "shadow shots: what the screen looked like after each write")
    p_run = add("run", "one door: run a Python script from stdin against the bridge")

    # -- doctor ------------------------------------------------------------- #
    # (options come from `common`; nothing else)

    # -- install / uninstall / upgrade -------------------------------------- #
    for name in ("install", "uninstall", "upgrade"):
        sp = sub.choices[name]
        if name == "uninstall":
            sp.add_argument("--verify-clean", dest="verify_clean", action="store_true",
                            help="check the four-way clean predicate afterwards")

    # -- targets ------------------------------------------------------------ #
    p_targets.set_defaults(targets_action="list")
    tsub = p_targets.add_subparsers(dest="targets_action")
    tsub.add_parser("list", help="list targets", parents=[common])
    t_add = tsub.add_parser("add", help="add / override a target", parents=[common])
    t_add.add_argument("name")
    t_add.add_argument("--source-dir", dest="source_dir", required=True)
    t_add.add_argument("--java-level", dest="java_level")
    t_add.add_argument("--eclipse-version", dest="eclipse_version")
    t_add.add_argument("--product")
    t_add.add_argument("--jre")
    t_add.add_argument("--launcher")
    t_add.add_argument("--vendor-prefix", dest="vendor_prefix")
    t_add.add_argument("--default-port", dest="default_port", type=int)
    t_rm = tsub.add_parser("remove", help="remove a target", parents=[common])
    t_rm.add_argument("name")

    # -- commands ----------------------------------------------------------- #
    p_commands.set_defaults(commands_action="export")
    csub = p_commands.add_subparsers(dest="commands_action")
    c_export = csub.add_parser("export", help="dump the full command table", parents=[common])
    c_export.add_argument("--full", action="store_true",
                          help="emit the six-field table per command (id/name/category/"
                               "parameters/handled/vendor) instead of bare ids; costs one "
                               "cmd.query per command")
    c_find = csub.add_parser("find", help="reverse lookup: UI text -> command id", parents=[common])
    c_find.add_argument("--text", required=True)

    # -- recipes ------------------------------------------------------------ #
    p_recipes.set_defaults(recipes_action="list")
    rsub = p_recipes.add_subparsers(dest="recipes_action")
    rsub.add_parser("list", help="list recipes", parents=[common])
    r_run = rsub.add_parser("run", help="run a recipe's bash blocks in order", parents=[common])
    r_run.add_argument("name")

    # -- single-call reads --------------------------------------------------- #
    p_tree.add_argument("depth", nargs="?", type=int, default=3)
    p_viewids.add_argument("prefix", nargs="?")
    p_cmd.add_argument("command_id")
    p_cmd.add_argument("params", nargs="*", metavar="key=value")
    p_open.add_argument("path")
    p_close.add_argument("view_id")

    # -- shell --------------------------------------------------------------- #
    p_shell.add_argument("-c", dest="command", metavar="REQUEST")
    p_shell.add_argument("--record", metavar="PATH")
    p_shell.add_argument("--allow-dangerous", dest="allow_dangerous", action="store_true")

    # -- verify -------------------------------------------------------------- #
    p_verify = sub.choices["verify"]
    group = p_verify.add_mutually_exclusive_group()
    group.add_argument("--case", metavar="NAME")
    group.add_argument("--group", metavar="GROUP")
    group.add_argument("--all", dest="all_", action="store_true")
    p_verify.add_argument("--no-screen-guard", dest="no_screen_guard", action="store_true",
                          help="disable the before/after window snapshot around writes "
                               "(diagnostic only: it is what lets 'OK lies' through)")

    # -- build --------------------------------------------------------------- #
    p_build = sub.choices["build"]
    p_build.add_argument("--out", metavar="JAR")
    p_build.add_argument("--src", metavar="TREE",
                         help="IDE install tree to compile against "
                              "(default: the target's install_dir)")
    p_build.add_argument("--ecj", metavar="JAR",
                         help="ECJ batch compiler jar (default: the target's, else one found in --src)")
    p_build.add_argument("--jre", metavar="JAVA",
                         help="java.exe that runs ECJ (default: the target's JRE)")

    # -- preflight ----------------------------------------------------------- #
    # (options come from `common`)

    # -- shadow -------------------------------------------------------------- #
    p_shadow.set_defaults(shadow_action="summary")
    p_shadow.add_argument("--seq", type=int, metavar="N",
                          help="print one action's record and its frame path")
    p_shadow.add_argument("--promote", type=int, metavar="N",
                          help="pin one frame so the ring never prunes it")
    p_shadow.add_argument("--open", dest="open_", nargs="?", const=-1, type=int, metavar="N",
                          help="open a frame with the OS viewer (bare = the frame --seq names)")
    p_shadow.add_argument("--prune", action="store_true",
                          help="apply the ring limits now")
    p_shadow.add_argument("--max-frames", dest="max_frames", type=int, metavar="N",
                          help="override the ring's frame budget for this call")
    p_shadow.add_argument("--max-bytes", dest="max_bytes", type=int, metavar="BYTES",
                          help="override the ring's byte budget for this call")

    # -- run (the one door) --------------------------------------------------- #
    p_run.add_argument("--helpers", metavar="PATH",
                       help="Python file exec'd first, in the same namespace as the script")
    p_run.add_argument("--no-start", dest="no_start", action="store_true",
                       help="never start an instance: fail closed (exit 2) when no live "
                            "bridge answers sys.ping")
    p_run.add_argument("--stop", action="store_true",
                       help="tear the instance down after the script and report the "
                            "four-way clean predicate (bundle_absent / configuration_clean "
                            "/ port_released / no_process)")
    p_run.add_argument("--doctor", action="store_true",
                       help="print the readiness self-check first; informational only -- "
                            "it scans the whole run root, so its exit code never gates "
                            "the script")

    for name in SUBCOMMANDS:
        sub.choices[name].set_defaults(func=HANDLERS[name])
    return parser


# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #

def _emit_json(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _hint(code: str, target: str, run_id: Optional[str]) -> str:
    template = RETRY_HINTS.get(code, "python -m ctl doctor --target <target>")
    return template.replace("<target>", target).replace("<run_id>", run_id or "<run_id>")


def _bridge_fail(response, target: str, run_id: Optional[str]) -> CtlError:
    code = response.code or "internal"
    message = response.message or response.status_line or "<empty response>"
    if response.timed_out:
        return CtlError("timeout",
                        "no response within %.0f ms; retry: %s"
                        % (BRIDGE_UI_TIMEOUT_MS, _hint("timeout", target, run_id)))
    return CtlError(code, "%s; retry: %s" % (message, _hint(code, target, run_id)))


def _print_response(response, args, parsed=None) -> int:
    if getattr(args, "json", False):
        payload = {"status": response.status_line, "payload": response.payload,
                   "raw": response.raw, "elapsed_ms": int(response.elapsed * 1000)}
        if parsed is not None:
            payload["parsed"] = parsed
        _emit_json(payload)
    else:
        print(response.status_line)
        for line in response.payload:
            print(line)
    return 0 if response.ok else 1


# --------------------------------------------------------------------------- #
# Config / target resolution
# --------------------------------------------------------------------------- #

def _load_config(args) -> Config:
    flags = {
        "config": getattr(args, "config", None),
        "port": getattr(args, "port", None),
    }
    return load({k: v for k, v in flags.items() if v is not None})


def _target_names(args, config: Config) -> List[str]:
    raw = getattr(args, "target", None) or []
    names: List[str] = []
    for item in raw:
        for part in str(item).split(","):
            part = part.strip()
            if part and part not in names:
                names.append(part)
    return names or [config.default_target]


def _single_target(args, config: Config) -> Target:
    names = _target_names(args, config)
    if len(names) > 1:
        raise UsageError("this command takes a single --target, got: %s" % ", ".join(names))
    # `--run-id` 已经点名了某个实例。调用方没写 `--target` 时，若能从 run id 反推出唯一的
    # target 名就采用它 —— 否则 `"target"` 字段与 retry 提示会写成**默认** target，
    # 对一个属于别的产品的 run 就是错的（实测：`--run-id ccs12-p42` 曾报 `target = gs32`，
    # 截断提示随之给出跑不通的 `retry: … --target gs32`）。
    if not getattr(args, "target", None):
        rid = getattr(args, "run_id", None)
        if rid:
            matched = [n for n in config.target_names() if rid == n or rid.startswith(n + "-")]
            if len(matched) == 1:
                return config.target(matched[0])
    return config.target(names[0])


def _client_for(config: Config, target: Target, run_id: Optional[str],
                port: Optional[int],
                retry: float = 0.0) -> Tuple[Client, str]:
    """Resolve the endpoint for a run; never guess a port."""
    if port is not None:
        # An explicit --port still names a *run* when --run-id is given: keep the
        # run binding so the shadow ledger can record (and know which pid to
        # photograph).  Without a run id there is nowhere to write, so the client
        # stays as it was -- `Client.port()` short-circuits on the explicit port, so
        # binding these two fields cannot change which socket is used.
        return Client(port=int(port),
                      run_root=config.run_root if run_id else None,
                      run_id=run_id or None, retry=retry), (run_id or "")
    rid = run_id or latest_run_id(config.run_root, target.name)
    if not rid:
        raise EndpointNotFound(
            "no run for target %s under %s; retry: python -m ctl install --target %s"
            % (target.name, config.run_root, target.name))
    endpoint = discover_endpoint(config.run_root, rid)
    return Client(port=endpoint["port"],
                  run_root=config.run_root, run_id=rid, retry=retry), rid


def _connect(args, config: Config) -> Tuple[Client, Target, str]:
    target = _single_target(args, config)
    client, rid = _client_for(config, target, getattr(args, "run_id", None),
                              getattr(args, "port", None),
                              retry=getattr(args, "retry", 0.0))
    return client, target, rid


def _send(client: Client, request: str, target: Target, run_id: str, args) -> int:
    response = client.request(request)
    if not response.ok:
        raise _bridge_fail(response, target.name, run_id)
    return _print_response(response, args)


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #

def _java_probe(java_exe: str) -> Tuple[Optional[str], Optional[int]]:
    _code, out = _run([java_exe, "-version"], timeout=20)
    match = re.search(r'version "([^"]+)"', out)
    version = match.group(1) if match else None
    code, out = _run([java_exe, "--list-modules"], timeout=20)
    modules = None
    if code == 0:
        lines = [line for line in out.splitlines() if re.match(r"^\s*\S+@\S+", line)]
        modules = len(lines) or None
    return version, modules


def _check(name: str, status: str, detail: str) -> Dict[str, str]:
    return {"name": name, "status": status, "detail": detail}


def _doctor_checks(config: Config, target: Target, args) -> List[Dict[str, str]]:
    checks: List[Dict[str, str]] = []

    # 1. source_dir exists and is an Eclipse-family product
    marker = os.path.join(target.install_dir, ".eclipseproduct")
    plugins = os.path.join(target.install_dir, "plugins")
    if os.path.isdir(target.install_dir) and (os.path.isfile(marker) or os.path.isdir(plugins)):
        checks.append(_check("source_dir exists", "PASS", target.install_dir))
    else:
        checks.append(_check("source_dir exists", "FAIL",
                             "not an Eclipse-family tree: %s" % target.install_dir))

    # 2. platform version / JRE version / JRE module count
    eclipse_version = None
    if os.path.isfile(marker):
        try:
            with open(marker, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.startswith("version="):
                        eclipse_version = line.split("=", 1)[1].strip()
        except OSError:
            eclipse_version = None
    java_exe = target.java_exe()
    java_version, modules = _java_probe(java_exe) if java_exe else (None, None)
    version_ok = (eclipse_version == target.eclipse_version and java_version is not None)
    detail = "Eclipse %s (expected %s); JRE %s (expected %s, %s modules)" % (
        eclipse_version or "<unknown>", target.eclipse_version,
        java_version or "<missing>", target.jre,
        modules if modules is not None else "?")
    if version_ok:
        checks.append(_check("platform / JRE", "PASS", detail))
    else:
        checks.append(_check("platform / JRE", "FAIL", detail + " -- at " + target.install_dir))

    # 3. ECJ batch compiler present (required to build the bridge in-tree)
    ecj = target.ecj_jar()
    if ecj:
        checks.append(_check("ECJ compiler", "PASS", os.path.basename(ecj)))
    else:
        checks.append(_check("ECJ compiler", "FAIL",
                             "no org.eclipse.jdt.core.compiler.batch_*.jar under %s/plugins" % target.install_dir))

    # 4. bridge jar present, or buildable from source -- and it must be a jar
    #    this target can actually load (java_target vs the jar's class-file level).
    ok, detail = bridge_buildable(target)
    checks.append(_check("bridge buildable", "PASS" if ok else "FAIL", detail))

    # 5. is the target port usable by a *new* run?
    #    A listener under our own run root is one of *our* instances, not a
    #    foreign one -- reporting it as FAIL (and pointing the retry at
    #    `--ensure-clean`, which kills the same-port listener) told a healthy
    #    session to destroy itself.  Measured 2026-10-01.
    # PIDs are compared across two sources that disagree on type --
    # `list_processes()` yields strings, `list_port_listeners()` yields ints --
    # so normalise to int here or every `in` test silently fails.
    leftovers = []
    run_marker = os.path.normpath(config.run_root).replace("\\", "/")
    for row in list_processes():
        cmdline = (row["cmdline"] or "").replace("\\", "/")
        if run_marker and run_marker in cmdline:
            try:
                leftovers.append(int(row["pid"]))
            except (TypeError, ValueError):
                continue
    listeners = [] if is_port_free(target.port) else list_port_listeners(target.port)
    ours = sorted(pid for pid in listeners if pid in leftovers)
    foreign = sorted(pid for pid in listeners if pid not in leftovers)
    if not listeners:
        checks.append(_check("port %d" % target.port, "PASS", "free"))
    elif foreign:
        checks.append(_check("port %d" % target.port, "FAIL",
                             "in use by foreign pid(s) %s; retry: python -m ctl doctor --ensure-clean --target %s"
                             % (foreign, target.name)))
    else:
        checks.append(_check("port %d" % target.port, "INFO",
                             "held by our own run (pid(s) %s) -- that instance is alive; "
                             "use `python -m ctl status --target %s` to talk to it, or a different --port "
                             "for a new run" % (ours, target.name)))

    # 6. other instances under *our* run root.
    #    Siblings (a different run_id) do not collide: each run has its own
    #    configuration area, workspace and port.  Only a process that also holds
    #    the target port would actually block a new run -- and check 5 says that.
    siblings = [pid for pid in leftovers if pid not in ours]
    if not leftovers:
        checks.append(_check("no leftover instance", "PASS", "0 process under %s" % config.run_root))
    elif siblings:
        checks.append(_check("no leftover instance", "INFO",
                             "%d sibling instance(s) under %s (pid(s) %s); they use their own run_id/"
                             "configuration/port and do not block a new run"
                             % (len(siblings), config.run_root,
                                ",".join(str(p) for p in siblings))))
    else:
        checks.append(_check("no leftover instance", "INFO",
                             "%d instance(s) under %s (pid(s) %s) belong to the port in check 5"
                             % (len(ours), config.run_root, ",".join(str(p) for p in ours))))

    # 7. run_root writable + free space
    run_root = config.run_root
    probe = run_root
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        usage = None
        if os.path.isdir(probe):
            import shutil as _shutil
            usage = _shutil.disk_usage(probe)
        writable = os.path.isdir(probe) and os.access(probe, os.W_OK)
    except OSError:
        writable = False
        usage = None
    if writable:
        free = ("%.1f GiB free" % (usage.free / (1 << 30))) if usage else "writable"
        checks.append(_check("run_root writable", "PASS", "%s (%s)" % (run_root, free)))
    else:
        checks.append(_check("run_root writable", "FAIL",
                             "cannot write under %s; retry: python -m ctl doctor --config <path>" % probe))

    # 8. installed version vs expected (only when a run exists)
    rid = getattr(args, "run_id", None) or latest_run_id(config.run_root, target.name)
    if rid and os.path.isfile(run_paths(config.run_root, rid).endpoint):
        try:
            client, _rid = _client_for(config, target, rid, None)
            response = client.env()
            if response.ok:
                fields = {}
                for line in response.text.splitlines():
                    if "=" in line:
                        key, value = line.split("=", 1)
                        fields[key.strip()] = value.strip()
                protocol = fields.get("protocol")
                bundle = fields.get("bundle", "")
                match = re.search(r"version=(\S+)", bundle)
                installed_version = match.group(1) if match else "<unreported>"
                if protocol is not None and str(protocol) != str(PROTOCOL_VERSION):
                    checks.append(_check("installed version", "FAIL",
                                         "protocol %s != %s; retry: python -m ctl build --target %s"
                                         % (protocol, PROTOCOL_VERSION, target.name)))
                else:
                    checks.append(_check("installed version", "PASS",
                                         "version %s, protocol %s" % (installed_version, protocol)))
            else:
                checks.append(_check("installed version", "FAIL",
                                     response.status_line or "no response"))
        except CtlError as exc:
            checks.append(_check("installed version", "FAIL", exc.message))
    else:
        checks.append(_check("installed version", "SKIP", "no run installed for target %s" % target.name))
    return checks


def _cmd_doctor(args) -> int:
    config = _load_config(args)
    names = _target_names(args, config)
    exit_code = 0
    report = []
    for name in names:
        target = config.target(name)
        checks = _doctor_checks(config, target, args)
        report.append({"target": name, "checks": checks})
        if not args.json:
            print("target %s" % name)
            for item in checks:
                print("  [%s] %-24s %s" % (item["status"], item["name"], item["detail"]))
        if any(item["status"] == "FAIL" for item in checks):
            exit_code = 2
    if args.json:
        _emit_json(report)
    elif exit_code == 0:
        print("all checks passed")
    return exit_code


# --------------------------------------------------------------------------- #
# install / uninstall / upgrade
# --------------------------------------------------------------------------- #

def _cmd_install(args) -> int:
    config = _load_config(args)
    target = _single_target(args, config)
    instance = lifecycle_install(config, target.name, getattr(args, "run_id", None),
                                 getattr(args, "port", None),
                                 getattr(args, "ensure_clean", False))
    info = instance.info()
    if args.json:
        _emit_json(info)
    else:
        protocol = info["env"].get("protocol", str(PROTOCOL_VERSION)) if isinstance(info["env"], dict) else PROTOCOL_VERSION
        print("run_id      %s" % info["run_id"])
        print("configuration %s" % info["configuration"])
        print("workspace   %s" % info["workspace"])
        print("endpoint    %s" % instance.paths.endpoint)
        print("OK bridge live on 127.0.0.1:%s (protocol %s, version %s)"
              % (info["port"], protocol, info["version"]))
    return 0


def _cmd_uninstall(args) -> int:
    config = _load_config(args)
    target = _single_target(args, config)
    result = lifecycle_uninstall(config, target.name, getattr(args, "run_id", None),
                                 getattr(args, "port", None),
                                 getattr(args, "verify_clean", False))
    if args.json:
        _emit_json(result)
        return 0
    print("stopped: %s" % (", ".join(result["stopped"]) or "none"))
    print("residue removed: %s" % (len(result["removed"])))
    report = result.get("verify_clean")
    if isinstance(report, dict):
        for key in ("bundle_absent", "configuration_clean", "port_released", "no_process"):
            print("  [%s] %s" % ("clean" if report.get(key) else "DIRTY", key))
    return 0


def _cmd_upgrade(args) -> int:
    config = _load_config(args)
    target = _single_target(args, config)
    code = _build_bridge(target.name, getattr(args, "out", None), config, args)
    if code != 0:
        return code

    # 端口是 run 身份的一部分：CLI 靠 endpoint.json 发现它，**不该在一次升级里漂掉**。
    # 实测（2026-10-01，P3.6）：不带 --port 时新实例起在了默认 8777，而原 run 是 8939 ——
    # 长脚本/外部工具手里握着旧端口，会突然连不上。
    # 所以：用户显式给了 --port 就听用户的；否则沿用这个 run 已记录的端口。
    carried_port = getattr(args, "port", None)
    rid = getattr(args, "run_id", None)
    if carried_port is None:
        try:
            rid = rid or latest_run_id(config.run_root, target.name)
            if rid:
                carried_port = int(discover_endpoint(config.run_root, rid)["port"])
                if not getattr(args, "run_id", None):
                    args.run_id = rid      # 没有 --run-id 时锁定到被升级的那个 run
        except (NotFoundError, CtlError, KeyError, TypeError, ValueError):
            carried_port = None            # 没有既有 run（或读不到）⇒ 交给 install 决定

    try:
        lifecycle_uninstall(config, target.name, getattr(args, "run_id", None),
                            carried_port, False)
    except (NotFoundError, CtlError):
        pass
    args.port = carried_port
    # The bridge cannot be reached over the console from outside the process, so
    # "upgrade" is a rebuild plus a controlled restart rather than a hot update.
    print("restarting instance on the rebuilt jar (hot console update is not reachable externally)",
          file=sys.stderr)
    return _cmd_install(args)


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #

def _cmd_status(args) -> int:
    config = _load_config(args)
    client, target, rid = _connect(args, config)
    response = client.request("sys.env")
    if not response.ok:
        raise _bridge_fail(response, target.name, rid)
    fields = {}
    for line in response.text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip()
    workbench = client.request("ui.parts", timeout=10.0)
    perspective = None
    if workbench.ok:
        match = re.search(r"^perspective id=(\S+)", workbench.text, re.M)
        perspective = match.group(1) if match else None
    info = {
        "target": target.name,
        "run_id": rid,
        "port": client.port(),
        "bundle": fields.get("bundle"),
        "protocol": fields.get("protocol"),
        "java": fields.get("java.version"),
        "workbench": perspective or ("not created" if not workbench.ok else "no perspective"),
    }
    if args.json:
        _emit_json(info)
    else:
        print("target       %s" % info["target"])
        print("run_id       %s" % info["run_id"])
        print("port         %s" % info["port"])
        print("bundle       %s" % info["bundle"])
        print("protocol     %s" % info["protocol"])
        print("java         %s" % info["java"])
        print("workbench    %s" % info["workbench"])
    return 0


# --------------------------------------------------------------------------- #
# targets
# --------------------------------------------------------------------------- #

def _cmd_targets(args) -> int:
    action = getattr(args, "targets_action", "list") or "list"
    if action == "list":
        config = _load_config(args)
        rows = []
        for target in list_targets(config):
            rows.append({
                "name": target.name,
                "install_dir": target.install_dir,
                "eclipse_version": target.eclipse_version,
                "jre": target.jre,
                "java_target": target.java_target,
                "product": target.product,
                "default_port": target.default_port,
                "port": target.port,
            })
        if args.json:
            _emit_json(rows)
        else:
            print("%-8s %-10s %-6s %-6s %-24s %-6s %s" %
                  ("NAME", "ECLIPSE", "JRE", "JAVA", "PRODUCT", "PORT", "INSTALL_DIR"))
            for row in rows:
                print("%-8s %-10s %-6s %-6s %-24s %-6s %s" %
                      (row["name"], row["eclipse_version"], row["jre"], row["java_target"],
                       row["product"], row["port"], row["install_dir"]))
        return 0
    if action == "add":
        fields = {
            "install_dir": args.source_dir,
            "java_target": args.java_level,
            "eclipse_version": args.eclipse_version,
            "product": args.product,
            "jre": args.jre,
            "launcher": args.launcher,
            "vendor_prefix": args.vendor_prefix,
            "default_port": args.default_port,
            "port": args.default_port,
        }
        path = add_target(args.name, fields, args.config)
        print("OK target %s written to %s" % (args.name, path))
        return 0
    if action == "remove":
        path = remove_target(args.name, args.config)
        print("OK target %s removed (%s)" % (args.name, path))
        return 0
    raise UsageError("unknown targets action: %s; retry: python -m ctl targets list" % action)


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def _fetch_command_ids(client: Client, target: Target,
                       rid: str) -> Tuple[List[str], Optional[int], List[str]]:
    """Read the full command table.

    桥的 `cmd.list` 负载形态（2026-10-01 实测原文）：

        OK
        ICommandService via IWorkbench.getService -> true
          <command id>                     <- 每行一个，前导两空格
          ...
        definedCommandIds total=666 matched(prefix=)=666 returned=666 truncated=false
        handlerOnly registry=ok total=1 inactiveContributors=0 (handler without a <command> declaration; ...)
          + com.gs.chipsetting.commands.opthandler
        caveat=handler-only ids cannot be enumerated through ICommandService; ...

    ⇒ **`total=` 不在行首**，旧写法 `re.match(r"^\\s*total=(\\d+)")` 永远匹配不到，
    于是 `total` 恒为 `None`、`truncated` 恒为 `False` —— 「截断检测」形同虚设。
    改为：优先认带 `definedCommandIds` 的那一行，退而求其次认任何含 `total=` 的行。

    id 块与 handler-only 块的解析**不在本函数里**：唯一的权威实现在
    :func:`ctl.parse.command_ids`（`ctl run` 的门共用它，见 `measurement-hygiene.md`
    §13.7）。这里只保留结算行 `total=` 的解析 —— 它认的是**带 `definedCommandIds`
    前缀**的那一行，与 id 块框定是两件事。
    """
    response = client.request("cmd.list", timeout=30.0)
    if not response.ok:
        raise _bridge_fail(response, target.name, rid)
    # 先认带 `definedCommandIds` 的汇总行（它有 total/matched/returned/truncated 四个值）；
    # 再退到任何含 `total=` 的行。**不要**让后面的 `handlerOnly ... total=1` 覆盖它。
    total = None
    for line in response.payload:
        if "definedCommandIds" in line:
            m = re.search(r"\btotal=(\d+)", line)
            if m:
                total = int(m.group(1))
                break
    if total is None:
        for line in response.payload:
            m = re.search(r"\btotal=(\d+)", line)
            if m:
                total = int(m.group(1))
                break

    # id 块（头 `ICommandService …` / 尾 `definedCommandIds …` 框定，块内逐行照抄，**不许**
    # 加 `"." in token` 之类的启发式）与 handler-only 块（行形如 `  + <id>`，单独返回、不混进
    # ids）的解析**不在本函数里** —— 唯一权威实现是 `ctl.parse.command_ids`，`ctl run` 的门
    # 共用它。CCS 上 `undo` / `redo` 不带点，任何点号判据都会静默吞掉它们（805 vs 807）。
    ids, handler_only = command_ids(response.payload)
    return ids, total, handler_only


#: R8 定死的那六个字段。顺序即产物里的列序。
_COMMAND_FIELDS: Tuple[str, ...] = ("id", "name", "category", "parameters", "handled", "vendor")


def _command_vendor(command_id: str, vendor_prefix: str) -> str:
    """第 6 个字段（厂商标记）—— 由 id 本身判定，不额外问桥。

    `AUTOGEN:::` 那些是 Eclipse 自己生成的包装命令，不属于任何厂商。
    """
    if command_id.startswith("AUTOGEN:::"):
        return "autogen"
    for prefix in (vendor_prefix, "com.gs", "com.ti"):
        if prefix and command_id.startswith(prefix + "."):
            return prefix
    parts = command_id.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else command_id


def _query_command_fields(client: Client, command_id: str,
                          vendor_prefix: str) -> Dict[str, Any]:
    """一次 `cmd.query`，解析成表里的 6 个字段。

    负载是 `key=value` 行 —— 这里**一律按键取值、不按下标**：`name=` / `category=`
    的值是自由文本，按下标取字段正是 `measurement-hygiene.md` §13.4 那个坑。
    `cmd.query` 失败（如已消失的命令）不抛，如实留空，由调用方看见。
    """
    row: Dict[str, Any] = {"id": command_id, "name": "", "category": "",
                           "parameters": "", "handled": "",
                           "vendor": _command_vendor(command_id, vendor_prefix)}
    response = client.request("cmd.query %s" % command_id, timeout=10.0)
    if not response.ok:
        return row
    for line in response.payload:
        text = line.strip()
        for key in ("handled", "name", "category"):
            head = key + "="
            if text.startswith(head):
                value = text[len(head):]
                if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                row[key] = value
        head = "parameters="
        if text.startswith(head):
            row["parameters"] = text[len(head):]
    return row


def _cmd_commands(args) -> int:
    action = getattr(args, "commands_action", "export") or "export"
    config = _load_config(args)
    client, target, rid = _connect(args, config)
    if action == "export":
        ids, total, handler_only = _fetch_command_ids(client, target, rid)
        truncated = bool(total is not None and total > len(ids))
        if truncated:
            print("warning: bridge reported total=%d but returned %d (truncated); "
                  "retry: python -m ctl build --target %s"
                  % (total, len(ids), target.name), file=sys.stderr)

        if getattr(args, "full", False):
            # R8 的那张表：每条 6 个字段。`cmd.query` 一条一次，所以 n 条 ≈ n 次往返；
            # 进度走 stderr —— stdout 只放结果（R12′.2）。
            rows: List[Dict[str, Any]] = []
            for index, command_id in enumerate(ids, 1):
                rows.append(_query_command_fields(client, command_id, target.vendor_prefix))
                # 进度**只在人看的那次**打。`--json` 的契约是「stderr 为空」（A11b′ / R12′.2）——
                # 机器消费者不要噪声，否则 `--json 2>err` 不再为空（实测曾因此违反 A11b′）。
                if not args.json and index % 100 == 0:
                    print("export: %d/%d" % (index, len(ids)), file=sys.stderr)
            if args.json:
                _emit_json({"target": target.name, "run_id": rid, "total": total,
                            "returned": len(rows), "truncated": truncated,
                            "fields": list(_COMMAND_FIELDS), "commands": rows,
                            "handler_only": handler_only})
            else:
                print("\t".join(_COMMAND_FIELDS))
                for row in rows:
                    print("\t".join(str(row.get(field, "")) for field in _COMMAND_FIELDS))
            return 0

        if args.json:
            _emit_json({"target": target.name, "run_id": rid, "total": total,
                        "returned": len(ids), "truncated": truncated,
                        "commands": ids, "handler_only": handler_only})
        else:
            print("total=%s returned=%d handler_only=%d"
                  % (total if total is not None else "?", len(ids), len(handler_only)))
            for command_id in ids:
                print(command_id)
            for command_id in handler_only:
                print("+ " + command_id)
        return 0
    if action == "find":
        needle = args.text.lower()
        ids, _total, _handler_only = _fetch_command_ids(client, target, rid)
        hits = []
        for command_id in ids:
            response = client.request("cmd.query %s" % command_id, timeout=10.0)
            if not response.ok:
                continue
            for line in response.payload:
                # **锚定**到 `name=` 行：`cmd.query` 在命令声明了参数时还会吐 `  param id=… name="…"`
                # 行，`re.search` 会拿参数名当命令名（假命中）。命令自身的 name 行不带前导空格。
                match = re.match(r'\s*name="([^"]*)"', line)
                if match and needle in match.group(1).lower():
                    hits.append({"id": command_id, "name": match.group(1)})
                    break
        if not hits:
            raise NotFoundError(
                "no command whose name contains %r; retry: python -m ctl commands find --text \"Reset Perspective\""
                % args.text)
        if args.json:
            _emit_json(hits)
        else:
            for hit in hits:
                print("%s  %s" % (hit["id"], hit["name"]))
        return 0
    raise UsageError("unknown commands action: %s; retry: python -m ctl commands --json" % action)


# --------------------------------------------------------------------------- #
# recipes
# --------------------------------------------------------------------------- #

def _recipe_files() -> Dict[str, str]:
    found: Dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(RECIPES_DIR, "*.md"))):
        found[os.path.splitext(os.path.basename(path))[0]] = path
    return found


def _recipe_description(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("# "):
                    return line[2:].strip()
                if line:
                    return line
    except OSError:
        pass
    return ""


def _recipe_bash_blocks(path: str) -> List[str]:
    blocks: List[str] = []
    current: Optional[List[str]] = None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                stripped = line.strip()
                if current is None:
                    if stripped.startswith("```") and "bash" in stripped:
                        current = []
                    continue
                if stripped.startswith("```"):
                    blocks.append("\n".join(current))
                    current = None
                    continue
                current.append(line.rstrip("\n"))
    except OSError as exc:
        raise CtlError("internal",
                       "recipe unreadable: %s (%s); retry: python -m ctl recipes list" % (path, exc))
    return blocks


def _cmd_recipes(args) -> int:
    action = getattr(args, "recipes_action", "list") or "list"
    files = _recipe_files()
    if action == "list":
        rows = []
        for name in RECIPE_ORDER:
            rows.append({"name": name, "file": files.get(name),
                         "description": _recipe_description(files[name]) if name in files else "MISSING"})
        for name, path in files.items():
            if name not in RECIPE_ORDER:
                rows.append({"name": name, "file": path, "description": _recipe_description(path)})
        if args.json:
            _emit_json(rows)
        else:
            for row in rows:
                print("%-18s %s" % (row["name"], row["description"]))
        return 0
    if action == "run":
        path = files.get(args.name)
        if not path:
            raise NotFoundError("no such recipe: %s; retry: python -m ctl recipes list" % args.name)
        bash = os.environ.get("SHELL_BIN") or _find_bash()
        if not bash:
            raise PrereqNotReady(
                "no bash found to run recipe %s; retry: python -m ctl recipes list" % args.name)
        for index, block in enumerate(_recipe_bash_blocks(path), 1):
            placeholder = _BASH_PLACEHOLDER.search(block)
            if placeholder:
                raise UsageError(
                    "recipe %s block %d still contains placeholder %s -- replace it before running; "
                    "retry: python -m ctl recipes run %s"
                    % (args.name, index, placeholder.group(0), args.name))
            if not args.json:
                print("--- %s block %d ---" % (args.name, index))
            result = subprocess.run([bash, "-c", block], cwd=REPO_ROOT)
            if result.returncode != 0:
                raise CtlError("internal",
                               "recipe %s block %d failed (rc=%d); retry: python -m ctl recipes run %s"
                               % (args.name, index, result.returncode, args.name))
        return 0
    raise UsageError("unknown recipes action: %s; retry: python -m ctl recipes list" % action)


def _find_bash() -> Optional[str]:
    import shutil as _shutil
    for candidate in ("bash", "C:/Program Files/Git/bin/bash.exe",
                      "C:/Program Files (x86)/Git/bin/bash.exe"):
        found = _shutil.which(candidate) if not os.path.isabs(candidate) else (
            candidate if os.path.isfile(candidate) else None)
        if found:
            return found
    return None


# --------------------------------------------------------------------------- #
# gc
# --------------------------------------------------------------------------- #

def _cmd_gc(args) -> int:
    config = _load_config(args)
    keep = args.keep if args.keep is not None else config.keep_runs
    if keep < 0:
        raise UsageError("gc --keep must be >= 0, got: %d" % keep)
    dry_run = not args.yes
    result = lifecycle_gc(config.run_root, keep, dry_run=dry_run,
                          skip_live=not args.force_live)
    if args.json:
        _emit_json({"run_root": config.run_root, "keep": keep, "dry_run": dry_run,
                    "removed": result["removed"], "skipped_live": result["skipped_live"],
                    "failed": result["failed"]})
        # Same exit-code contract as the human path: "nothing to remove" and
        # "could not remove" must not look alike (measurement-hygiene 13.6).
        return 1 if result["failed"] else 0
    print("run_root %s (keep %d)%s"
          % (config.run_root, keep, "  [dry-run: nothing deleted, pass --yes to delete]" if dry_run else ""))
    for name in result["removed"]:
        print("%s %s" % ("would remove" if dry_run else "removed", name))
    for entry in result["skipped_live"]:
        print("skipped     %s" % entry)
    for entry in result["failed"]:
        print("FAILED      %s" % entry)
    if not (result["removed"] or result["skipped_live"] or result["failed"]):
        print("nothing to remove")
    return 1 if result["failed"] else 0


# --------------------------------------------------------------------------- #
# single-call reads and writes
# --------------------------------------------------------------------------- #

def _cmd_tree(args) -> int:
    client, target, rid = _connect(args, _load_config(args))
    return _send(client, "ui.tree %d" % args.depth, target, rid, args)


def _cmd_parts(args) -> int:
    config = _load_config(args)
    client, target, rid = _connect(args, config)
    response = client.request("ui.parts")
    if not response.ok:
        raise _bridge_fail(response, target.name, rid)
    match = re.search(r"^perspective id=(\S+)", response.text, re.M)
    views = re.findall(r"^\s*view id=(\S+)", response.text, re.M)
    editors = re.search(r"^editors=(\d+)", response.text, re.M)
    parsed = {"perspective": match.group(1) if match else None,
              "views": views,
              "editors": int(editors.group(1)) if editors else None}
    return _print_response(response, args, parsed)


def _cmd_viewids(args) -> int:
    client, target, rid = _connect(args, _load_config(args))
    request = "ui.viewids" + ((" " + args.prefix) if args.prefix else "")
    response = client.request(request)
    if not response.ok:
        raise _bridge_fail(response, target.name, rid)
    total = re.search(r"total=(\d+)", response.text)
    ids = re.findall(r"^\s*view id=(\S+)", response.text, re.M)
    parsed = {"total": int(total.group(1)) if total else None, "views": ids}
    return _print_response(response, args, parsed)


def _cmd_persp(args) -> int:
    client, target, rid = _connect(args, _load_config(args))
    return _send(client, "ui.persp", target, rid, args)


def _dry_run(args, request: str) -> int:
    """Print what would be sent and stop -- without reading endpoint.json or connecting."""
    if args.json:
        _emit_json({"dry_run": True, "request": request})
    else:
        print("DRY-RUN %s" % request)
    return 0


def _cmd_cmd(args) -> int:
    if args.params:
        pairs = []
        for item in args.params:
            if "=" not in item:
                raise UsageError("parameter must be key=value, got %r; retry: python -m ctl commands find --text \"Reset Perspective\"" % item)
            pairs.append(item)
        request = "cmd.runp %s %s" % (args.command_id, " ".join(pairs))
    else:
        request = "cmd.run %s" % args.command_id
    if not args.yes:
        return _dry_run(args, request)
    config = _load_config(args)
    client, target, rid = _connect(args, config)
    return _send(client, request, target, rid, args)


def _cmd_open(args) -> int:
    request = "ui.open %s" % args.path
    if not args.yes:
        return _dry_run(args, request)
    client, target, rid = _connect(args, _load_config(args))
    return _send(client, request, target, rid, args)


def _cmd_close(args) -> int:
    request = "ui.close %s" % args.view_id
    if not args.yes:
        return _dry_run(args, request)
    client, target, rid = _connect(args, _load_config(args))
    return _send(client, request, target, rid, args)


# --------------------------------------------------------------------------- #
# shell
# --------------------------------------------------------------------------- #

def _cmd_shell(args) -> int:
    config = _load_config(args)
    target = _single_target(args, config)
    allow_dangerous = bool(getattr(args, "allow_dangerous", False)) or config.allow_dangerous

    def one(line: str) -> int:
        text = line.strip()
        if not text:
            return 0
        if command_is_dangerous(text) and not allow_dangerous:
            raise CtlError("disabled",
                           "dangerous command refused: %r; retry: python -m ctl shell --target %s --allow-dangerous -c %r"
                           % (text, target.name, text))
        if "." not in text.split()[0]:
            raise UsageError(
                "%r is not a bridge method (Gogo console forwarding is not wired in this round); "
                'retry: python -m ctl shell -c "sys.ping"' % text)
        if args.run_id and not args.port:
            client = Client(run_root=config.run_root, run_id=args.run_id)
            rid = args.run_id
        else:
            client, rid = _client_for(config, target, args.run_id, args.port)
        response = client.request(text)
        if args.json:
            _emit_json({"request": text, "status": response.status_line,
                        "payload": response.payload})
        else:
            print(response.status_line)
            for payload_line in response.payload:
                print(payload_line)
        if args.record:
            _record(args.record, text, response.raw)
        return 0 if response.ok else 1

    if args.command:
        return one(args.command)
    if args.json:
        raise UsageError("--json requires -c; retry: python -m ctl shell -c \"sys.ping\"")
    print("eclipse-ctl shell -- one request per line, blank line quits", file=sys.stderr)
    while True:
        try:
            line = input("ctl> ")
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            break
        if not line.strip():
            break
        try:
            one(line)
        except CtlError as exc:
            print(exc.line(), file=sys.stderr)
    return 0


def _record(path: str, request: str, response: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("# %s\n" % time.strftime("%Y-%m-%dT%H:%M:%S"))
        fh.write("> %s\n" % request)
        for line in response.splitlines():
            fh.write("#   %s\n" % line)


# --------------------------------------------------------------------------- #
# shadow
# --------------------------------------------------------------------------- #

def _shadow_config(args, config: Config, run_id: str):
    """Effective shadow settings for a `shadow` invocation (RunRoot + run pinned)."""
    cfg = shadow.resolve(getattr(args, "no_shadow", None),
                         getattr(args, "shadow_only_changes", None),
                         config_path=config.config_path)
    cfg.run_root = config.run_root
    cfg.run_id = run_id
    frames = getattr(args, "max_frames", None)
    if frames:
        cfg.max_frames = max(1, int(frames))
    limit = getattr(args, "max_bytes", None)
    if limit:
        cfg.max_bytes = max(1, int(limit))
    return cfg


def _shadow_run_id(args, config: Config, target: Target) -> str:
    rid = getattr(args, "run_id", None) or latest_run_id(config.run_root, target.name)
    if not rid:
        raise EndpointNotFound(
            "no run for target %s under %s; retry: python -m ctl install --target %s"
            % (target.name, config.run_root, target.name))
    # An explicit --run-id is not validated above, so a typo used to read as
    # "no shadow records" *and still exit 0* -- a lookup error must never look
    # like an empty result (`design-obs-ux.md` 14.3: exit 1 covers "find" errors
    # and carries `ERR notfound`).  Only the *directory* is checked, on purpose:
    # reviewing frames has to keep working with the bridge dead -- that is the
    # whole point of a ledger -- so this must never touch endpoint.json.
    if not os.path.isdir(os.path.join(config.run_root, rid)):
        raise EndpointNotFound(
            "no run %s under %s; retry: python -m ctl install --target %s"
            % (rid, config.run_root, target.name))
    return rid


def _shadow_describe(cfg, row: dict) -> List[str]:
    path = shadow.frame_path(cfg, row)
    if row.get("shot"):
        frame = "%s (%s bytes)%s" % (path, row.get("bytes"),
                                     "" if os.path.isfile(path) else "  [pruned]")
    elif row.get("same_as"):
        frame = "<same pixels as seq %s -- no new file>" % row.get("same_as")
    else:
        frame = "<no frame kept>"
    lines = ["seq=%s  %s  %s  outcome=%s%s"
             % (row.get("seq"), row.get("ts"), row.get("method"), row.get("outcome"),
                "  promoted (%s)" % row.get("promote_reason") if row.get("promoted") else ""),
             "  args: %s" % (row.get("args") or "-"),
             "  frame: %s" % frame]
    if row.get("sha256"):
        lines.append("  sha256: %s" % row["sha256"])
    target = row.get("target") or {}
    lines.append("  target: class=%s hwnd=%s title=%r bounds=%s pid=%s"
                 % (target.get("class"), target.get("hwnd"), target.get("title"),
                    target.get("bounds"), target.get("pid")))
    windows = row.get("windows") or {}
    lines.append("  windows: %s (%s)" % (windows.get("count"), windows.get("delta")))
    if row.get("probe"):
        lines.append("  probe: %s -- %s" % (row["probe"].get("reason"), row["probe"].get("note")))
    if row.get("dialog"):
        lines.append("  dialog: %s" % row["dialog"])
    return lines


def _cmd_shadow(args) -> int:
    config = _load_config(args)
    target = _single_target(args, config)
    rid = _shadow_run_id(args, config, target)
    cfg = _shadow_config(args, config, rid)

    open_seq = getattr(args, "open_", None)
    if args.seq is not None and args.promote is not None:
        raise UsageError("--seq and --promote are different actions; retry: python -m ctl shadow --run-id %s" % rid)
    if args.promote is not None and args.prune:
        raise UsageError("--promote and --prune are different actions; retry: python -m ctl shadow --run-id %s" % rid)

    if args.promote is not None:
        row = shadow.promote(cfg, args.promote)
        if row is None:
            print("ERR notfound no shadow record with seq=%s in run %s; retry: "
                  "python -m ctl shadow --run-id %s" % (args.promote, rid, rid), file=sys.stderr)
            return 1
        if args.json:
            _emit_json({"run_id": rid, "promoted": row})
        else:
            print("promoted seq=%s (%s)" % (row.get("seq"), row.get("promote_reason") or "manual"))
        return 0

    if args.prune:
        deleted = shadow.prune(cfg)
        if args.json:
            _emit_json({"run_id": rid, "pruned": [r.get("seq") for r in deleted]})
        elif deleted:
            for row in deleted:
                print("pruned seq=%s %s (%s bytes)" % (row.get("seq"), row.get("shot"), row.get("bytes")))
        else:
            print("nothing to prune (limits: %d frame(s) / %d byte(s))"
                  % (cfg.max_frames, cfg.max_bytes))
        return 0

    if args.seq is not None or (open_seq is not None and open_seq >= 0):
        seq = args.seq if args.seq is not None else open_seq
        if open_seq is not None and open_seq >= 0 and args.seq is not None and open_seq != args.seq:
            raise UsageError("--open %s and --seq %s name different frames; retry: "
                             "python -m ctl shadow --run-id %s --seq %s"
                             % (open_seq, args.seq, rid, args.seq))
        row = shadow.find(cfg, seq)
        if row is None:
            print("ERR notfound no shadow record with seq=%s in run %s; retry: "
                  "python -m ctl shadow --run-id %s" % (seq, rid, rid), file=sys.stderr)
            return 1
        if args.json:
            _emit_json({"run_id": rid, "record": row, "path": shadow.frame_path(cfg, row)})
        else:
            for line in _shadow_describe(cfg, row):
                print(line)
        if open_seq is not None:
            path = shadow.frame_path(cfg, row)
            if not path or not os.path.isfile(path):
                print("ERR notfound seq=%s has no frame on disk (pruned or never kept); retry: "
                      "python -m ctl shadow --run-id %s" % (seq, rid), file=sys.stderr)
                return 1
            shadow.open_frame(path)
        return 0

    if open_seq is not None:
        raise UsageError("--open needs a frame: use --seq N --open, or --open N; "
                         "retry: python -m ctl shadow --run-id %s" % rid)

    if args.json:
        rows = shadow.read_rows(cfg)
        _emit_json({"run_id": rid, "manifest": cfg.manifest_path(),
                    "max_frames": cfg.max_frames, "max_bytes": cfg.max_bytes,
                    "enabled": cfg.enabled, "only_changes": cfg.only_changes,
                    "records": rows})
        return 0
    for line in shadow.summary(cfg):
        print(line)
    return 0


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #

def _cmd_verify(args) -> int:
    from .verify.runner import GROUPS, Runner

    config = _load_config(args)
    names = _target_names(args, config)
    if not (args.case or args.group or args.all_):
        raise UsageError("verify needs --case, --group or --all; retry: python -m ctl verify --case read.ping")

    selection_runner = Runner(config, names[0], getattr(args, "run_id", None),
                              getattr(args, "port", None))
    cases = selection_runner.select(args.case, args.group, args.all_)
    if not cases:
        raise PrereqNotReady(
            "no cases matched (case=%r group=%r; known groups: %s); retry: python -m ctl verify --case read.ping"
            % (args.case, args.group, ",".join(GROUPS)),
            code="notfound")

    screen_guard = not getattr(args, "no_screen_guard", False)
    if not args.json:
        print("screen guard: %s" % ("on" if screen_guard else
                                    "OFF (writes are judged by the status line and the read-back only)"))

    report = []
    failed = env_not_ready = 0
    for name in names:
        runner = Runner(config, name, getattr(args, "run_id", None),
                        getattr(args, "port", None),
                        screen_guard=screen_guard)
        try:
            results = runner.run(cases)
        except (PrereqNotReady, EndpointNotFound) as exc:
            env_not_ready += 1
            report.append({"target": name, "env": "not ready", "detail": exc.message, "cases": []})
            if not args.json:
                print("target %s: [ENV-NOT-READY] %s" % (name, exc.message))
            continue
        report.append({"target": name, "env": "ready",
                       "cases": [result.to_dict() for result in results]})
        for result in results:
            if result.skipped:
                status = "SKIP"
            else:
                status = "PASS" if result.passed else "FAIL"
                failed += 1 if not result.passed else 0
            if not args.json:
                print("[%s] %-20s %s" % (status, result.name, result.detail))
                for evidence in result.evidence:
                    print("      %s" % evidence)
    if args.json:
        _emit_json(report)
    if failed:
        return 1
    if env_not_ready:
        return 2
    return 0


# --------------------------------------------------------------------------- #
# build / preflight
# --------------------------------------------------------------------------- #

def _build_bridge(target_name: str, out: Optional[str], config: Config, args) -> int:
    if not os.path.isfile(BRIDGE_BUILD):
        raise PrereqNotReady(
            "bridge build entry missing: %s; retry: python -m ctl --help" % BRIDGE_BUILD)
    argv = [sys.executable, BRIDGE_BUILD, "--target", target_name]
    if out:
        argv += ["--out", out]
    # Resolve the target's toolchain explicitly instead of letting build.py
    # rediscover it: ccs12 ships no JDT, so its ECJ can only come from the
    # target definition (or from an explicit --ecj). Explicit CLI flags win.
    target = config.target(target_name)
    src = getattr(args, "src", None) or target.install_dir
    ecj = getattr(args, "ecj", None) or target.ecj_jar()
    jre = getattr(args, "jre", None) or target.java_exe()
    for flag, value in (("--src", src), ("--ecj", ecj), ("--jre", jre)):
        if value:
            argv += [flag, value]
    print("running %s" % " ".join(argv), file=sys.stderr)
    return subprocess.run(argv, cwd=REPO_ROOT).returncode


def _cmd_build(args) -> int:
    config = _load_config(args)
    target = _single_target(args, config)
    return _build_bridge(target.name, getattr(args, "out", None), config, args)


#: A slash-joined run of ≥2 backticked bare names -- the shape a doc uses to
#: enumerate subcommands without repeating the ``ctl`` prefix, e.g.
#: ``\`shell\` / \`status\` / \`parts\```.
_BARE_ENUM = re.compile(r"`[a-z][a-z0-9\-]*`(?:\s*/\s*`[a-z][a-z0-9\-]*`)+")


def _doc_commands(text: str) -> List[str]:
    """Command words that the docs actually *invoke* (code spans / shell lines).

    Prose like "the ctl description" must not be mistaken for a command, so only
    backticked spans and lines beginning with ``ctl`` / ``python -m ctl`` count
    as invocations.  A *bare* slash-joined list of backticked names is read as
    subcommands only when the line says so (``… 等子命令``): elsewhere
    ``port`` / ``pid``, ``undo`` / ``redo`` and the frozen error codes are all
    slash-listed too, and none of them is a command.
    """
    pattern = re.compile(r"(?:python -m ctl|ctl)\s+([a-z][a-z0-9\-]+)")
    found: List[str] = []
    for span in re.findall(r"`([^`\n]+)`", text):
        match = pattern.match(span.strip())
        if match:
            found.append(match.group(1))
    for line in text.splitlines():
        match = pattern.match(re.sub(r"^\s*\$?\s*", "", line))
        if match:
            found.append(match.group(1))
        if "子命令" in line or "subcommand" in line.lower():
            for enumeration in _BARE_ENUM.findall(line):
                found.extend(re.findall(r"`([^`]+)`", enumeration))
    return found


def _doc_command_consistency() -> Tuple[bool, str]:
    """Every subcommand the repo docs mention must be a real one.

    That covers ``ctl <word>`` / ``python -m ctl <word>`` *and* a bare
    ``\\`shell\\` / \\`status\\` / … 等子命令`` list, so prose that enumerates
    subcommands by name alone can no longer name a removed one (F5).
    """
    problems: List[str] = []
    checked = 0
    for path in sorted(glob.glob(os.path.join(REPO_ROOT, "*.md"))) + \
            sorted(glob.glob(os.path.join(REPO_ROOT, "skill", "*.md"))):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        checked += 1
        for word in _doc_commands(text):
            if word in SUBCOMMANDS or word == "help":
                continue
            problems.append("%s: %s" % (os.path.basename(path), word))
    if problems:
        return (False, "unknown subcommand(s) referenced in docs: %s" % ", ".join(sorted(set(problems))))
    return (True, "%d doc file(s) scanned" % checked)


#: Directories whose Python must stay stdlib-only (R11'.3 / deliverable-shape.md C3).
_STDLIB_ONLY_DIRS = ("ctl", "bridge", "tools")

#: Import roots that resolve inside this repo rather than to a distribution.
_STDLIB_ONLY_LOCAL = ("ctl",)


def _import_roots(source: str) -> List[Tuple[str, int]]:
    """Import roots in ``source`` -> ``[(root, lineno), …]``, in source order.

    Only the *root* of each dotted name is kept (``from urllib.parse import
    quote`` -> ``urllib``).  Every ``Import`` / ``ImportFrom`` is inspected --
    module level *and* nested -- because a lazy ``import requests`` inside a
    function is still a third-party dependency.  Relative imports (``from .
    import x``) resolve inside this package and are skipped.
    """
    roots: List[Tuple[str, int]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.append((alias.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            roots.append((node.module.split(".")[0], node.lineno))
    return sorted(roots, key=lambda row: row[1])


def _stdlib_only_check() -> Tuple[bool, str]:
    """Every shipped Python module must import stdlib (or ``ctl``) only.

    This is the runnable judge `R11'.3` never had: until 2026-10-04 the
    "standard library only" dependency policy lived in two module docstrings
    and nothing checked it, so a stray ``import requests`` would have shipped
    silently.  Each file's imports are parsed and any root that is
    neither in ``sys.stdlib_module_names`` nor part of this package is
    reported with ``file:line``.
    """
    problems: List[str] = []
    checked = 0
    for root_dir in _STDLIB_ONLY_DIRS:
        base = os.path.join(REPO_ROOT, root_dir)
        if not os.path.isdir(base):
            continue
        for path in sorted(glob.glob(os.path.join(base, "**", "*.py"), recursive=True)):
            if "__pycache__" in path.split(os.sep):
                continue
            rel = os.path.relpath(path, REPO_ROOT)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    imports = _import_roots(fh.read())
            except (OSError, SyntaxError) as exc:
                problems.append("%s: unreadable/unparsable (%s)" % (rel, exc))
                continue
            checked += 1
            for module, lineno in imports:
                if module in sys.stdlib_module_names or module in _STDLIB_ONLY_LOCAL:
                    continue
                problems.append("%s:%d: %s" % (rel, lineno, module))
    if problems:
        return (False, "non-stdlib import(s): %s" % "; ".join(problems))
    return (True, "%d module(s) scanned in %s" % (checked, "/".join(_STDLIB_ONLY_DIRS)))


def _changelog_has_version() -> Tuple[bool, str]:
    path = os.path.join(REPO_ROOT, "CHANGELOG.md")
    if not os.path.isfile(path):
        return (False, "CHANGELOG.md missing")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        return (False, "CHANGELOG.md unreadable: %s" % exc)
    if __version__ in text:
        return (True, "entry for %s present" % __version__)
    return (False, "no entry for version %s" % __version__)


def _cmd_preflight(args) -> int:
    config = _load_config(args)
    names = _target_names(args, config)
    problems = 0
    code = _cmd_doctor(args)
    if code != 0:
        problems += 1
        print("[FAIL] doctor -> exit %d" % code)
    else:
        print("[PASS] doctor")

    # verify --all on the first target
    verify_args = argparse.Namespace(**vars(args))
    verify_args.case = None
    verify_args.group = None
    verify_args.all_ = True
    # The screen guard is what turns "OK + nothing changed" from a PASS into a
    # FAIL/SUSPECT (`errors.plugin-id-as-view`).  `--no-screen-guard` exists only
    # as a diagnostic knob that reproduces the hole, so the acceptance gate must
    # never inherit it -- pin it off here rather than relying on this parser
    # happening not to define the flag (2026-10-01).
    verify_args.no_screen_guard = False
    try:
        verify_code = _cmd_verify(verify_args)
    except PrereqNotReady as exc:
        verify_code = 2
        print("[ENV-NOT-READY] verify: %s" % exc.message)
    print("[%s] verify --all (target %s, exit %d)"
          % ("PASS" if verify_code == 0 else "FAIL", names[0], verify_code))
    if verify_code != 0:
        problems += 1

    ok, detail = _doc_command_consistency()
    print("[%s] doc/CLI command consistency: %s" % ("PASS" if ok else "FAIL", detail))
    if not ok:
        problems += 1

    ok, detail = _stdlib_only_check()
    print("[%s] stdlib-only imports: %s" % ("PASS" if ok else "FAIL", detail))
    if not ok:
        problems += 1

    ok, detail = _changelog_has_version()
    print("[%s] CHANGELOG: %s" % ("PASS" if ok else "FAIL", detail))
    if not ok:
        problems += 1

    return 1 if problems else 0


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #

def _cmd_run_door(args) -> int:
    """`ctl run` plus the two lifecycle flags R10' requires (`--doctor` / `--stop`).

    **`--doctor` is informational, never a gate.** `_cmd_doctor` scans the *whole* run
    root, so in a healthy session it reports FAIL for every sibling run and exits 2
    (measured 2026-10-01) -- and the `--ensure-clean` retry it suggests would kill *this*
    instance.  Its exit code is therefore discarded.

    **`--stop` reuses the already-tested teardown path** (`_cmd_uninstall`) rather than
    re-implementing it, and runs even when the script failed: leaking a live instance is
    worse than a failed script.
    """
    if getattr(args, "doctor", False):
        _cmd_doctor(args)
    code = cmd_run_door(args)
    if getattr(args, "stop", False):
        args.verify_clean = True
        try:
            stop_code = _cmd_uninstall(args)
        except Exception as exc:  # cleanup must never mask the script's own result
            print("ERR stop failed: %s" % exc, file=sys.stderr)
            stop_code = 1
        if stop_code:
            return stop_code
    return code


HANDLERS = {
    "doctor": _cmd_doctor,
    "install": _cmd_install,
    "uninstall": _cmd_uninstall,
    "upgrade": _cmd_upgrade,
    "status": _cmd_status,
    "targets": _cmd_targets,
    "commands": _cmd_commands,
    "recipes": _cmd_recipes,
    "gc": _cmd_gc,
    "tree": _cmd_tree,
    "parts": _cmd_parts,
    "viewids": _cmd_viewids,
    "persp": _cmd_persp,
    "cmd": _cmd_cmd,
    "open": _cmd_open,
    "close": _cmd_close,
    "shell": _cmd_shell,
    "verify": _cmd_verify,
    "build": _cmd_build,
    "preflight": _cmd_preflight,
    "shadow": _cmd_shadow,
    "run": _cmd_run_door,
}


def _first_positional(argv: Sequence[str]) -> Optional[str]:
    for token in argv:
        if token.startswith("-"):
            continue
        return token
    return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv:
        parser.print_help(sys.stdout)
        return 0
    first = _first_positional(argv)
    if first is not None and first not in SUBCOMMANDS:
        print("ERR notfound no such subcommand: %s; retry: python -m ctl --help" % first,
              file=sys.stderr)
        return 1
    args = parser.parse_args(argv)
    try:
        # Install the shadow settings before anything can reach the bridge: the
        # hook lives in `Client.request`, i.e. it reads this module state.
        shadow.configure(shadow.resolve(getattr(args, "no_shadow", None),
                                        getattr(args, "shadow_only_changes", None),
                                        config_path=getattr(args, "config", None)))
    except Exception as exc:                      # never let observation break control
        print("WARN: shadow configuration failed (%s); the shadow layer stays off" % exc,
              file=sys.stderr)
        shadow.configure(shadow.ShadowConfig(enabled=False))
    try:
        return int(args.func(args))
    except EndpointNotFound as exc:
        print(exc.line(), file=sys.stderr)
        return 1
    except PrereqNotReady as exc:
        print(exc.line(), file=sys.stderr)
        return 2
    except CtlError as exc:
        print(exc.line(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
