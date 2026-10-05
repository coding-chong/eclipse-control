"""input.fixture -- SWT 接不接受外部合成输入（A14 / P6.2）.

判据（`design-project.md` §18.4）：六条同构断言，**两条是证伪**。

| # | 断言 | 期望 | 性质 |
|---|---|---|---|
| ① | 元素寻址点按钮（`BM_CLICK` → Button HWND） | 标题**必须变** | 能力 |
| ②a | 坐标消息 → **Button HWND** | 记录结果 | 定论记录 |
| ②b | **同坐标同消息** → 顶层 Shell | 记录结果 | 定论记录（**对照组**） |
| ③ | 按键（`WM_KEYDOWN VK_RETURN` → Edit HWND） | 标题**必须变** | 能力 |
| ④ | 文本输入（`WM_SETTEXT` → Edit HWND） | 标题**必须变** | 能力 |
| ⑤ | 对**不存在**的控件点（产品库 `act_click_button`） | **必须失败** | **证伪** |
| ⑥ | 坐标点空白 | **必须无变化** | **证伪** |

②a 与 ②b 是本域最有价值的一条：两条**坐标相同、消息相同**，只差**收件人**。
⇒ 决定成败的是**寻址**，不是「SWT 不认合成消息」（`PostMessage` 不做命中测试）。

**为什么 `requires_bridge=False`**：本用例判的是 **SWT 的行为**，与 `ctl` 的桥无关；
它自带夹具启停，不连任何 IDE 实例。这也是它能在 `verify --all` 里跑而不需要先 `install` 的原因。

**为什么必须借目标安装树里的 SWT 片段**（§18.6 / D1）：要判的是「**GS32 / CCS 那个 SWT 版本**认不认
合成输入」。换一个 SWT 版本搭夹具，结论**推不回目标** —— 借它不是图省事，是保证结论可迁移。

**纪律**：判据只有一条 —— **动作 → 可观测回读差**；夹具把每次动作的结果写进**窗口标题**，
所以标题就是唯一可观测（`OK` ≠ 到位，F9）。
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
import zipfile
from typing import Dict, List, Optional, Tuple

from ... import run as run_door
from ...client import Client, write_endpoint
from ...errors import NotFoundError
from ..runner import Case, Skip
from ._util import verdict

#: 仓库根。本文件在 ``<root>/ctl/verify/cases/`` 下。
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_FIXTURE_DIR = os.path.join(_ROOT, "tools", "fixture-swt")
#: Build output is **per target**, never shared.  The class-file version a target's
#: JVM accepts differs (`java_target` 17 vs 8) and so does the SWT fragment, so one
#: shared `out/` makes the second target silently reuse the first one's class.
#: Measured 2026-10-02: CCS (JRE 11.0.13) picked up the Java-17 `Fixture.class`
#: (major 61) a GS32 run had left behind, the JVM refused to load it, and the
#: fixture window never appeared -- reported as a SKIP, never as a PASS.
def _out_dir(target_name: str) -> str:
    return os.path.join(_FIXTURE_DIR, "out", target_name)
_PROBE = os.path.join(_FIXTURE_DIR, "probe.ps1")

#: 夹具基类名（`Fixture.java` 的 `BASE`）。标题即判据：
#: ``ctl-fixture`` → ``ctl-fixture GO <n>`` / ``KEY <k>`` / ``TEXT <x>``。
_TITLE = "ctl-fixture"
_PAYLOAD = "P6CASE"
#: 等窗口出现。夹具进程约 5 s 就绪，但**首次 pwsh 调用要现场 Add-Type 编译 C# 类**（实测 40–50 s），
#: 所以轮询必须放在 pwsh 进程内（探针的 ``-WaitSecs``），不能靠外部反复起 pwsh。
_READY_SECS = 120
_PROBE_TIMEOUT = 240
_BUILD_TIMEOUT = 300

#: 期望值。``None`` = **只记录不判定**（②a/②b 是定论记录，不是能力断言）。
_CHANGED = "CHANGED"
_UNCHANGED = "UNCHANGED"
_RECORD = None

#: (id, 探针断言, 重试次数, 期望, 标题形态断言, 说明)
#:
#: ``重试`` 只对点类有意义：研究档 §2 实测本夹具 **9 次点击 1 次未落地**，
#: 所以「点击后轮询确认」是必须的，不能假定一次必中。
#: 对期望 **无变化** 的 ②b/⑥ 必须为 1 —— 重试只会重复发同一条消息，无意义且会把稳定负例变不确定。
_PROBES: Tuple[Tuple[str, str, int, Optional[str], Optional[str], str], ...] = (
    ("button", "button", 3, _CHANGED, "GO ", "① 元素寻址点 Button（BM_CLICK → Button HWND）"),
    ("coord-button", "coord-button", 3, _RECORD, None, "②a 坐标消息 → Button HWND"),
    ("coord-shell", "coord-shell-at-button", 1, _RECORD, None, "②b 同坐标同消息 → 顶层 Shell（对照）"),
    ("key", "key", 1, _CHANGED, "KEY 13", "③ 按键（WM_KEYDOWN VK_RETURN → Edit HWND）"),
    ("text", "text", 1, _CHANGED, "TEXT " + _PAYLOAD, "④ 文本输入（WM_SETTEXT → Edit HWND）"),
    ("coord-blank", "coord-blank", 1, _UNCHANGED, None, "⑥ 坐标点空白"),
)

#: ⑤ 走**产品面**：`ctl run` 脚本命名空间里的 `act_click_button`（`ctl/run.py`），不走探针 ——
#: 契约就在那一层（研究档 §5）。下层 `tools/win-click-button.ps1` 已于 2026-10-02 对齐
#: （**0 命中**与**>1 命中**都 `exit 1`）。
_NONEXISTENT_TEXT = "&NoSuchButton"


def _click_nonexistent(pid: int) -> Tuple[int, List[str]]:
    """⑤ 的载具：**产品库**的 `act_click_button` 对不存在的控件必须失败。

    夹具进程是本用例自己起的，这里没有桥、也没有真的 run；于是搭一个最小的 run 目录
    （`endpoint.json` 只写夹具的 pid），再把产品面**原样**喂进去 —— `ctl run` 脚本命名空间
    暴露的就是这一个 `act_click_button`，它解析 pid 走的也是同一条 `endpoint.json` 路径。
    失败必须是**寻址失败**（`NotFoundError`）：若这里冒出别的 `CtlError`（例如运行记录里
    没有 pid），那是前置没就绪，不能算 ⑤ 通过。
    """
    root = tempfile.mkdtemp(prefix="eclipse-ctl-fixture-endpoint-")
    try:
        write_endpoint(root, "fixture", 1, pid)
        client = Client(port=1, run_root=root, run_id="fixture")
        namespace = run_door._make_namespace(client, run_door._DoorState(run_id="fixture"))
        try:
            namespace["act_click_button"](_NONEXISTENT_TEXT, title=_TITLE, yes=True)
        except NotFoundError as exc:
            return 1, [exc.line()]
        return 0, ["clicked a control that does not exist (unexpected)"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _find(source_dir: str, pattern: str) -> Optional[str]:
    hits = sorted(glob.glob(os.path.join(source_dir, pattern)))
    return hits[0] if hits else None


def _resolve(target) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """借目标安装树里的 JRE / ECJ / SWT 片段（§18.6 的 D1 裁决）。"""
    java = target.java_exe()
    ecj = target.ecj_jar()
    swt = _find(target.install_dir, os.path.join(
        "plugins", "org.eclipse.swt.win32.win32.x86_64_*.jar"))
    return java, ecj, swt


def _decode(raw: Optional[bytes]) -> str:
    """Decode a child process' output **without ever losing it**.

    ``text=True`` alone is unsafe here: on a Chinese Windows locale the JVM writes
    GBK, so a fixed UTF-8 decode raises inside the reader thread and ``stderr``
    comes back as ``None`` -- the failure then reports an **empty** cause
    (measured 2026-10-02: CCS's ``fixture build failed (rc=1): `` had no tail at
    all, hiding the real ``UnsupportedClassVersionError``).  Same family as
    ``measurement-hygiene.md`` 13.6: a failure that hides its own cause.
    """
    if not raw:
        return ""
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _can_host_ecj(java: str, ecj: str) -> bool:
    """True when `java` can actually load and run the ECJ jar -- probed, not guessed."""
    try:
        proc = subprocess.run([java, "-jar", ecj, "-version"],
                              capture_output=True, timeout=_BUILD_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _owner_of(ecj: str) -> Optional[object]:
    """The configured target whose installation tree contains `ecj`, if any."""
    import ctl.targets as _targets
    try:
        cfg = _targets.load({})
    except Exception:
        return None
    want = os.path.abspath(ecj).replace("\\", "/")
    best = None
    for name in cfg.target_names():
        t = cfg.target(name)
        d = os.path.abspath(t.install_dir).replace("\\", "/").rstrip("/")
        if want.startswith(d + "/") and (best is None or len(d) > len(best[0])):
            best = (d, t)
    return best[1] if best else None


def _build_java(target, ecj: str, log: List[str]) -> str:
    """The JVM that *compiles* the fixture -- **the ECJ and its JVM must match**.

    A batch compiler is itself bytecode, so the JVM picked here must be able to
    *load* it; that is a different question from what level it *emits* (which is
    ``-target <java_target>``, handled below).  Measured 2026-10-02, while
    ``ccs12`` still borrowed GS32's ECJ 3.36: CCS's bundled JRE 11 died with
    ``UnsupportedClassVersionError: class file version 61.0``.  Since 2026-10-06
    ``ccs12`` finds its own compiler inside its XDCtools component (ECJ 3.14,
    which its JRE 11 loads without complaint), so the first candidate wins and
    the owner lookup below is no longer the path ``ccs12`` takes -- it stays as
    the general fallback for a target whose own JVM cannot host the compiler
    discovered for it.

    Only the **compiler** runs on the JVM picked here: the fixture is still
    launched with the target's own JVM (``_start``) so the target's SWT is what
    gets exercised.
    """
    target_java = target.java_exe() or ""
    candidates: List[Tuple[str, str]] = []
    if target_java:
        candidates.append((target.name, target_java))
    owner = _owner_of(ecj)
    if owner is not None:
        owner_java = owner.java_exe()
        if owner_java and all(owner_java.lower() != j.lower() for _, j in candidates):
            candidates.append((owner.name, owner_java))
    for name, java in candidates:
        ok = _can_host_ecj(java, ecj)
        log.append("build-jvm: %s [%s] -> %s"
                   % (java, name, "can host ECJ" if ok else "cannot host ECJ"))
        if ok:
            return java
    # Nothing can host it: hand back the target's own JVM so the compile below
    # fails with the compiler's *real* message instead of an empty string.
    return target_java


def _swt_version(swt_path: str) -> str:
    """``…org.eclipse.swt.win32.win32.x86_64_3.119.0.v2022….jar`` → ``3.119.0``."""
    for part in os.path.basename(swt_path or "").split("_"):
        if part and part[0].isdigit() and part.count(".") >= 2:
            return part.split(".v")[0]
    return ""


def _ensure_built(java: str, ecj: str, swt: str, source_level: str,
                  out_dir: str, log: List[str]) -> None:
    """编译夹具并从 SWT 片段里抽出原生 DLL。

    **幂等是按构建输入键控的**，不只按 mtime：输入 = 源级 / SWT 片段 / ECJ / **跑 ECJ 的 JVM**，
    记在 ``<out_dir>/.stamp``；任一变化就把整个输出（含 DLL）作废重来。只比 mtime 不够 ——
    换 target 或换 SWT 片段时源码没动，但产物已经不能用（见 `_out_dir` 的实测）。
    """
    src_java = os.path.join(_FIXTURE_DIR, "Fixture.java")
    stamp = os.path.join(out_dir, ".stamp")
    want = "%s|%s|%s|%s" % (source_level, swt, ecj, java)

    have = ""
    if os.path.isfile(stamp):
        try:
            with open(stamp, encoding="utf-8") as fh:
                have = fh.read().strip()
        except OSError:
            have = ""
    if have != want:
        # 输入变了 ⇒ class 与 DLL 一起作废（DLL 是从上一份 SWT 片段里抽的）。
        shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)

    cls = os.path.join(out_dir, "Fixture.class")
    if os.path.isfile(cls) and os.path.getmtime(cls) >= os.path.getmtime(src_java):
        log.append("build: up-to-date (%s)" % want)
    else:
        proc = subprocess.run(
            [java, "-jar", ecj, "-source", source_level, "-target", source_level,
             "-nowarn", "-cp", swt, "-d", out_dir, src_java],
            capture_output=True, timeout=_BUILD_TIMEOUT)
        tail = (_decode(proc.stdout) + _decode(proc.stderr)).strip().replace("\n", " ")[:300]
        log.append("build: rc=%d %s" % (proc.returncode, tail))
        if proc.returncode != 0:
            raise Skip("fixture build failed (rc=%d): %s" % (proc.returncode, tail))

    with open(stamp, "w", encoding="utf-8") as fh:
        fh.write(want)

    dlls = [n for n in os.listdir(out_dir) if n.lower().endswith(".dll")]
    if dlls:
        log.append("swt dlls: present (%d)" % len(dlls))
    else:
        # SWT 的原生库不在 PATH 上，必须从平台片段 jar 里抽到 class 同层，
        # 否则 `new Display()` 直接 UnsatisfiedLinkError（§18.6 的 ②）。
        with zipfile.ZipFile(swt) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".dll")]
            for name in names:
                with zf.open(name) as fh:
                    with open(os.path.join(out_dir, os.path.basename(name)), "wb") as out:
                        shutil.copyfileobj(fh, out)
        log.append("swt dlls: extracted (%d)" % len(names))


def _start(java: str, swt: str, out_dir: str, log: List[str]) -> subprocess.Popen:
    classpath = out_dir + os.pathsep + swt
    proc = subprocess.Popen(
        [java, "-Djava.library.path=" + out_dir, "-cp", classpath, "Fixture"],
        cwd=_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace")
    log.append("fixture: started pid=%d" % proc.pid)
    return proc


def _run_probe(assertion: str, pid: int, retries: int) -> Dict[str, object]:
    """一次探针调用 = 一次「发动作 + 回读标题」。返回原始行，供证据链留档。"""
    cmd = ["pwsh", "-NoProfile", "-File", _PROBE,
           "-TitleLike", _TITLE, "-Assertion", assertion,
           "-ProcId", str(pid), "-Retries", str(retries),
           "-WaitSecs", str(_READY_SECS), "-Payload", _PAYLOAD]
    # `errors="replace"` 不是保险丝，是**必需**：pwsh 的 stdout 按控制台码页（本机 cp936）编码，
    # 任何非 ASCII 字节都会让解码线程抛 UnicodeDecodeError 并**丢掉整段输出**
    # —— 症状是"探针没有输出"，极具误导性（实测踩到）。探针侧也已改成只出 ASCII。
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=_PROBE_TIMEOUT)
    lines = [ln.rstrip() for ln in ((proc.stdout or "") + (proc.stderr or "")).splitlines() if ln.strip()]

    before = after = None
    verdict_line = ""
    attempts = ""
    for ln in lines:
        # 探针把窗口句柄和 before 打在同一行（`window=0x…  before=[…]`），
        # 所以**不能**用 startswith 找 before —— 实测这一条会让 before 恒为 None。
        if "before=[" in ln:
            before = ln.split("before=[", 1)[1].rstrip("]")
        if "after=[" in ln:
            after = ln.split("after=[", 1)[1].rstrip("]")
        if ln.startswith("verdict="):
            verdict_line = ln.split("=", 1)[1].strip()
        elif ln.startswith("attempts="):
            attempts = ln.split("=", 1)[1].strip()

    return {
        "rc": proc.returncode,
        "before": before,
        "after": after,
        "verdict": verdict_line or ("ERR" if proc.returncode else ""),
        "attempts": attempts,
        "lines": lines,
    }


def _action(ctx) -> Dict[str, object]:
    target = ctx.target
    java, ecj, swt = _resolve(target)
    if not (java and ecj and swt):
        # 不是失败，是**这里没有可用的工具链** —— 如实 SKIP，不伪装成 PASS（P1.1 禁止静默跳过）。
        raise Skip(
            "target %s 的安装树里缺夹具工具链（java=%s ecj=%s swt=%s）；"
            "本用例只回答「该产品的 SWT 认不认合成输入」，缺一即无法给出结论"
            % (target.name, bool(java), bool(ecj), bool(swt)))

    log: List[str] = []
    out_dir = _out_dir(target.name)
    build_java = _build_java(target, ecj, log)
    _ensure_built(build_java, ecj, swt, target.java_target or "17", out_dir, log)
    log.append("build: out_dir=%s" % out_dir)
    log.append("swt: %s (version %s)" % (swt, _swt_version(swt) or "?"))

    proc = _start(java, swt, out_dir, log)
    rows: List[Dict[str, object]] = []
    try:
        # 先探一次窗口（探针自带等待），顺便把子窗清单留成证据。
        first = _run_probe("children", proc.pid, 1)
        ctx.note("fixture: window probe rc=%d" % first["rc"])
        for ln in first["lines"]:
            ctx.note("  " + ln)
        if first["rc"] != 0:
            raise Skip("夹具窗口未出现（pid=%d）：%s" % (proc.pid, first["lines"][-1:] or []))

        for cid, assertion, retries, want, shape, why in _PROBES:
            res = _run_probe(assertion, proc.pid, retries)
            row = dict(res)
            row.update({"id": cid, "expect": want, "shape": shape, "why": why,
                        "retries": retries})
            rows.append(row)
            ctx.note("%-12s %s | before=%r after=%r verdict=%s attempts=%s"
                     % (cid, "rc=%d" % res["rc"], res["before"], res["after"],
                        res["verdict"], res["attempts"]))
            for ln in res["lines"]:
                ctx.note("    " + ln)

        # ⑤ 证伪：对**不存在**的控件点，必须失败。走**产品面**（`ctl run` 的脚本命名空间，
        # 调的就是 `ctl/run.py` 里那个 `act_click_button`），不走探针。
        non_rc, non_lines = _click_nonexistent(proc.pid)
        rows.append({"id": "nonexistent", "rc": non_rc,
                     "expect": None, "shape": None, "retries": 1,
                     "before": None, "after": None, "verdict": "ERR" if non_rc else "OK",
                     "why": "⑤ 对不存在的控件点（证伪：必须失败）",
                     "lines": non_lines})
        ctx.note("nonexistent  rc=%d | %s" % (non_rc, (non_lines or [""])[-1][:200]))
    finally:
        # 夹具是**本用例自己起的**，无论成败都必须收干净 —— 否则下次跑会留下幽灵窗口，
        # 而本用例按 pid 寻址，幽灵窗口会让 `-TitleLike` 命中多扇窗（探针是 fail-closed 的，会直接报错）。
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        log.append("fixture: stopped pid=%d (rc=%s)" % (proc.pid, proc.returncode))

    return {"log": log, "assertions": rows, "target": target.name,
            "swt": _swt_version(swt)}


def _expect(ctx, result) -> Tuple[bool, str]:
    rows = result.get("assertions") or []
    problems: List[str] = []

    for row in rows:
        cid = row["id"]
        got_rc = int(row.get("rc") or 0)

        if cid == "nonexistent":
            # ⑤ 的唯一判据：**必须失败**。退 0 = 静默成功 = 正是要证伪掉的那件事。
            if got_rc == 0:
                problems.append("⑤ 不存在的控件**必须失败**，实测退出码 0（静默成功）")
            continue

        if got_rc != 0:
            problems.append("%s：探针退出码 %d（窗口/控件没找到）" % (cid, got_rc))
            continue

        want = row["expect"]
        got = row["verdict"]
        if want is _RECORD:
            continue  # ②a/②b 是定论记录，不判定
        if got != want:
            note = ""
            if cid == "key":
                # 平台的 SWT 是否把「合成 WM_KEYDOWN」派发给控件自身的 KeyListener。
                # 实测（2026-10-02，2×2 同启动方式）：SWT 3.119.0 / Eclipse 4.23 **不**派发；
                # SWT 3.124.200 / Eclipse 4.30 **派发**。换 JVM（11 ↔ 23）不改变结果；
                # 补 `WM_SETFOCUS` 或真 `SetForegroundWindow` 也不改变结果
                # ⇒ 归因到**平台版本**，进兼容矩阵（R5' 要求差异有归因，不允许静默）。
                note = ("｜目标 SWT=%s —— 已知平台差异（兼容矩阵 input.fixture/key）："
                        "Eclipse 4.23 不把合成 WM_KEYDOWN 派发给控件自身的 KeyListener"
                        % (result.get("swt") or "?"))
            problems.append("%s：期望 %s，实测 %s（after=%r）%s"
                            % (cid, want, got, row.get("after"), note))
            continue
        shape = row.get("shape")
        if shape and want == _CHANGED and shape not in (row.get("after") or ""):
            problems.append("%s：标题形态不含 %r（after=%r）" % (cid, shape, row.get("after")))

    # 「至少一条证伪」是本用例的存在理由，缺了它等于没判（A14）。
    tried = {row["id"] for row in rows}
    for required in ("nonexistent", "coord-blank"):
        if required not in tried:
            problems.append("证伪例 %s 没有执行" % required)

    changed = sum(1 for row in rows if row.get("verdict") == "CHANGED")
    detail = ("%d 条断言（%d 条标题有变化；证伪 ⑤=%s ⑥=%s）｜ target=%s"
              % (len(rows), changed,
                 next((row.get("rc") for row in rows if row["id"] == "nonexistent"), "?"),
                 next((row.get("verdict") for row in rows if row["id"] == "coord-blank"), "?"),
                 result.get("target")))
    return verdict(problems, detail)


CASE = Case(
    name="input.fixture",
    group="input",
    # 两个 target 都挂（R5′ 双 target 一致）。工具链解析本就是**按 target** 的：
    # `_resolve()` 走 `target.java_exe()` / `target.ecj_jar()` + 该树自己的 SWT 片段 ——
    # CCS 侧实测三条全解析得到（自带 `jre/bin/java.exe`、SWT 片段在、ECJ 走 target 表里那份）。
    # 真缺任一 ⇒ 如实 SKIP（不伪装成 PASS），而不是靠闸门预先排除。
    targets=("gs32", "ccs12"),
    description=("SWT 接受元素寻址的合成输入（六条断言：①③④ 能力、②定论记录、⑤⑥ 证伪）；"
                 "自带夹具启停，不连桥"),
    action=_action,
    expect=_expect,
    requires_bridge=False,
    # 夹具不是 IDE：没有「IDE 要被动过」需要守卫，屏幕守卫在这里没有对象。
    screen_guard=False,
    evidence=("fixture:window", "assertions:table", "fixture:log"),
)
