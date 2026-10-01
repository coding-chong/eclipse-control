#!/usr/bin/env python3
"""Build the eclipse-ctl bridge bundle (OSGi) without a JDK.

This machine has no ``javac`` and no ``jar.exe``.  Both are borrowed from the target
IDE install tree, which is read-only and is never written to by this script:

* ECJ batch compiler  -> ``<src>/plugins/org.eclipse.jdt.core.compiler.batch_*.jar``
* JVM that runs ECJ   -> a JRE shipped inside the same tree
* packaging           -> Python ``zipfile`` writes ``META-INF/MANIFEST.MF`` + ``*.class``

Usage::

    python bridge/build.py --target gs32
    python bridge/build.py --target ccs12 --src <install tree> --ecj <ecj.jar> --jre <java.exe>
    python bridge/build.py --out <path/to/bundle.jar>

Exit code is 0 only when the jar was written; any compile failure exits 1 and leaves no
jar behind (a stale jar must never be mistaken for a fresh one).
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import zipfile

BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BRIDGE_DIR)

DEFAULT_VERSION = "3.1.0"
DEFAULT_JAVA_SRC = os.path.join(BRIDGE_DIR, "src", "ctl", "bridge", "LiveBridge.java")

# Frozen bridge identity (design-project.md §15.1): the OSGi symbolic name may contain '-',
# the Java package may not.
BUNDLE_SYMBOLIC_NAME = "eclipse-ctl.bridge"
BUNDLE_ACTIVATOR = "ctl.bridge.LiveBridge"
BUNDLE_NAME = "eclipse-ctl bridge"

# Bundles the bridge either imports directly or loads at run time.  All of them ship with
# stock Eclipse, so nothing has to be fetched from the network.
REQUIRE_BUNDLE = ",".join([
    "org.eclipse.ui",
    "org.eclipse.ui.workbench",
    "org.eclipse.ui.ide",
    "org.eclipse.ui.console",
    "org.eclipse.swt",
    "org.eclipse.jface",
    "org.eclipse.text",
    "org.eclipse.core.commands",
    "org.eclipse.core.runtime",
    "org.eclipse.core.jobs",
    "org.eclipse.core.resources",
    "org.eclipse.core.filesystem",
    "org.eclipse.equinox.common",
    "org.eclipse.equinox.registry",
    "org.eclipse.e4.core.contexts",
    "org.eclipse.e4.ui.workbench",
    "org.eclipse.e4.ui.model.workbench",
])

# Compile-time classpath.  Each entry is a jar-name prefix under <src>/plugins; the first
# (sorted) match of every prefix is used.  A missing prefix is a hard error, because a
# silently shorter classpath turns into "cannot resolve type" noise instead of a diagnosis.
#   org.eclipse.swt.win32.*  -- SWT classes live in the platform fragment, the host jar
#                               (org.eclipse.swt) carries only ten entries.
#   org.eclipse.text         -- org.eclipse.jface.text.IDocument (console text).
REQUIRED_PLUGIN_PREFIXES = [
    "org.eclipse.swt.win32.win32.x86_64_",
    "org.eclipse.swt_",
    "org.eclipse.jface_",
    "org.eclipse.ui.workbench_",
    "org.eclipse.ui.console_",
    "org.eclipse.ui.ide_",
    "org.eclipse.ui_",
    "org.eclipse.core.commands_",
    "org.eclipse.core.runtime_",
    "org.eclipse.core.jobs_",
    "org.eclipse.core.resources_",
    "org.eclipse.core.filesystem_",
    "org.eclipse.equinox.common_",
    "org.eclipse.equinox.registry_",
    "org.eclipse.e4.core.contexts_",
    "org.eclipse.e4.ui.workbench_",
    "org.eclipse.e4.ui.model.workbench_",
    "org.eclipse.text_",
    "org.eclipse.osgi_",
]

ECJ_GLOBS = ["plugins/org.eclipse.jdt.core.compiler.batch_*.jar"]

# Install roots recorded in research/facts-baseline.md §1.
TARGETS = {
    "gs32": {
        "src": "D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2",
        "java_level": "17",
        "ecj_globs": ECJ_GLOBS,
        "jre_globs": [
            "plugins/org.eclipse.justj.openjdk.hotspot.jre*/jre/bin/java.exe",
            "jre/bin/java.exe",
        ],
    },
    "ccs12": {
        "src": "D:/ti/ccs1281/ccs/eclipse",
        "java_level": "11",
        # CCS ships no JDT, so the in-tree glob finds nothing; the second entry
        # borrows the sibling gs32 tree's ECJ (3.36 emits `-source/-target 11`).
        # Override with --ecj <jar>.
        "ecj_globs": ECJ_GLOBS + [
            "D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2/plugins/"
            "org.eclipse.jdt.core.compiler.batch_*.jar",
        ],
        "jre_globs": [
            "jre/bin/java.exe",
            "plugins/org.eclipse.justj.openjdk.hotspot.jre*/jre/bin/java.exe",
        ],
    },
}


def die(msg: str) -> "None":
    print("build: ERROR: %s" % msg, file=sys.stderr)
    sys.exit(1)


def find_first(src: str, patterns) -> str:
    for pattern in patterns:
        hits = sorted(glob.glob(os.path.join(src, pattern)))
        if hits:
            return hits[0]
    return None


def class_file_level(jar: str) -> "int | None":
    """Class-file *major* version of the first class in ``jar`` (55 = Java 11, 61 = Java 17)."""
    try:
        with zipfile.ZipFile(jar) as z:
            for entry in z.namelist():
                if not entry.endswith(".class"):
                    continue
                head = z.read(entry)[:8]
                if head[:4] == b"\xca\xfe\xba\xbe":
                    return int.from_bytes(head[6:8], "big")
    except (zipfile.BadZipFile, OSError):
        return None
    return None


def jre_feature_level(java_exe: str) -> "int | None":
    """Java feature level of a JRE (8, 11, 17, 23...) from its ``release`` file."""
    home = os.path.dirname(os.path.dirname(os.path.abspath(java_exe)))
    try:
        with open(os.path.join(home, "release"), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("JAVA_VERSION="):
                    raw = line.split("=", 1)[1].strip().strip('"')
                    parts = raw.split(".")
                    if parts[0] == "1" and len(parts) > 1:   # 1.8.0_202 -> 8
                        return int(parts[1])
                    return int(parts[0])                     # 11.0.13 -> 11
    except (OSError, ValueError):
        return None
    return None


def can_run(java_exe: str, jar: str) -> bool:
    """True when ``java_exe`` is new enough to load ``jar``'s classes.

    Unknown level on either side returns True: this only rules out a case we can
    *prove* is impossible, it never second-guesses the caller.
    """
    need, have = class_file_level(jar), jre_feature_level(java_exe)
    if need is None or have is None:
        return True
    return have + 44 >= need


def classpath_jars(plugins_dir: str) -> list:
    jars = []
    for prefix in REQUIRED_PLUGIN_PREFIXES:
        hits = sorted(glob.glob(os.path.join(plugins_dir, prefix + "*.jar")))
        if not hits:
            die("no bundle jar matching '%s*.jar' under %s -- wrong --src for this target?"
                % (prefix, plugins_dir))
        jars.append(hits[0])
    return jars


def manifest(version: str, java_level: str) -> bytes:
    lines = [
        "Manifest-Version: 1.0",
        "Bundle-ManifestVersion: 2",
        "Bundle-SymbolicName: %s" % BUNDLE_SYMBOLIC_NAME,
        "Bundle-Version: %s" % version,
        "Bundle-Name: %s" % BUNDLE_NAME,
        "Bundle-Activator: %s" % BUNDLE_ACTIVATOR,
        "Require-Bundle: %s" % REQUIRE_BUNDLE,
        "Import-Package: org.osgi.framework",
        "Bundle-RequiredExecutionEnvironment: JavaSE-%s" % java_level,
    ]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="build.py",
        description="Build the eclipse-ctl bridge bundle using the ECJ compiler and JRE "
                    "found inside a target IDE install tree.")
    parser.add_argument("--target", choices=sorted(TARGETS), default="gs32",
                        help="target product whose toolchain is borrowed (default: gs32)")
    parser.add_argument("--src", help="IDE install tree (overrides the target default)")
    parser.add_argument("--out", help="output jar path (default: bridge/dist/"
                                      "eclipse-ctl.bridge_<version>_<target>.jar)")
    parser.add_argument("--java", dest="java_src", default=DEFAULT_JAVA_SRC,
                        help="bridge source file (default: bridge/src/ctl/bridge/LiveBridge.java)")
    parser.add_argument("--jre", help="java.exe that runs ECJ (default: discovered in --src)")
    parser.add_argument("--ecj", help="ECJ batch compiler jar (default: discovered in --src)")
    parser.add_argument("--version", default=DEFAULT_VERSION,
                        help="Bundle-Version written into the manifest (default: %s)" % DEFAULT_VERSION)
    args = parser.parse_args(argv)

    target = TARGETS[args.target]
    java_level = target["java_level"]

    src = os.path.abspath(args.src) if args.src else target["src"]
    if not os.path.isdir(src):
        die("install tree not found: %s%s"
            % (src, "" if args.src else " (default for target '%s'; pass --src)" % args.target))
    if not os.path.isdir(os.path.join(src, "plugins")):
        die("%s does not look like an Eclipse product (no plugins/ directory)" % src)

    java_src = os.path.abspath(args.java_src)
    if not os.path.isfile(java_src):
        die("source file not found: %s" % java_src)

    # The file name carries the target: the same source compiles to Java 17 for
    # gs32 and Java 11 for ccs12, and those two artifacts must **coexist** in
    # bridge/dist/ (a shared name meant building one target silently replaced
    # the other's jar, and `find_bridge_jar()` then picked an unloadable one).
    jar_out = os.path.abspath(args.out) if args.out else os.path.join(
        BRIDGE_DIR, "dist", "%s_%s_%s.jar" % (BUNDLE_SYMBOLIC_NAME, args.version, args.target))
    out_dir = os.path.join(BRIDGE_DIR, "build", args.target, "out")

    ecj = os.path.abspath(args.ecj) if args.ecj else find_first(src, target["ecj_globs"])
    if not ecj or not os.path.isfile(ecj):
        die("no ECJ batch compiler found for target '%s' under %s (tried: %s); this install "
            "tree ships no JDT -- pass --src <tree that has one> or --ecj <ecj.jar>"
            % (args.target, src, ", ".join(target["ecj_globs"])))

    # The JVM that *runs ECJ* and the bytecode level we *emit* are two separate
    # requirements.  A borrowed ECJ may itself need a newer JRE than this target
    # ships: gs32's ECJ 3.36 is class-file 61 (Java 17) while ccs12's JRE is 11,
    # which cannot even load it (`UnsupportedClassVersionError`, hit 2026-10-01).
    jre = os.path.abspath(args.jre) if args.jre else find_first(src, target["jre_globs"])
    if jre and not os.path.isfile(jre):
        jre = None
    if not jre:
        die("no java.exe found for target '%s' under %s (tried: %s); pass --jre <java.exe>"
            % (args.target, src, ", ".join(target["jre_globs"])))
    if not can_run(jre, ecj):
        able = []
        for other in TARGETS.values():
            cand = find_first(other["src"], other["jre_globs"])
            if cand and os.path.isfile(cand) and can_run(cand, ecj):
                able.append((jre_feature_level(cand) or 0, cand))
        if not able:
            die("the JRE at %s (Java %s) cannot load the ECJ compiler %s (class-file %s); "
                "pass --jre <java.exe> and/or --ecj <ecj.jar>"
                % (jre, jre_feature_level(jre), os.path.basename(ecj), class_file_level(ecj)))
        jre = max(able)[1]
        print("  jre         : %s (the target's own JRE cannot run this ECJ)" % jre)

    cp = classpath_jars(os.path.join(src, "plugins"))

    # No stale class files and no stale jar: a failed build must not leave anything behind
    # that could be mistaken for a fresh artifact.
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.dirname(jar_out), exist_ok=True)
    if os.path.exists(jar_out):
        os.remove(jar_out)

    cmd = [jre, "-jar", ecj, "-source", java_level, "-target", java_level,
           "-encoding", "UTF-8", "-nowarn", "-proc:none",
           "-cp", ";".join(cp), "-d", out_dir, java_src]

    print("target      : %s (java level %s)" % (args.target, java_level))
    print("src tree    : %s" % src)
    print("jre         : %s" % jre)
    print("ecj         : %s" % ecj)
    print("source      : %s" % java_src)
    print("classpath   : %d jars" % len(cp))
    for j in cp:
        print("              %s" % os.path.basename(j))
    print("command     :")
    print("  \"%s\" -jar \"%s\" -source %s -target %s -encoding UTF-8 -nowarn -proc:none -cp <%d jars> -d \"%s\" \"%s\""
          % (jre, ecj, java_level, java_level, len(cp), out_dir, java_src))
    print()

    proc = subprocess.run(cmd, capture_output=True)
    diag = (proc.stdout or b"").decode("utf-8", "replace") + \
           (proc.stderr or b"").decode("utf-8", "replace")
    print("ecj rc=%s" % proc.returncode)
    if diag.strip():
        print("--- compiler diagnostics (truncated to 2500 chars) ---")
        print(diag[:2500], end="" if diag[:2500].endswith("\n") else "\n")
        if len(diag) > 2500:
            print("--- diagnostics truncated: %d chars total ---" % len(diag))
    else:
        print("--- compiler diagnostics: (none) ---")

    if proc.returncode != 0:
        print("build: FAILED (ecj rc=%s); not packaging anything, no jar written" % proc.returncode,
              file=sys.stderr)
        return 1

    classes = []
    for root, _dirs, files in os.walk(out_dir):
        for name in files:
            if name.endswith(".class"):
                full = os.path.join(root, name)
                classes.append((full, os.path.relpath(full, out_dir).replace("\\", "/")))
    classes.sort(key=lambda pair: pair[1])
    if not classes:
        print("build: FAILED (ecj produced no class files); no jar written", file=sys.stderr)
        return 1

    with zipfile.ZipFile(jar_out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("META-INF/MANIFEST.MF", manifest(args.version, java_level))
        for full, rel in classes:
            zf.write(full, rel)

    print()
    print("built %s (%d bytes, %d classes)" % (jar_out, os.path.getsize(jar_out), len(classes)))
    for _full, rel in classes:
        print("  %s" % rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
