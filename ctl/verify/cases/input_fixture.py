"""input.fixture -- SWT 接不接受外部合成输入（A14 / P6.2）.

判据（`design-project.md` §18.4）：六条同构断言，**两条是证伪**。

| # | 断言 | 期望 | 性质 |
|---|---|---|---|
| ① | 元素寻址点按钮（`BM_CLICK` → Button HWND） | 标题**必须变** | 能力 |
| ②a | 坐标消息 → **Button HWND** | 记录结果 | 定论记录 |
| ②b | **同坐标同消息** → 顶层 Shell | 记录结果 | 定论记录（**对照组**） |
| ③ | 按键（`WM_KEYDOWN VK_RETURN` → Edit HWND） | 标题**必须变** | 能力 |
| ④ | 文本输入（`WM_SETTEXT` → Edit HWND） | 标题**必须变** | 能力 |
| ⑤ | 对**不存在**的控件点（`ctl act click-button`） | **必须失败** | **证伪** |
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
import sys
import zipfile
from typing import Dict, List, Optional, Tuple

from ..runner import Case, Skip
from ._util import verdict

#: 仓库根。本文件在 ``<root>/ctl/verify/cases/`` 下。
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_FIXTURE_DIR = os.path.join(_ROOT, "tools", "fixture-swt")
_OUT_DIR = os.path.join(_FIXTURE_DIR, "out")
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
_CLI_TIMEOUT = 120

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

#: ⑤ 走**产品面**（CLI），不走探针 —— 契约在 CLI 层成立（研究档 §5：
#: 底层 `win-click-button.ps1` 在找不到控件时**仍退 0**，只有 CLI 是 fail-closed）。
_NONEXISTENT_TEXT = "&NoSuchButton"


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


def _ensure_built(java: str, ecj: str, swt: str, source_level: str, log: List[str]) -> None:
    """编译夹具并从 SWT 片段里抽出原生 DLL。**幂等**：class 比源码新就跳过。"""
    os.makedirs(_OUT_DIR, exist_ok=True)
    src_java = os.path.join(_FIXTURE_DIR, "Fixture.java")
    cls = os.path.join(_OUT_DIR, "Fixture.class")

    if os.path.isfile(cls) and os.path.getmtime(cls) >= os.path.getmtime(src_java):
        log.append("build: up-to-date (Fixture.class 不比 Fixture.java 旧)")
    else:
        proc = subprocess.run(
            [java, "-jar", ecj, "-source", source_level, "-target", source_level,
             "-nowarn", "-cp", swt, "-d", _OUT_DIR, src_java],
            capture_output=True, text=True, timeout=_BUILD_TIMEOUT)
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip().replace("\n", " ")[:300]
        log.append("build: rc=%d %s" % (proc.returncode, tail))
        if proc.returncode != 0:
            raise Skip("fixture build failed (rc=%d): %s" % (proc.returncode, tail))

    dlls = [n for n in os.listdir(_OUT_DIR) if n.lower().endswith(".dll")]
    if dlls:
        log.append("swt dlls: present (%d)" % len(dlls))
    else:
        # SWT 的原生库不在 PATH 上，必须从平台片段 jar 里抽到 class 同层，
        # 否则 `new Display()` 直接 UnsatisfiedLinkError（§18.6 的 ②）。
        with zipfile.ZipFile(swt) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".dll")]
            for name in names:
                with zf.open(name) as fh:
                    with open(os.path.join(_OUT_DIR, os.path.basename(name)), "wb") as out:
                        shutil.copyfileobj(fh, out)
        log.append("swt dlls: extracted (%d)" % len(names))


def _start(java: str, swt: str, log: List[str]) -> subprocess.Popen:
    classpath = _OUT_DIR + os.pathsep + swt
    proc = subprocess.Popen(
        [java, "-Djava.library.path=" + _OUT_DIR, "-cp", classpath, "Fixture"],
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


def _run_cli(args: List[str]) -> "subprocess.CompletedProcess[str]":
    """跑产品 CLI 的**子进程**形式（用例本身也跑在 CLI 里，直接调会自己套自己）。

    ``-NoProfile`` 不是为了快，是为了不让 pwsh profile 往 stdout 打代理横幅污染解析 —— 这里用
    ``sys.executable`` 起的是 Python，于是连 pwsh 都不需要。
    """
    return subprocess.run([sys.executable, "-m", "ctl", *args], cwd=_ROOT,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=_CLI_TIMEOUT)


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
    _ensure_built(java, ecj, swt, target.java_target or "17", log)

    proc = _start(java, swt, log)
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

        # ⑤ 证伪：对**不存在**的控件点，必须失败。走产品面（CLI），因为契约在那一层。
        cli = _run_cli(["act", "click-button", "--title", _TITLE,
                        "--text", _NONEXISTENT_TEXT, "--yes"])
        rows.append({"id": "nonexistent", "rc": cli.returncode,
                     "expect": None, "shape": None, "retries": 1,
                     "before": None, "after": None, "verdict": "ERR" if cli.returncode else "OK",
                     "why": "⑤ 对不存在的控件点（证伪：必须失败）",
                     "lines": [ln.rstrip() for ln in (cli.stdout or "").splitlines() if ln.strip()]})
        ctx.note("nonexistent  rc=%d | %s" % (cli.returncode, (cli.stdout or "").strip()[:200]))
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

    return {"log": log, "assertions": rows, "target": target.name}


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
            problems.append("%s：期望 %s，实测 %s（after=%r）" % (cid, want, got, row.get("after")))
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
    # 只挂 gs32：夹具要借**该 target 安装树内**的 ECJ + JRE + SWT 片段（D1）。
    # 挂在没有这套工具链的 target 上会 SKIP —— 那时 `verify --all` 显示 SKIP，不是假 PASS。
    targets=("gs32",),
    description=("SWT 接受元素寻址的合成输入（六条断言：①③④ 能力、②定论记录、⑤⑥ 证伪）；"
                 "自带夹具启停，不连桥"),
    action=_action,
    expect=_expect,
    requires_bridge=False,
    # 夹具不是 IDE：没有「IDE 要被动过」需要守卫，屏幕守卫在这里没有对象。
    screen_guard=False,
    evidence=("fixture:window", "assertions:table", "fixture:log"),
)
