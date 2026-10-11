# bridge/BUILD-NOTES.md — build & jar verification

2026-10-11 · bridge `eclipse-ctl.bridge` **0.3.0** (protocol 1)

> **版本沿革（2026-10-02）**：桥的 `Bundle-Version` 原为 **3.1.0**（`livebridge 3.0.0` 遗留序列的
> 默认值），与项目版本不一致 ⇒ 违反 `design-project.md` §15.2「项目版本 == 桥 `Bundle-Version`」。
> 现统一为项目版本 **0.1.0**（`bridge/build.py:DEFAULT_VERSION`），jar 名随之变为
> `eclipse-ctl.bridge_0.1.0_{gs32,ccs12}.jar`（两 target 各一份，**不是**单 jar）。
> **沿革续（2026-10-11 切版）**：`0.1.0 → 0.2.0`（2026-10-06 那批）→ **`0.3.0`**（发布准备：
> `ctl/__init__.py` 与 `bridge/build.py:DEFAULT_VERSION` **两处同改**，产物名随之变为
> `eclipse-ctl.bridge_0.3.0_{gs32,ccs12}.jar`）。**文件头那行是"撰写当时"的版本**，现为 0.3.0。
> ⚠️ **切版后要把 `dist/` 里的旧 jar 删掉**：`find_bridge_jar` 按名字 `sorted()` 取首个、
> **不比较 `Bundle-Version`**（本仓 `measurement-hygiene.md` §13.9 反例 A 实测过 `0.1.0` 胜 `0.2.0`），
> 新旧并存时它会让**旧的那份**胜出 —— 静默用旧桥，而版本号看起来是新的。
> **下文标着 2026-10-01 的原始输出，是当时的实况**（当时确实是 3.1.0，且是**单 jar** 构建、7 classes）——
> 保留作历史，不再作当前产出；照抄命令时以「输出名随 `--version` 变」为准。

Toolchain: this machine has **no `javac` and no `jar.exe`**. ECJ and the JVM are borrowed
**read-only** from the target install tree, packaging is Python `zipfile`
(research/facts-baseline.md §8; recipe `D:\tmp\gs32-bridge-test.py:19-102`).
Nothing is downloaded and nothing is installed; the install tree is never written to.

```
$ python bridge/build.py --help      # --target {gs32|ccs12} --src --out --java --jre --ecj --version
```

## 1. Build (target gs32) — exit code 0

```
$ python bridge/build.py --target gs32
target      : gs32 (java level 17)
src tree    : D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2
jre         : D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2\plugins\org.eclipse.justj.openjdk.hotspot.jre.minimal.win32.x86_64_23.0.2.v20250131-0604\jre\bin\java.exe
ecj         : D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2\plugins\org.eclipse.jdt.core.compiler.batch_3.36.0.v20231114-0937.jar
source      : D:\gitclone\eclipse-ctl\bridge\src\ctl\bridge\LiveBridge.java
classpath   : 19 jars
              org.eclipse.swt.win32.win32.x86_64_3.124.200.v20231113-1355.jar
              org.eclipse.swt_3.124.200.v20231113-1355.jar
              org.eclipse.jface_3.32.0.v20231107-0834.jar
              org.eclipse.ui.workbench_3.131.0.v20231201-0512.jar
              org.eclipse.ui.console_3.13.100.v20230914-0751.jar
              org.eclipse.ui.ide_3.22.0.v20231102-1012.jar
              org.eclipse.ui_3.205.0.v20230922-1312.jar
              org.eclipse.core.commands_3.11.200.v20231108-1058.jar
              org.eclipse.core.runtime_3.30.0.v20231102-0719.jar
              org.eclipse.core.jobs_3.15.100.v20230930-1207.jar
              org.eclipse.core.resources_3.20.0.v20231102-0934.jar
              org.eclipse.core.filesystem_1.10.200.v20231102-0934.jar
              org.eclipse.equinox.common_3.18.200.v20231106-1826.jar
              org.eclipse.equinox.registry_3.11.400.v20231102-2218.jar
              org.eclipse.e4.core.contexts_1.12.400.v20231103-2012.jar
              org.eclipse.e4.ui.workbench_1.15.200.v20231030-2045.jar
              org.eclipse.e4.ui.model.workbench_2.4.100.v20230801-1255.jar
              org.eclipse.text_3.13.100.v20230801-1334.jar
              org.eclipse.osgi_3.18.600.v20231110-1900.jar
command     :
  "<jre>" -jar "<ecj>" -source 17 -target 17 -encoding UTF-8 -nowarn -proc:none -cp <19 jars> -d "<repo>/bridge/build/gs32/out" "<repo>/bridge/src/ctl/bridge/LiveBridge.java"

ecj rc=0
--- compiler diagnostics: (none) ---

built D:\gitclone\eclipse-ctl\bridge\dist\eclipse-ctl.bridge_3.1.0.jar (25863 bytes, 7 classes)
  ctl/bridge/LiveBridge$1.class
  ctl/bridge/LiveBridge$2.class
  ctl/bridge/LiveBridge$3.class
  ctl/bridge/LiveBridge$CtlException.class
  ctl/bridge/LiveBridge$Handler.class
  ctl/bridge/LiveBridge$Method.class
  ctl/bridge/LiveBridge.class
```

`-encoding UTF-8` is passed because ECJ otherwise decodes the source with the platform
encoding (a `§` in a string literal turned into mojibake in the first build).

## 2. Jar verification (raw output)

```
$ python -c "import zipfile;z=zipfile.ZipFile('bridge/dist/eclipse-ctl.bridge_3.1.0.jar');print(z.read('META-INF/MANIFEST.MF').decode())"
Manifest-Version: 1.0
Bundle-ManifestVersion: 2
Bundle-SymbolicName: eclipse-ctl.bridge
Bundle-Version: 3.1.0
Bundle-Name: eclipse-ctl bridge
Bundle-Activator: ctl.bridge.LiveBridge
Require-Bundle: org.eclipse.ui,org.eclipse.ui.workbench,org.eclipse.ui.ide,org.eclipse.ui.console,org.eclipse.swt,org.eclipse.jface,org.eclipse.text,org.eclipse.core.commands,org.eclipse.core.runtime,org.eclipse.core.jobs,org.eclipse.core.resources,org.eclipse.core.filesystem,org.eclipse.equinox.common,org.eclipse.equinox.registry,org.eclipse.e4.core.contexts,org.eclipse.e4.ui.workbench,org.eclipse.e4.ui.model.workbench
Import-Package: org.osgi.framework
Bundle-RequiredExecutionEnvironment: JavaSE-17

$ python -c "import zipfile;z=zipfile.ZipFile('bridge/dist/eclipse-ctl.bridge_3.1.0.jar');
            mf=z.read('META-INF/MANIFEST.MF').decode();
            [print(n) for n in z.namelist()];
            print('livebridge in MANIFEST text :', mf.count('livebridge'));
            print('livebridge in entry paths   :', sum(n.count('livebridge') for n in z.namelist()))"
META-INF/MANIFEST.MF
ctl/bridge/LiveBridge$1.class
ctl/bridge/LiveBridge$2.class
ctl/bridge/LiveBridge$3.class
ctl/bridge/LiveBridge$CtlException.class
ctl/bridge/LiveBridge$Handler.class
ctl/bridge/LiveBridge$Method.class
ctl/bridge/LiveBridge.class
livebridge in MANIFEST text : 0
livebridge in entry paths   : 0

$ grep -rn "D:[/]tmp" bridge/          # same pattern, bracket only so this file cannot match itself
(no output)          # rc=1 -> zero hits in the source, build.py, notes and jar payload
```

The manifest is CRLF-only (`CRLF=10 bareLF=0`) and is parsed by `java.util.jar.Manifest`
(see §4), which is what Equinox does when it installs the bundle.

## 3. Failure behaviour (must not leave a stale artifact)

```
$ python bridge/build.py --target ccs12
build: ERROR: no ECJ batch compiler found for target 'ccs12' under D:/ti/ccs1281/ccs/eclipse
(tried: plugins/org.eclipse.jdt.core.compiler.batch_*.jar); this install tree ships no JDT
-- pass --src <tree that has one> or --ecj <ecj.jar>
$ echo $?
1

$ python bridge/build.py --target gs32 --java <broken>.java --out <pre-existing jar>
ecj rc=4294967295
...
1. ERROR in <broken>.java (at line 1) ... Syntax error
...
build: FAILED (ecj rc=4294967295); not packaging anything, no jar written
$ echo $?
1
$ ls <pre-existing jar>
(absent — the target jar is removed before compiling, so a stale jar can never be
 mistaken for a fresh one; the last good jar in bridge/dist/ is left untouched)
```

CCS 12.8.1 ships a JRE (`<src>/jre/bin/java.exe`) but **no JDT**. Since 2026-10-06 the
`ccs12` target discovers its own compiler inside the product's XDCtools component
(`../../xdctools_*/packages/xdc/shelf/java/ecj.jar`, ECJ 3.14), so `--target ccs12`
builds without `--ecj`; the hard-coded borrow from the GS32 tree is gone. That ECJ caps at
`-source/-target 9`, which is why `ccs12`'s level is **8** (the GS32 ECJ is not used, and
`-source 11` is exactly what this tree's own compiler rejects). The error block above is the
**pre-2026-10-06** message (it listed only `plugins/`); the current one also lists the
ancestor glob.

## 4. Offline verification of the built jar (no IDE)

Two throwaway harnesses (not committed) ran the **built jar** on the target JRE with the 19
bundles above on the classpath plus a `java.lang.reflect.Proxy` `BundleContext`:

* reflection smoke — manifest parsed with `java.util.jar.JarFile`, `ctl.bridge.LiveBridge`
  loaded and constructed, `sys.help` rendered 16 method rows, `sys.ping` → `pong`,
  `sys.wait` (no arg) → `OK / idle=true / pending=0`. Payload strings are pure ASCII.
* wire test — real sockets against the real accept loop, port 8899, `-Dctl.log`:

```
=== 1) sys.ping
    | OK
    | pong from gs32ctl-conn-1
    | END
=== 2) sys.env
    | OK
    | java.version=23.0.2
    | os.name=Windows 11
    | protocol=1
    | bundle=eclipse-ctl.bridge version=3.1.0 id=42 state=32
    | port=8899 uiTimeoutMs=3000 maxConnections=8 log=D:\tmp\ectl-scratch\wire.log
    | thread=gs32ctl-conn-2
    | END
=== 3) unknown method / empty request
    | ERR badrequest unknown method: no.such.method (see sys.help)
    | END
    | ERR badrequest unknown method: <empty request> (see sys.help)
    | END
=== 4) ui.shells with no workbench
    | ERR noWorkbench workbench is not created yet: java.lang.NoClassDefFoundError: org/eclipse/ui/testing/TestableObject
    | END
=== 5) cap: hold 8 idle connections
    idle sockets accepted and held (no bytes): 8/8
=== 6) 9th and 10th connection must be ERR busy
    | ERR busy bridge is at capacity (8 concurrent connections); retry
    | END
    connection closed by bridge after ERR busy: true
    | ERR busy bridge is at capacity (8 concurrent connections); retry
    | END
    connection closed by bridge after ERR busy: true
=== 7) release slots, ping works again
    | OK
    | pong from gs32ctl-conn-14
    | END
```

Bridge log for the same run (timestamps + per-request duration + result code):

```
[2026-10-01 01:49:44.934] [main] START bundle=eclipse-ctl.bridge version=3.1.0 state=32
[2026-10-01 01:49:44.959] [main] LISTENING on 127.0.0.1:8899 maxConn=8 uiTimeoutMs=3000 log=...
[2026-10-01 01:49:45.623] [gs32ctl-conn-2] REQ "sys.env" -> OK (7 ms, 6 lines)
[2026-10-01 01:49:45.623] [gs32ctl-conn-1] REQ "sys.ping" -> OK (30 ms, 1 lines)
[2026-10-01 01:49:45.632] [gs32ctl-conn-3] REQ "no.such.method" -> ERR badrequest unknown method: no.such.method (see sys.help) (10 ms, 0 lines)
[2026-10-01 01:49:45.636] [gs32ctl-conn-4] REQ "" -> ERR badrequest unknown method: <empty request> (see sys.help) (0 ms, 0 lines)
[2026-10-01 01:49:54.341] [gs32ctl-bridge] BUSY reject (8 in flight, max 8)
[2026-10-01 01:49:54.346] [gs32ctl-bridge] BUSY reject (8 in flight, max 8)
[2026-10-01 01:49:55.159] [gs32ctl-conn-14] REQ "sys.ping" -> OK (1 ms, 1 lines)
```

`sys.env`/`sys.help` report `version=unknown` only in the reflection harness, where there is
no OSGi context; inside the IDE they read the real `Bundle-Version` from the bundle.

### 4.1 UI timeout / concurrency contract (real SWT `Display`, stubbed workbench)

A third throwaway harness creates a **real SWT `Display`** (SWT native DLL extracted from the
platform fragment) plus a real `Shell`/`Composite`/`Button` tree, and defines the shipped
`ctl.bridge.LiveBridge` in a child-first loader together with a `org.eclipse.ui.PlatformUI`
test double (the Eclipse jars are signed, so an unsigned class in `org.eclipse.ui` can only be
defined by a different loader). An event pump on the SWT thread plays the role of the IDE
event loop and can be stopped, which makes the timeout deterministic.

```
== normal path (pump running) ==
sys.ping   -> OK / pong from gs32ctl-conn-1 / END
ui.shells  -> OK / display=org.eclipse.swt.widgets.Display@cb51256 onThread=main
              shellCount=1 / shell text="ectl-ui-test" ... / END
ui.parts   -> OK / workbenchWindows=1 / perspective id=org.eclipse.cdt.ui.CPerspective / END
ui.viewids -> OK /  view id=com.gs.memory.view label="Memory"
              registeredViews total=1 matched(prefix=)=1 returned=1 truncated=false / END
== queued-job test: sys.wait must return OK/idle=false on budget expiry ==
sys.wait 400       -> OK / mode=budget / waited_ms=402 budget_ms=400 / idle=false / pending=1
                      jobs_total=1 running=1 waiting=0 sleeping=0 none=0
                      busy name="probe-slow" state=RUNNING / END
sys.wait jobs-idle -> OK / waited_ms=2215 budget_ms=15000 / idle=true / pending=0 / END
sys.wait           -> OK / mode=snapshot / waited_ms=0 / idle=true / pending=0 / END
== cmd.list full export (stubbed ICommandService with 666 ids) ==
cmd.list             idLines=666  definedCommandIds total=666 matched(prefix=)=666 returned=666 truncated=false
cmd.list com.gs      idLines=2    definedCommandIds total=666 matched(prefix=com.gs)=2 returned=2 truncated=false
cmd.list --limit 5   idLines=5    definedCommandIds total=666 matched(prefix=)=666 returned=5 truncated=true
== sys.help idempotent column ==
methods=16
ui.open|<abs path>|yes|unknown|...
cmd.run|<id>|yes|unknown|...
cmd.runp|<id> <paramId>=<value>|yes|unknown|...
== timeout path (pump stopped, uiTimeoutMs=200) ==
ui.shells (pump off) -> ERR timeout UI task did not finish within 200 ms; the action is still
                        queued on the SWT event thread and MAY still take effect - read back
                        before retrying / END            (0 payload lines)
ui.tree 3 (pump off) -> ERR timeout ... / END
bridge log:
[..] [gs32ctl-conn-9] UI-TIMEOUT ui.shells arg="" after 200 ms; runnable is still queued on the SWT event thread and may still apply
[..] [gs32ctl-conn-9] REQ "ui.shells" -> ERR timeout UI task did not finish within 200 ms; the action is still queued on the SWT event thread and MAY still take effect - read back before retrying (204 ms, 0 lines)
== resume pump: the queued runnables now execute (discarded output) ==
ui.shells after resume -> OK / shellCount=1 / END      ← late runnable did not leak into any reply
== race interleaving: 40 requests while the pump is toggled ==
   timeouts=14 oks=26 bad=0
sys.ping after interleaving -> OK
ui.shells after interleaving -> OK
```

**`bad=0`** means every one of the 40 replies was either a clean `OK` (payload + `END`) or
exactly `ERR timeout …` + `END` — no `ERR internal`, no partial payload. The timeout path
therefore cannot be turned into `internal` by the UI thread writing its output late
(the runnable now writes to a private list that is published only after it completes).

**Measurement for P3.5 档 2** (recorded, not a defect of this build): with the flat cap of 8,
a 9th connection — including `sys.ping` — gets `ERR busy` while 8 other connections are held
open. That is exactly the condition implement.md P3.5 档 2 asks about; if `sys.ping` must stay
answerable while all 8 slots are jammed, design.md §4 has to reserve capacity for `sys.*`
(see the note in §5).

## 5. What changed in the bridge source vs the 3.0.0/`livebridge` slice-1 jar

* one thread per connection, cap 8, `ERR busy` over the cap; `ui.*`/`cmd.*` dispatch via
  `asyncExec` + bounded wait (`-Dctl.uiTimeoutMs`, default 15000) → `ERR timeout`
* `onUi` hands the SWT runnable a **private** output list and copies it into the caller's list
  only after the task finished (under the same lock): a timed-out request returns while its
  runnable is still queued, and the caller then iterates its own list — sharing that list
  would let the UI thread mutate it during iteration (`ConcurrentModificationException`, which
  the outer catch would have reported as `ERR internal` instead of `ERR timeout`, breaking the
  error-code contract). See §4.1 for the interleaving evidence.
* closed error-code set mapped on every failure path; single-line `ERR <code> <message>`
* new `sys.help` (machine-readable method table incl. `write` / `idempotent`) and
  `sys.wait [<ms>|jobs-idle]` (JobManager, timeout is `OK idle=false`) and
  `ui.console [--tail <n>]` (`ERR notfound` when no console exists)
* `cmd.list` exports everything (no silent 300-entry cap; `--limit <n>` to opt in) and adds
  a `handlerOnly` block recovered from `org.eclipse.ui.handlers` for ids that have a handler
  but no `<command>` declaration (e.g. `com.gs.chipsetting.commands.opthandler`)
* log path per contract (`-Dctl.log` / `CTL_LOG` / `~/.eclipse-ctl/bridge.log`); every
  request logs its duration and result code
* method table single-sourced in `LiveBridge.methods`, so `sys.help` cannot drift from the code
* connection thread names keep the historical `gs32ctl-` prefix (`gs32ctl-bridge` for the
  accept loop, `gs32ctl-conn-<seq>` per connection, from a monotonic sequence) for evidence
  continuity with earlier runs; the in-flight counter that enforces the cap of 8 is a
  separate counter, so log lines never share a thread name

Open question for design.md §4 (owner: main agent, not fixed here): the cap is flat, so 8
connections holding a blocked UI request make a 9th `sys.ping` return `ERR busy`. If §4 wants
`sys.*` to stay answerable under that condition, `sys.*` needs reserved capacity (or its own
dispatch path); the measurement above is the evidence P3.5 档 2 asks for.

`idempotent` for `ui.open` / `cmd.run` / `cmd.runp` is **`unknown`** on purpose: those three
values are filled in by P2.1 measurement, and `unknown` means "do not auto-retry".
