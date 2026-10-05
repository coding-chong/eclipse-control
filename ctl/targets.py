"""Per-IDE target facts and the layered configuration.

The matrix mirrors `design.md` §9 ("跨产品编译") and the measured values in
`research/facts-baseline.md` §1.  Configuration precedence is fixed by
`design-obs-ux.md` §14.2::

    CLI flag  >  environment ECLIPSE_CTL_*  >  config file  >  built-in default

Only the standard library is used.
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from .errors import CtlError, NotFoundError

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

ENV_PREFIX = "ECLIPSE_CTL_"
DEFAULT_TARGET = "gs32"
DEFAULT_KEEP_RUNS = 3

STATE_DIR = os.path.join(os.path.expanduser("~"), ".eclipse-ctl")
CONFIG_PATH = os.path.join(STATE_DIR, "config.json")

#: Built-in default run root.  Deliberately under the per-user state dir:
#: the design only ever writes `<run_root>` and `~/.eclipse-ctl/`
#: (`design-project.md` §16.5), and no path is hardcoded to a machine-local
#: scratch directory.
DEFAULT_RUN_ROOT = os.path.join(STATE_DIR, "runs")

_SCALAR_KEYS = (
    "default_target",
    "run_root",
    "keep_runs",
    "copy",
    "allow_dangerous",
    "auto_gc",
)

#: `design-obs-ux.md` §14.6 uses `source_dir` / `java_level` for the same two
#: fields the target model calls `install_dir` / `java_target`.
_ALIASES = {
    "source_dir": "install_dir",
    "source": "install_dir",
    "java_level": "java_target",
    "java": "java_target",
    "eclipse": "eclipse_version",
    "port": "port",
}


# --------------------------------------------------------------------------- #
# Target
# --------------------------------------------------------------------------- #

@dataclass
class Target:
    """One IDE installation plus the facts needed to build/run against it."""

    name: str
    install_dir: str
    eclipse_version: str
    jre: str
    java_target: str
    product: str
    default_port: int
    port: int
    launcher: str = ""
    vendor_prefix: str = ""
    jre_home: str = ""
    ecj: str = ""
    #: The vendor view the write cases open/close.  This is per-target **data**,
    #: not a case constant: the two products name their views differently
    #: (`com.gs.memory.view` vs `com.ti.ccstudio.project.ui.views.MemoryAllocationView`).
    #: R5' requires the *same* case with the *same* judgement on both targets;
    #: only this value may differ.  Empty -> the case SKIPs (never guesses).
    probe_view: str = ""

    # -- construction ------------------------------------------------------ #

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any], base: Optional["Target"] = None) -> "Target":
        """Build from a config-file dict, applying documented aliases."""
        merged: Dict[str, Any] = {}
        src = dict(data or {})
        for key, value in src.items():
            merged[_ALIASES.get(key, key)] = value
        if base is None:
            # Built-in entry: every canonical field is expected (port falls
            # back to default_port when only one of the two is given).
            base = cls(
                name=name,
                install_dir="",
                eclipse_version="",
                jre="",
                java_target="",
                product="",
                default_port=int(merged.get("default_port", merged.get("port", 8777))),
                port=int(merged.get("port", merged.get("default_port", 8777))),
            )
        values: Dict[str, Any] = {}
        for f in ("install_dir", "eclipse_version", "jre", "java_target", "product",
                  "launcher", "vendor_prefix", "jre_home", "ecj", "probe_view"):
            if f in merged:
                values[f] = str(merged[f])
        if "default_port" in merged:
            values["default_port"] = int(merged["default_port"])
        if "port" in merged:
            values["port"] = int(merged["port"])
        return replace(base, **values) if values else base

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "install_dir": self.install_dir,
            "eclipse_version": self.eclipse_version,
            "jre": self.jre,
            "java_target": self.java_target,
            "product": self.product,
            "default_port": self.default_port,
            "port": self.port,
            "launcher": self.launcher,
            "vendor_prefix": self.vendor_prefix,
            "jre_home": self.jre_home,
            "ecj": self.ecj,
        }

    # -- derived facts ----------------------------------------------------- #

    @property
    def plugins_dir(self) -> str:
        return os.path.join(self.install_dir, "plugins")

    def launcher_path(self) -> str:
        return os.path.join(self.install_dir, self.launcher) if self.launcher else ""

    def java_exe(self) -> Optional[str]:
        """Locate a JVM to run ECJ with (target-tree JRE preferred)."""
        if self.jre_home:
            exe = os.path.join(self.jre_home, "bin", "java.exe")
            if os.path.isfile(exe):
                return exe
        found = _find_justj_java(self.install_dir, self.jre)
        if found:
            return found
        bundled = os.path.join(self.install_dir, "jre", "bin", "java.exe")
        if os.path.isfile(bundled):
            return bundled
        return None

    def ecj_jar(self) -> Optional[str]:
        """Locate the ECJ batch compiler inside the target tree, if any."""
        if self.ecj and os.path.isfile(self.ecj):
            return self.ecj
        return _find_ecj(self.install_dir)

    def product_file(self) -> str:
        return os.path.join(self.install_dir, ".eclipseproduct")


# --------------------------------------------------------------------------- #
# Discovery helpers
# --------------------------------------------------------------------------- #

#: ECJ inside the target's own tree -- Eclipse ships JDT, so this is the normal case.
ECJ_TREE_GLOBS = ("plugins/org.eclipse.jdt.core.compiler.batch_*.jar",)

#: Two levels up from the IDE tree.  CCS ships **no JDT**, but its XDCtools component
#: (a declared part of the product: `ccs/install_info/com.ti.xdctools.update.properties`
#: -> `Installdir=../../xdctools_3_62_01_16_core`) carries a batch compiler.  `install_dir`
#: is the IDE tree `<ccs_root>/ccs/eclipse`, so `<ccs_root>` is `../..`.
#: Measured 2026-10-06: that compiler is ECJ 3.14.0, which caps out at `-source/-target 9`.
ECJ_ANCESTOR_GLOBS = ("../../xdctools_*/packages/xdc/shelf/java/ecj.jar",)


def _find_justj_java(install_dir: str, jre_version: str = "") -> Optional[str]:
    plugins = os.path.join(install_dir, "plugins")
    patterns = []
    if jre_version:
        patterns.append("org.eclipse.justj.openjdk.hotspot.jre.*%s*" % jre_version)
    patterns.append("org.eclipse.justj.openjdk.hotspot.jre.*win32.x86_64_*")
    for pattern in patterns:
        for d in sorted(glob.glob(os.path.join(plugins, pattern))):
            exe = os.path.join(d, "jre", "bin", "java.exe")
            if os.path.isfile(exe):
                return exe
    return None


def _find_ecj(install_dir: str) -> Optional[str]:
    """Locate the ECJ batch compiler for an IDE tree.

    Two search surfaces, in order (both are the *same* product's install, never a
    sibling product's):

    1. ``ECJ_TREE_GLOBS`` -- inside the tree itself (Eclipse ships JDT).
    2. ``ECJ_ANCESTOR_GLOBS`` -- two levels up.  CCS ships **no JDT**, but its
       XDCtools component carries a batch compiler at
       ``<ccs_root>/xdctools_*/packages/xdc/shelf/java/ecj.jar``, and
       ``install_dir`` is the IDE tree (``<ccs_root>/ccs/eclipse``).

    Returns ``None`` when neither surface has one.  Callers must treat that as
    "this tree cannot build the bridge", never as "borrow one from somewhere
    else": the old code fell back to a **hard-coded sibling install path**, which
    made a CCS-only machine fail with a message about a GS32 tree it never had.
    """
    for pattern in ECJ_TREE_GLOBS:
        hits = sorted(glob.glob(os.path.join(install_dir, pattern)))
        if hits:
            return os.path.normpath(hits[-1])
    for pattern in ECJ_ANCESTOR_GLOBS:
        hits = sorted(glob.glob(os.path.join(install_dir, pattern)))
        if hits:
            # `normpath` matters here and only here: the ancestor pattern is relative
            # (`../../xdctools_*`), so the raw match carries `../..` inside it.  Every
            # caller compares this string against other paths (doctor prints it, tests
            # assert on it), and `a/../..\b` != `b`.
            return os.path.normpath(hits[-1])
    return None


# --------------------------------------------------------------------------- #
# Built-in matrix (measured values, facts-baseline.md §1)
# --------------------------------------------------------------------------- #

_BUILTIN: Dict[str, Dict[str, Any]] = {
    "gs32": {
        "install_dir": "D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2",
        "eclipse_version": "4.30.0",
        "jre": "23.0.2",
        "java_target": "17",
        "product": "com.gs.ui.Studio",
        "default_port": 8777,
        "port": 8777,
        "launcher": "GS32.exe",
        "vendor_prefix": "com.gs",
        # Measured 2026-10-01 (facts-baseline §5): one of the 5 registered `com.gs.*` views.
        "probe_view": "com.gs.memory.view",
    },
    "ccs12": {
        "install_dir": "D:/ti/ccs1281/ccs/eclipse",
        "eclipse_version": "4.23.0",
        "jre": "11.0.13",
        # 8, not 11.  This tree ships **no JDT**, so the only compiler it has is its
        # own XDCtools component's (`ECJ_ANCESTOR_GLOBS`), and that one is ECJ 3.14 --
        # measured 2026-10-06: `-source/-target` caps at 9, `-source 11` exits 255.
        # 8 is the widest level every candidate compiler can emit, and the bridge
        # source uses no Java 9+ API (constant-pool scan), so nothing is lost.
        # Deliberately NOT derived from the discovered compiler: the level must be a
        # property of the *target*, or the same target would emit different bytecode
        # on different machines and `doctor`'s exact-level check would stop meaning
        # anything (`lifecycle.py:421-426`).  Override per-run with `--ecj <jar>`.
        "java_target": "8",
        "product": "org.eclipse.platform.ide",
        "default_port": 8778,
        "port": 8778,
        "launcher": "ccstudio.exe",
        "vendor_prefix": "com.ti",
        # No `ecj` key: the compiler is discovered inside this product's own install
        # (see `_find_ecj`).  It used to be a hard-coded path into the **gs32** tree,
        # which made a CCS-only machine die with a message about an install it never had.
        # Measured 2026-10-02 on a live instance: `com.ti` registers 33 views
        # (`ui.viewids com.ti`), and this one opens and reads back
        # (`cmd.runp showView viewId=…` -> OK, then present in `ui.parts`).
        # `.memory.view` (the gs32 suffix) does NOT exist under `com.ti` -- that
        # is exactly why the old suffix-concatenation could not cross targets.
        "probe_view": "com.ti.ccstudio.project.ui.views.MemoryAllocationView",
    },
}


def builtin_targets() -> Dict[str, Target]:
    return {name: Target.from_dict(name, data) for name, data in _BUILTIN.items()}


def reference_install_dir(name: str) -> Optional[str]:
    """The built-in ``install_dir`` shipped for ``name``, or ``None``.

    The built-ins carry the *reference machine's* paths, so a fresh clone on any
    other machine inherits an install tree that is not there.  Compare a
    target's effective ``install_dir`` against this to tell "you never set this
    target up" apart from "your own value is wrong", and word the diagnosis
    accordingly.
    """
    entry = _BUILTIN.get(name)
    return entry.get("install_dir") if entry else None


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

@dataclass
class Config:
    """Merged, effective configuration (all four precedence layers applied)."""

    default_target: str = DEFAULT_TARGET
    run_root: str = DEFAULT_RUN_ROOT
    keep_runs: int = DEFAULT_KEEP_RUNS
    copy: bool = False
    allow_dangerous: bool = False
    #: Cross-run collection on close-out: keep `keep_runs` newest runs **per
    #: target**.  On by default (`design.md` §3.7); the switch exists because
    #: "delete by default with no way out" is the shape of the 2026-10-01 wipe.
    auto_gc: bool = True
    port: Optional[int] = None
    targets: Dict[str, Target] = field(default_factory=builtin_targets)
    user_targets: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    removed_targets: List[str] = field(default_factory=list)
    config_path: str = CONFIG_PATH
    provenance: Dict[str, str] = field(default_factory=dict)

    def target(self, name: Optional[str] = None) -> Target:
        key = name or self.default_target
        if key not in self.targets:
            raise NotFoundError("no such target: %s; retry: python -m ctl targets list" % key)
        target = self.targets[key]
        if self.port is not None:
            target = replace(target, port=int(self.port))
        return target

    def target_names(self) -> List[str]:
        return sorted(self.targets)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _apply_env(config: Dict[str, Any], provenance: Dict[str, str]) -> None:
    env = os.environ
    mapping = {
        "default_target": "DEFAULT_TARGET",
        "run_root": "RUN_ROOT",
        "keep_runs": "KEEP_RUNS",
        "copy": "COPY",
        "allow_dangerous": "ALLOW_DANGEROUS",
        "auto_gc": "AUTO_GC",
        "port": "PORT",
    }
    for key, suffix in mapping.items():
        raw = env.get(ENV_PREFIX + suffix)
        if raw is None or raw == "":
            continue
        if key in ("keep_runs", "port"):
            try:
                config[key] = int(raw)
            except ValueError:
                raise CtlError("badrequest", "%s%s must be an integer, got %r"
                               % (ENV_PREFIX, suffix, raw))
        elif key in ("copy", "allow_dangerous", "auto_gc"):
            config[key] = _as_bool(raw)
        else:
            config[key] = raw
        provenance[key] = "env"


def load(flags: Optional[Dict[str, Any]] = None) -> Config:
    """Merge the four layers and return the effective :class:`Config`.

    ``flags`` accepts ``config`` (config-file path), the six scalar keys, and
    ``port``.  Unknown keys are ignored so callers can pass a whole argparse
    namespace.
    """
    flags = {k: v for k, v in (flags or {}).items() if v is not None}
    provenance: Dict[str, str] = {}

    effective: Dict[str, Any] = {
        "default_target": DEFAULT_TARGET,
        "run_root": DEFAULT_RUN_ROOT,
        "keep_runs": DEFAULT_KEEP_RUNS,
        "copy": False,
        "allow_dangerous": False,
        "auto_gc": True,
        "port": None,
    }
    for key in effective:
        provenance[key] = "default"

    # -- layer 3: config file --------------------------------------------- #
    path = flags.get("config") or os.environ.get(ENV_PREFIX + "CONFIG") or CONFIG_PATH
    file_data: Dict[str, Any] = {}
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                file_data = json.load(fh) or {}
        except (OSError, ValueError) as exc:
            raise CtlError("badrequest",
                           "config file unreadable: %s (%s); retry: python -m ctl doctor" % (path, exc))
        if not isinstance(file_data, dict):
            raise CtlError("badrequest", "config file must contain a JSON object: %s" % path)

    for key in ("default_target", "run_root", "keep_runs", "copy",
                "allow_dangerous", "auto_gc", "port"):
        if key in file_data and file_data[key] is not None:
            effective[key] = file_data[key]
            provenance[key] = "file"

    config_file_targets = file_data.get("targets") or {}
    if not isinstance(config_file_targets, dict):
        raise CtlError("badrequest", "config 'targets' must be an object: %s" % path)
    removed = list(file_data.get("removed_targets") or [])

    # -- layer 2: environment --------------------------------------------- #
    _apply_env(effective, provenance)

    # -- layer 1: CLI flags ------------------------------------------------ #
    for key in ("default_target", "run_root", "keep_runs", "copy",
                "allow_dangerous", "port"):
        if key in flags:
            effective[key] = flags[key]
            provenance[key] = "flag"

    effective["port"] = int(effective["port"]) if effective["port"] is not None else None
    effective["keep_runs"] = int(effective["keep_runs"])
    effective["copy"] = _as_bool(effective["copy"])
    effective["allow_dangerous"] = _as_bool(effective["allow_dangerous"])
    effective["auto_gc"] = _as_bool(effective["auto_gc"])

    # -- targets: built-ins <- file overrides; removed list drops them ------ #
    targets = builtin_targets()
    for name in removed:
        targets.pop(name, None)
    for name, data in config_file_targets.items():
        targets[name] = Target.from_dict(name, data, base=targets.get(name))

    return Config(
        default_target=effective["default_target"],
        run_root=effective["run_root"],
        keep_runs=effective["keep_runs"],
        copy=effective["copy"],
        allow_dangerous=effective["allow_dangerous"],
        auto_gc=effective["auto_gc"],
        port=effective["port"],
        targets=targets,
        user_targets=dict(config_file_targets),
        removed_targets=removed,
        config_path=path,
        provenance=provenance,
    )


def _read_raw(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (OSError, ValueError) as exc:
        raise CtlError("badrequest", "config file unreadable: %s (%s)" % (path, exc))
    if not isinstance(data, dict):
        raise CtlError("badrequest", "config file must contain a JSON object: %s" % path)
    return data


def save(config: Config, path: Optional[str] = None) -> str:
    """Write the *user-scope* config (never the merged built-ins) to disk."""
    path = path or config.config_path or CONFIG_PATH
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    data: Dict[str, Any] = {
        "default_target": config.default_target,
        "run_root": config.run_root,
        "keep_runs": config.keep_runs,
        "copy": config.copy,
        "allow_dangerous": config.allow_dangerous,
        "auto_gc": config.auto_gc,
        "targets": config.user_targets,
    }
    if config.removed_targets:
        data["removed_targets"] = config.removed_targets
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def add_target(name: str, fields: Dict[str, Any], config_path: Optional[str] = None) -> str:
    """Persist a user-defined target (or override) into the config file."""
    if not name or not name.strip():
        raise CtlError("badrequest", "target name must not be empty")
    name = name.strip()
    path = config_path or CONFIG_PATH
    raw = _read_raw(path)
    targets = dict(raw.get("targets") or {})
    entry = dict(targets.get(name) or {})
    for key, value in fields.items():
        if value is not None:
            entry[key] = value
    if not (entry.get("install_dir") or entry.get("source_dir")):
        raise CtlError("badrequest", "target %r needs --source-dir <dir>" % name)
    targets[name] = entry
    raw["targets"] = targets
    if name in (raw.get("removed_targets") or []):
        raw["removed_targets"] = [n for n in raw["removed_targets"] if n != name]
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def remove_target(name: str, config_path: Optional[str] = None) -> str:
    """Drop a target: from user overrides, and (for built-ins) mark it removed."""
    if not name or not name.strip():
        raise CtlError("badrequest", "target name must not be empty")
    name = name.strip()
    builtins = _BUILTIN
    path = config_path or CONFIG_PATH
    raw = _read_raw(path)
    targets = dict(raw.get("targets") or {})
    existed = name in targets or name in builtins
    targets.pop(name, None)
    raw["targets"] = targets
    if name in builtins:
        removed = list(raw.get("removed_targets") or [])
        if name not in removed:
            removed.append(name)
        raw["removed_targets"] = removed
    if not existed:
        raise NotFoundError("no such target: %s; retry: python -m ctl targets list" % name)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


def list_targets(config: Optional[Config] = None) -> List[Target]:
    """All known targets, name-sorted."""
    cfg = config or load()
    return [cfg.targets[name] for name in sorted(cfg.targets)]
