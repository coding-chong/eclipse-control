"""realflow.build_artifact -- the real four-step workflow, one recipe per target.

What is verified (the user's own words): **create a project -> write a few lines
of code -> the IDE acknowledges it -> the build produces an artifact**.  Both
targets run the *same* case body and the *same* predicates; only the recipe
(launcher path, create/build command, build configuration, artifact name) is
per-target data -- that is the one difference the research report attributed and
cross-checked (`realflow-scenario-2026-10-02.md` §5, §6.2).

The four steps and what each one is judged by:

1. **create** -- GS32 copies its CDT template out of the install tree and renames
   the ``<name>`` in ``.project``; CCS writes a minimal ``.projectspec`` and runs
   ``com.ti.ccstudio.apps.projectCreate``.  Judged by: the project description
   landed and the create command exited 0 (when there is one).
2. **write code** -- a new ``src/realflow_marker_<8 hex>.c`` carrying a unique
   ``CTL-REALFLOW-<8 hex>`` string, plus a patch of the project's ``main`` source
   so the marker is *referenced* (an unreferenced section is exactly what
   ``--gc-sections`` / the C2000 linker would drop).  Judged by: the file exists
   and the marker is in it.
3. **the IDE acknowledges it** -- ``ui.open`` the file through the bridge, with a
   ``ui.parts`` read-back before and after.  Judged by the *diff*, never by the
   status line (`design.md` §4.3): ``editors`` +1, the new row's id contains
   ``CEditor`` and its ``name=`` equals the file's basename.
4. **build** -- the target's own headless entry point, in a separate JVM with its
   own scratch workspace.  Judged by: rc 0 (not killed by the timeout), the
   artifact exists and is a real ELF, ``e_machine`` is the recipe's value, **and**
   the unique marker string is found inside the artifact's bytes.  That last one
   is the anti-false-positive probe: it proves the image was built from *this*
   run's source, not left over from an earlier one.  The byte form is a per-target
   *value*: GS32's 8-bit ``char`` stores the marker as ASCII, the TI C2000
   compiler's default 16-bit ``char`` stores it as one little-endian word per
   character -- both are searched and the matched encoding is recorded.

Skip / FAIL boundary (this is load-bearing -- a silent skip hides coverage):

* **SKIP** -- the environment is not the measured one: no recipe for the target,
  the launcher binary is absent, or the template directory is absent.  These are
  checked in ``pre``, before any scratch tree exists.
* **FAIL** -- the recipe is complete but the run broke: the create command
  returned non-zero, the template's anchors no longer match (the recipe's premise
  is violated), the editor diff is not ``+1``/``CEditor``, the build returned
  non-zero or hit the timeout, or the artifact is missing / not an ELF / the
  wrong ``e_machine`` / does not contain the marker.

``screen_guard`` is off on purpose: nothing here is judged by the screen (the
``ui.open`` verdict is a read-back diff and the build verdict is rc + artifact
bytes), the action spans an external multi-second build whose windows belong to
another process, and ``ui.open`` retitling the main shell is an already-explained
bridge-side artifact (`_explain_as_title_change`).

The editor is deliberately left open afterwards: the bridge has no
"close editor" method, so there is nothing to roll back to; the scratch project
tree *is* removed in ``post`` and that fact is recorded in the evidence.
"""

from __future__ import annotations

import glob
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import uuid
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from ..runner import Case, Skip
from ._util import editor_rows, parts_counts, verdict

#: Environment prefix, mirroring ``ctl/targets.py:ENV_PREFIX``.
ENV_PREFIX = "ECLIPSE_CTL_"
_REALFLOW_ENV = ENV_PREFIX + "REALFLOW_"

#: Scratch tree name inside the run directory (never a machine-local fixed path).
_SCRATCH_DIRNAME = "realflow"

#: The unique marker: ``CTL-REALFLOW-<8 hex>``.
_MARKER_PREFIX = "CTL-REALFLOW-"

#: Placeholder inside the source fragments.  A plain token, not `str.format`: the
#: CCS fragment contains C braces (`int main(void)\n{`), which `.format` would eat.
_MARKER_TOKEN = "@MARKER_FILE@"

#: Build timeout.  Measured 2026-10-03: GS32 ~26 s cold, CCS ~10 s; the ceiling is
#: generous because a cold CDT build also compiles the vendor driver library.
_DEFAULT_BUILD_TIMEOUT = 900.0

#: How many trailing build-log lines to carry into the evidence.
_BUILD_LOG_TAIL = 25

#: Recipe keys the environment may override, so another machine can be fitted
#: without editing this file: ``ECLIPSE_CTL_REALFLOW_<KEY>``.  ``launcher`` and
#: ``template`` are install-relative paths and are resolved separately (before the
#: file-existence checks that turn "not on this machine" into a SKIP).
_SCALAR_KEYS = ("config", "artifact", "device", "machine")

# --------------------------------------------------------------------------- #
# Recipes -- per-target *data* (install-relative), never a machine-local path.
# --------------------------------------------------------------------------- #

_RECIPES: Dict[str, Dict[str, Any]] = {
    "gs32": {
        "kind": "cdt-template",
        # Install-relative; resolved against ``ctx.target.install_dir``.
        "launcher": "GS32.exe",
        "template": "packages/GS32-DSPWare/gs32_examples/gs32f035/template/gs32f035",
        # No headless *create* entry in GS32: the project is a copy of `template`.
        "create_argv": None,
        "build_argv": [
            "{launcher}", "-nosplash",
            "-application", "org.eclipse.cdt.managedbuilder.core.headlessbuild",
            "-data", "{ws}", "-import", "{proj_uri}", "-build", "{name}/{config}",
        ],
        "project": "realflow_gs32",
        "config": "Flash_ILM",
        "artifact": "{config}/{name}.elf",
        "machine": 243,                     # EM_RISCV
        "main_source": "src/main.c",
        "marker_dir": "src",
    },
    "ccs12": {
        "kind": "ti-projectspec",
        "launcher": "eclipsec.exe",
        "spec_dir": "ccs-spec",
        "base_main": "src/realflow_main.c",
        "create_argv": [
            "{launcher}", "-noSplash", "-data", "{ws}",
            "-application", "com.ti.ccstudio.apps.projectCreate",
            "-ccs.projectSpec", "{spec}",
        ],
        "build_argv": [
            "{launcher}", "-noSplash", "-data", "{ws}",
            "-application", "com.ti.ccstudio.apps.projectBuild",
            "-ccs.projects", "{name}", "-ccs.configuration", "{config}",
            "-ccs.buildType", "full",
        ],
        "project": "realflow_ccs",
        "config": "Debug",
        "artifact": "{config}/{name}.out",
        "machine": 141,                     # EM_TI_C2000
        "device": "TMS320F280049C",
        "main_source": "src/realflow_main.c",
        "marker_dir": "src",
    },
}

# --------------------------------------------------------------------------- #
# Source fragments (shared shape; the anchors differ because one main belongs to
# a vendor template and the other is one we author ourselves).
# --------------------------------------------------------------------------- #

_CDT_INC_OLD = '#include "device.h"\n#include "log.h"'
_CDT_INC_NEW = (
    '#include "device.h"\n'
    '#include "log.h"\n'
    '\n'
    '/* realflow marker: defined in src/@MARKER_FILE@, referenced here so the\n'
    ' * unique byte string survives the linker section GC and lands in the\n'
    ' * linked image. */\n'
    'extern unsigned long ctl_rf_marker_live(void);\n'
    'extern volatile const char ctl_rf_marker[];'
)
_CDT_CALL_OLD = '    __enable_irq();\n\n    oldTicks = dspTicks;'
_CDT_CALL_NEW = (
    '    __enable_irq();\n'
    '\n'
    '    if (ctl_rf_marker_live() != 0UL) {\n'
    '        log_info("realflow marker: %s\\r\\n", (const char *)ctl_rf_marker);\n'
    '    }\n'
    '\n'
    '    oldTicks = dspTicks;'
)

#: The base main the CCS projectSpec copies in; step 2 patches it in place.
_BASE_MAIN = """/*
 * eclipse-ctl realflow CCS leg -- the smallest C2000 project the build can link.
 * Written into the project by `com.ti.ccstudio.apps.projectCreate` from the
 * generated projectSpec.
 */

volatile unsigned long g_rf_in;
volatile unsigned long g_rf_out;

int main(void)
{
    while (1) {
    }
    return 0;
}
"""

_CCS_MAIN_OLD = (
    'volatile unsigned long g_rf_in;\n'
    'volatile unsigned long g_rf_out;\n'
    '\n'
    'int main(void)\n'
    '{\n'
    '    while (1) {\n'
    '    }\n'
    '    return 0;\n'
    '}'
)
_CCS_MAIN_NEW = (
    '/* realflow marker: defined in src/@MARKER_FILE@, referenced here so the\n'
    ' * unique byte string survives the linker section GC and lands in the\n'
    ' * linked image. */\n'
    'extern unsigned long ctl_rf_marker_live(void);\n'
    'extern volatile const char ctl_rf_marker[];\n'
    '\n'
    'volatile unsigned long g_rf_in;\n'
    'volatile unsigned long g_rf_out;\n'
    '\n'
    'int main(void)\n'
    '{\n'
    '    g_rf_out = ctl_rf_marker_live();\n'
    '\n'
    '    if (g_rf_out == 0UL) {\n'
    '        g_rf_in = (unsigned long)(unsigned char)ctl_rf_marker[0];\n'
    '    }\n'
    '\n'
    '    while (1) {\n'
    '    }\n'
    '    return 0;\n'
    '}'
)

_PROJECTSPEC = """<?xml version="1.0" encoding="UTF-8"?>
<projectSpec>
  <project
        name="{name}"
        device="{device}"
        outputType="executable"
        outputFormat="ELF"
        launchWizard="False"
        location="{proj}"
        >
    <configuration name="Debug"
        compilerBuildOptions="-v28 -ml -mt --float_support=fpu32 --abi=eabi --opt_level=off -g --diag_warning=225 --diag_wrap=off --display_error_number --gen_func_subsections=on --gen_data_subsections=on" />
    <configuration name="Release"
        compilerBuildOptions="-v28 -ml -mt --float_support=fpu32 --abi=eabi -O2 -g --diag_warning=225 --diag_wrap=off --display_error_number --gen_func_subsections=on --gen_data_subsections=on" />
    <file action="copy" path="src/realflow_main.c" targetDirectory="src" excludeFromBuild="False" />
  </project>
</projectSpec>
"""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def _override(key: str) -> Optional[str]:
    """``ECLIPSE_CTL_REALFLOW_<KEY>`` -- a non-empty override, or ``None``."""
    raw = os.environ.get(_REALFLOW_ENV + key.upper())
    return raw if raw else None


def _decode(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return raw.decode("utf-8", errors="replace")


def _file_uri(path: str) -> str:
    """``D:/x`` -> ``file:/D:/x``.

    CDT rejects a bare ``D:/x`` ("No file system is defined for scheme: D") and a
    space is not legal in a URI, so the path is quoted but ``/`` and ``:`` are
    kept literal (the report's measured spelling is ``file:/D:/x``).
    """
    return "file:/" + quote(path.replace("\\", "/"), safe="/:")


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _elf_header(path: str) -> Optional[Dict[str, int]]:
    """``{class, endian, machine}`` off the first 20 bytes, or ``None``.

    ``e_machine`` is read straight from the header (little-endian) instead of
    shelling out to an objdump: the two measured targets are both ELF32 LE
    (GS32 RISC-V 243 / TI C2000 141).
    """
    with open(path, "rb") as handle:
        head = handle.read(20)
    if len(head) < 20 or head[:4] != b"\x7fELF":
        return None
    return {"class": head[4], "endian": head[5],
            "machine": struct.unpack_from("<H", head, 18)[0]}


def _kill_tree(pid: int) -> str:
    """Kill a timed-out build and its children; returns a one-line note."""
    if sys.platform != "win32":
        try:
            os.kill(int(pid), 9)
            return "SIGKILL pid=%d" % pid
        except OSError as exc:
            return "os.kill(%d) failed: %r" % (pid, exc)
    try:
        done = subprocess.run(["taskkill", "/F", "/T", "/PID", str(int(pid))],
                              capture_output=True, timeout=30)
        text = (_decode(done.stdout) + _decode(done.stderr)).strip().replace("\n", " ")
        return "taskkill /F /T /PID %d rc=%d %s" % (pid, done.returncode, text[:200])
    except Exception as exc:  # noqa: BLE001 - cleanup must never raise from a timeout
        return "taskkill failed: %r" % exc


def _run_capture(argv: List[str], timeout: float, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Run a build/create command, capture merged stdout, and never orphan it.

    ``subprocess.run(timeout=...)`` kills only the launcher; the Eclipse launcher
    hands the work to a ``javaw`` child (and gmake/gcc below that), so a timeout
    kills the whole tree via ``taskkill /F /T`` before draining the pipes.
    """
    flags: Dict[str, Any] = {}
    if sys.platform == "win32":
        flags["creationflags"] = 0x08000000          # CREATE_NO_WINDOW
    started = time.monotonic()
    try:
        proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, **flags)
    except OSError as exc:
        return {"rc": None, "timed_out": False, "text": "spawn failed: %r" % exc,
                "elapsed": 0.0, "killed": None, "argv": list(argv)}
    try:
        out, _ = proc.communicate(timeout=timeout)
        return {"rc": proc.returncode, "timed_out": False, "text": _decode(out),
                "elapsed": time.monotonic() - started, "killed": None, "argv": list(argv)}
    except subprocess.TimeoutExpired:
        killed = _kill_tree(proc.pid)
        try:
            out, _ = proc.communicate(timeout=15)
        except Exception:  # noqa: BLE001
            out = b""
        return {"rc": proc.returncode, "timed_out": True, "text": _decode(out),
                "elapsed": time.monotonic() - started, "killed": killed, "argv": list(argv)}


def _tail(text: str, lines: int = _BUILD_LOG_TAIL) -> str:
    rows = [row for row in (text or "").splitlines()]
    return "\n".join(rows[-lines:])


def _marker_variants(marker: str) -> List[Tuple[str, bytes]]:
    """The marker's byte forms, because ``char`` width is a per-target fact.

    GS32 (RISC-V, ``char`` = 8 bit) stores it as plain ASCII; the TI C2000
    compiler's default is a **16-bit** ``char`` (no ``--pack``), so each character
    occupies one little-endian word and the image holds ``C\\x00T\\x00…``.  Both
    are the same unique string; searching every form keeps one predicate for both
    targets and records *which* encoding matched (measured 2026-10-03).
    """
    return (("ascii", marker.encode("ascii")),
            ("u16le", marker.encode("utf-16-le")),
            ("u16be", marker.encode("utf-16-be")))


def _find_marker(blob: bytes, marker: str) -> Tuple[int, str]:
    """``(offset, encoding)`` of the first marker form found, else ``(-1, "")``."""
    for label, needle in _marker_variants(marker):
        offset = blob.find(needle)
        if offset >= 0:
            return offset, label
    return -1, ""


def _marker_source(marker: str, main_rel: str) -> str:
    return (
        '/*\n'
        ' * eclipse-ctl realflow marker -- the unique byte string this workflow adds.\n'
        ' * Referenced from %s so it survives the linker section GC and lands\n'
        ' * verbatim in the linked image (the anti-false-positive probe).\n'
        ' */\n'
        '\n'
        'volatile const char ctl_rf_marker[] = "%s";\n'
        '\n'
        'unsigned long ctl_rf_marker_live(void)\n'
        '{\n'
        '    return (ctl_rf_marker[0] == (char)0) ? 1UL : 0UL;\n'
        '}\n'
    ) % (main_rel, marker)


def _write_text(path: str, text: str) -> None:
    """Write LF bytes verbatim -- never let the platform turn them into CRLF."""
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


# --------------------------------------------------------------------------- #
# Recipe resolution (`pre`)
# --------------------------------------------------------------------------- #

def _resolve_recipe(ctx) -> Dict[str, Any]:
    """Recipe for this target, or ``Skip`` when the environment is not ready."""
    base = _RECIPES.get(ctx.target.name)
    if base is None:
        raise Skip("no realflow recipe for target %r (known: %s)"
                   % (ctx.target.name, ", ".join(sorted(_RECIPES))))
    install_dir = ctx.target.install_dir or ""
    if not install_dir:
        raise Skip("target %r has no install_dir in the target matrix; set one with "
                   "`ctl targets add %s --source-dir <dir>`" % (ctx.target.name, ctx.target.name))

    recipe = dict(base)
    recipe["project"] = str(recipe["project"])
    # `launcher` / `template` are install-relative unless the override is absolute
    # (os.path.join keeps an absolute second argument).
    launcher = _override("launcher") or str(recipe["launcher"])
    recipe["launcher"] = os.path.join(install_dir, launcher)
    if not os.path.isfile(recipe["launcher"]):
        raise Skip("launcher not found: %s (override with %sLAUNCHER=<abs path>)"
                   % (recipe["launcher"], _REALFLOW_ENV))
    if recipe["kind"] == "cdt-template":
        template = _override("template") or str(recipe["template"])
        recipe["template"] = os.path.join(install_dir, template)
        if not os.path.isdir(recipe["template"]):
            raise Skip("template dir not found: %s (override with %sTEMPLATE=<abs path>)"
                       % (recipe["template"], _REALFLOW_ENV))
    for key in _SCALAR_KEYS:
        raw = _override(key)
        if raw is None:
            continue
        if key == "machine":
            try:
                recipe[key] = int(raw, 0)
            except ValueError:
                raise Skip("%sMACHINE=%r is not an integer" % (_REALFLOW_ENV, raw))
        else:
            recipe[key] = raw
    recipe["timeout"] = _DEFAULT_BUILD_TIMEOUT
    raw_timeout = _override("build_timeout")
    if raw_timeout is not None:
        try:
            recipe["timeout"] = float(raw_timeout)
        except ValueError:
            raise Skip("%sBUILD_TIMEOUT=%r is not a number" % (_REALFLOW_ENV, raw_timeout))
    return recipe


def _pre(ctx):
    if ctx.paths is None:
        raise Skip("no run directory to hold the scratch project; retry with "
                   "--run-id <id> (the case writes only inside <run_root>/<run_id>)")
    recipe = _resolve_recipe(ctx)
    scratch = os.path.join(ctx.paths.run_root, ctx.paths.run_id, _SCRATCH_DIRNAME)
    if os.path.isdir(scratch):
        shutil.rmtree(scratch)
    os.makedirs(scratch)
    ctx.realflow_plan = {"scratch": scratch, "recipe": recipe, "killed": []}
    ctx.note("pre: scratch=%s recipe kind=%s launcher=%s template=%s config=%s "
             "artifact=%s machine=%s"
             % (scratch, recipe.get("kind"), recipe.get("launcher"),
                recipe.get("template") or "-", recipe.get("config"),
                recipe.get("artifact"), recipe.get("machine")))
    return "scratch=%s" % scratch


# --------------------------------------------------------------------------- #
# The four steps
# --------------------------------------------------------------------------- #

def _create(ctx, recipe: Dict[str, Any], scratch: str, name: str) -> Dict[str, Any]:
    """Step 1 -- build the project (template copy, or projectSpec + projectCreate)."""
    proj = os.path.join(scratch, "proj")
    out: Dict[str, Any] = {"path": proj, "rc": None, "ok": False, "error": "",
                           "log_tail": "", "argv": []}

    if recipe["kind"] == "cdt-template":
        shutil.copytree(recipe["template"], proj)
        project_file = os.path.join(proj, ".project")
        if not os.path.isfile(project_file):
            out["error"] = "template copy has no .project"
            return out
        text = _read_text(project_file)
        # Only the *project description*'s own <name> is the project name; the
        # buildSpec's <buildCommand><name> children are builder ids and must stay.
        match = re.search(r"<projectDescription>\s*<name>([^<]*)</name>", text)
        if match is None:
            out["error"] = "template .project has no <projectDescription><name>; the " \
                           "measured template shape changed"
            return out
        renamed = text[:match.start(1)] + name + text[match.end(1):]
        if renamed == text:
            out["error"] = ".project rename did not apply (%r -> %r)" % (match.group(1), name)
            return out
        _write_text(project_file, renamed)
        # An in-process copy+rename has no external exit status; `rc` stays 0 here
        # and the honest proof is the landed project description + the rename.
        out["rc"] = 0
        out["ok"] = True
        ctx.note("create: copied CDT template -> %s; .project name %r -> %r"
                 % (proj, match.group(1), name))
        return out

    if recipe["kind"] == "ti-projectspec":
        spec_dir = os.path.join(scratch, recipe["spec_dir"])
        os.makedirs(os.path.join(spec_dir, "src"), exist_ok=True)
        _write_text(os.path.join(spec_dir, recipe["base_main"]), _BASE_MAIN)
        spec = os.path.join(spec_dir, name + ".projectspec")
        _write_text(spec, _PROJECTSPEC.format(name=name, device=recipe["device"],
                                              proj=proj.replace("\\", "/")))
        os.makedirs(proj, exist_ok=True)
        values = _values(recipe, scratch, proj, spec, name)
        argv = [part.format(**values) for part in recipe["create_argv"]]
        out["argv"] = argv
        run = _run_capture(argv, recipe["timeout"], cwd=scratch)
        out["rc"] = run["rc"]
        out["timed_out"] = run["timed_out"]
        out["log_tail"] = _tail(run["text"])
        if run["timed_out"]:
            out["error"] = "projectCreate timed out after %.0fs (%s)" % (
                run["elapsed"], run["killed"])
            return out
        landed = [entry for entry in (".project", ".cproject", ".ccsproject")
                  if os.path.isfile(os.path.join(proj, entry))]
        ctx.note("create: %s -> rc=%s elapsed=%.1fs; project files landed: %s"
                 % (" ".join(argv), run["rc"], run["elapsed"],
                    ", ".join(landed) or "<none>"))
        for line in out["log_tail"].splitlines():
            ctx.note("create| " + line)
        if run["rc"] != 0:
            out["error"] = "projectCreate rc=%s" % run["rc"]
            return out
        if ".project" not in landed or ".cproject" not in landed:
            out["error"] = "projectCreate rc=0 but the project description did not land: %s" % landed
            return out
        out["ok"] = True
        return out

    out["error"] = "unknown recipe kind: %r" % recipe["kind"]
    return out


def _write_code(ctx, recipe: Dict[str, Any], proj: str, name: str) -> Dict[str, Any]:
    """Step 2 -- the marker source, plus a patch making ``main`` reference it."""
    token = uuid.uuid4().hex[:8]
    marker = _MARKER_PREFIX + token
    marker_dir = os.path.join(proj, recipe["marker_dir"])
    marker_name = "realflow_marker_%s.c" % token
    marker_path = os.path.join(marker_dir, marker_name)
    main_rel = recipe["main_source"]
    main_path = os.path.join(proj, main_rel)
    out: Dict[str, Any] = {"ok": False, "error": "", "marker": marker,
                           "marker_path": marker_path, "marker_name": marker_name,
                           "main_path": main_path}
    if not os.path.isdir(marker_dir):
        out["error"] = "marker dir %s does not exist (create step failed?)" % marker_dir
        return out
    if not os.path.isfile(main_path):
        out["error"] = "main source %s does not exist (create step failed?)" % main_path
        return out

    _write_text(marker_path, _marker_source(marker, os.path.basename(main_rel)))
    ctx.note("write: %s = %r" % (marker_name, marker))

    text = _read_text(main_path)
    if recipe["kind"] == "cdt-template":
        if text.count(_CDT_INC_OLD) != 1:
            out["error"] = ("template %s: include anchor appears %d time(s), expected 1 "
                            "(template shape changed)" % (main_rel, text.count(_CDT_INC_OLD)))
            return out
        if text.count(_CDT_CALL_OLD) != 1:
            out["error"] = ("template %s: main() entry anchor appears %d time(s), expected 1 "
                            "(template shape changed)" % (main_rel, text.count(_CDT_CALL_OLD)))
            return out
        patched = text.replace(_CDT_INC_OLD, _CDT_INC_NEW.replace(_MARKER_TOKEN, marker_name))
        patched = patched.replace(_CDT_CALL_OLD, _CDT_CALL_NEW)
    elif recipe["kind"] == "ti-projectspec":
        if text.count(_CCS_MAIN_OLD) != 1:
            out["error"] = ("%s: main anchor appears %d time(s), expected 1"
                            % (main_rel, text.count(_CCS_MAIN_OLD)))
            return out
        patched = text.replace(_CCS_MAIN_OLD, _CCS_MAIN_NEW.replace(_MARKER_TOKEN, marker_name))
    else:
        out["error"] = "unknown recipe kind: %r" % recipe["kind"]
        return out
    _write_text(main_path, patched)
    ctx.note("write: patched %s so main() references %s (keeps the marker out of "
             "section GC)" % (main_rel, marker_name))
    out["ok"] = True
    return out


def _values(recipe: Dict[str, Any], scratch: str, proj: str, spec: str,
            name: str) -> Dict[str, str]:
    return {
        "launcher": recipe["launcher"],
        "ws": os.path.join(scratch, "ws"),
        "proj": proj.replace("\\", "/"),
        "proj_uri": _file_uri(proj),
        "spec": spec.replace("\\", "/"),
        "name": name,
        "config": recipe["config"],
    }


def _acknowledge(ctx, marker_path: str) -> Dict[str, Any]:
    """Step 3 -- ``ui.open`` + a ``ui.parts`` read-back diff."""
    before = ctx.request("ui.parts")
    opened = ctx.request("ui.open %s" % marker_path.replace("\\", "/"))
    after = ctx.request("ui.parts")
    ctx.note("ide: ui.open -> %s" % opened.status_line)
    return {"before": before, "opened": opened, "after": after}


def _build(ctx, recipe: Dict[str, Any], scratch: str, proj: str, name: str,
           plan: Dict[str, Any]) -> Dict[str, Any]:
    """Step 4 -- the target's headless build, in its own scratch workspace."""
    spec = os.path.join(scratch, recipe["spec_dir"], name + ".projectspec") \
        if recipe["kind"] == "ti-projectspec" else ""
    values = _values(recipe, scratch, proj, spec, name)
    argv = [part.format(**values) for part in recipe["build_argv"]]
    ctx.note("build: %s" % " ".join(argv))
    run = _run_capture(argv, recipe["timeout"], cwd=scratch)
    if run["killed"]:
        plan["killed"].append(run["killed"])
    ctx.note("build: rc=%s timed_out=%s elapsed=%.1fs%s"
             % (run["rc"], run["timed_out"], run["elapsed"],
                (" killed: " + run["killed"]) if run["killed"] else ""))
    for line in _tail(run["text"]).splitlines():
        ctx.note("build| " + line)
    return run


def _artifact(ctx, recipe: Dict[str, Any], proj: str, name: str) -> Dict[str, Any]:
    pattern = os.path.join(proj, recipe["artifact"].format(name=name,
                                                           config=recipe["config"]))
    hits = sorted(glob.glob(pattern))
    out: Dict[str, Any] = {"pattern": pattern, "path": hits[0] if hits else "",
                           "size": 0, "sha256": "", "elf": None,
                           "marker_offset": -1, "marker_encoding": ""}
    if not hits:
        return out
    path = hits[0]
    out["size"] = os.path.getsize(path)
    out["sha256"] = _sha256(path)
    out["elf"] = _elf_header(path)
    return out


def _action(ctx):
    plan = ctx.realflow_plan
    recipe = plan["recipe"]
    scratch = plan["scratch"]
    name = recipe["project"]
    result: Dict[str, Any] = {"errors": [], "recipe": recipe, "target": ctx.target.name,
                              "project_name": name, "scratch": scratch}

    create = _create(ctx, recipe, scratch, name)
    result["create"] = create
    if not create["ok"]:
        result["errors"].append("create: " + (create["error"] or "failed"))
        ctx.note("create: STOP -- %s" % (create["error"] or "failed"))
        return result

    write = _write_code(ctx, recipe, create["path"], name)
    result["write"] = write
    if not write["ok"]:
        result["errors"].append("write: " + (write["error"] or "failed"))
        ctx.note("write: STOP -- %s" % (write["error"] or "failed"))
        return result

    result["ack"] = _acknowledge(ctx, write["marker_path"])
    result["build"] = _build(ctx, recipe, scratch, create["path"], name, plan)
    result["artifact"] = _artifact(ctx, recipe, create["path"], name)
    result["marker"] = write["marker"]
    result["marker_name"] = write["marker_name"]

    art = result["artifact"]
    if art["path"]:
        with open(art["path"], "rb") as handle:
            blob = handle.read()
        offset, encoding = _find_marker(blob, write["marker"])
        art["marker_offset"] = offset
        art["marker_encoding"] = encoding
        elf = art["elf"] or {}
        ctx.note("artifact: %s size=%d sha256=%s class=%s endian=%s e_machine=%s"
                 % (os.path.basename(art["path"]), art["size"], art["sha256"],
                    elf.get("class"), elf.get("endian"), elf.get("machine")))
        ctx.note("artifact: marker %r found at offset %s (%s) of %d byte(s)"
                 % (write["marker"], offset if offset >= 0 else "<not found>",
                    encoding or "no encoding matched", art["size"]))
    else:
        ctx.note("artifact: no file matched %s" % art["pattern"])
    return result


# --------------------------------------------------------------------------- #
# Judgement
# --------------------------------------------------------------------------- #

def _expect(ctx, result) -> Tuple[bool, str]:
    problems: List[str] = list(result.get("errors") or [])
    recipe = result["recipe"]
    name = result["project_name"]

    create = result.get("create") or {}
    if create.get("rc") not in (0, None):
        problems.append("create rc=%s (expected 0)" % create.get("rc"))
    if create.get("timed_out"):
        problems.append("create timed out")

    write = result.get("write") or {}
    # Stop at the first broken step: reporting "ui.open was never reached" plus
    # "no artifact matched None" on top of the real cause is noise, not evidence.
    if result.get("errors") or not write.get("ok"):
        if not write.get("ok") and create.get("ok"):
            problems.append("write: " + (write.get("error") or "did not complete"))
        detail = ("target=%s project=%s create=%s write=%s"
                  % (result.get("target"), name,
                     ("ok rc=%s" % create.get("rc")) if create.get("ok") else "FAILED",
                     "ok" if write.get("ok") else "FAILED"))
        return verdict(problems, detail)

    ack = result.get("ack")
    e0 = e1 = None
    new_row = None
    if ack is None:
        problems.append("ide: ui.open was never reached")
    else:
        if not ack["opened"].ok:
            problems.append("ide: ui.open -> %r" % ack["opened"].status_line)
        counts0 = parts_counts(ack["before"].text)
        counts1 = parts_counts(ack["after"].text)
        e0, e1 = counts0["editors"], counts1["editors"]
        if e0 is None or e1 is None:
            problems.append("ide: ui.parts did not report editors= (%r/%r)" % (counts0, counts1))
        elif e1 != e0 + 1:
            problems.append("ide: ui.open did not add exactly one editor: editors %d -> %d"
                            % (e0, e1))
        rows0 = Counter(editor_rows(ack["before"].text))
        added = list((Counter(editor_rows(ack["after"].text)) - rows0).elements())
        if not added:
            problems.append("ide: no new editor row after ui.open")
        else:
            new_row = added[0]
            if "CEditor" not in new_row[0]:
                problems.append("ide: the new editor is %r, not a CEditor" % (new_row[0],))
            if new_row[1] != write.get("marker_name"):
                problems.append("ide: the new editor name is %r, expected %r"
                                % (new_row[1], write.get("marker_name")))

    build = result.get("build")
    if build is None:
        problems.append("build: never reached")
    else:
        if build["timed_out"]:
            problems.append("build: killed by the %.0fs timeout (%s)"
                            % (recipe["timeout"], build["killed"]))
        elif build["rc"] != 0:
            problems.append("build rc=%s (expected 0)" % build["rc"])

    art = result.get("artifact") or {}
    elf = art.get("elf")
    if not art.get("path"):
        problems.append("artifact: no file matched %s" % art.get("pattern"))
    else:
        if art["size"] <= 0:
            problems.append("artifact: %s is empty" % art["path"])
        if elf is None:
            problems.append("artifact: %s is not an ELF" % art["path"])
        else:
            if elf["machine"] != recipe["machine"]:
                problems.append("artifact: e_machine=%d, expected %d"
                                % (elf["machine"], recipe["machine"]))
    if art.get("path") and art.get("marker_offset", -1) < 0:
        problems.append("artifact: the unique marker %r is NOT in the image in any "
                        "encoding (ascii / u16le / u16be) -- stale artifact, or the "
                        "marker was optimized out" % result.get("marker"))

    detail = ("target=%s project=%s create=%s editors=%s->%s new_editor=%r build_rc=%s "
              "artifact=%s size=%s e_machine=%s(exp %s) marker_in_image=%s"
              % (result.get("target"), name,
                 ("ok rc=%s" % create.get("rc")) if create.get("ok") else "FAILED",
                 e0, e1, new_row[0] if new_row else None,
                 build["rc"] if build else None,
                 os.path.basename(art["path"]) if art.get("path") else "<missing>",
                 art.get("size"), (elf or {}).get("machine"), recipe["machine"],
                 ("%s@%s" % (art.get("marker_encoding") or "?", art.get("marker_offset")))
                 if art.get("marker_offset", -1) >= 0 else False))
    return verdict(problems, detail)


def _post(ctx):
    plan = getattr(ctx, "realflow_plan", None)
    if not plan:
        return "no scratch tree was created"
    scratch = plan["scratch"]
    shutil.rmtree(scratch, ignore_errors=True)
    gone = not os.path.isdir(scratch)
    ctx.note("post: scratch project tree removed=%s (%s)" % (gone, scratch))
    if plan.get("killed"):
        ctx.note("post: timed-out build process trees killed: %s" % "; ".join(plan["killed"]))
    ctx.note("post: no close-editor method exists on the bridge, so the editor opened "
             "by this case is left open on purpose (nothing to roll back to)")
    return "scratch removed=%s" % gone


CASE = Case(
    name="realflow.build_artifact",
    group="realflow",
    targets=("gs32", "ccs12"),
    description=("the real four-step workflow (create project -> write code -> the IDE "
                 "opens it -> the build emits an ELF); per-target recipe, same predicates"),
    pre=_pre,
    action=_action,
    expect=_expect,
    post=_post,
    screen_guard=False,
    evidence=("raw:action", "build:log", "artifact:probe"),
)
