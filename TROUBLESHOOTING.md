# 故障排查（症状 → 处置）

**读者**：使用者 / AI 会话 / CI 排障。
**契约出处**：`design-obs-ux.md` §14.5（错误 → 处置映射表，本文件 §1 逐行对齐）、§13.2（观测规则）、
`design.md` §5（模态框处置策略）、`protocol.md` §3/§4（错误码与超时语义）、`design-project.md` §17.3（错误信息可操作）。

**两条纪律**

1. **先自己看，再动手**：任何「超时 / 无响应 / 与预期不符」，**先截图存档**，从图上读出标题与按钮文字再决定动作；
   禁止把观察责任推给用户（`design-obs-ux.md` §13.2 规则 5）。
2. **`ERR timeout` 不是「未生效」**：写方法超时后**必须再取一次回读差**才能判定（`protocol.md` §4.2）。

**变量**：`<RUN_ID>` 由 `install --run-id` 指定或按 `<target>-<yyyymmdd-HHMM>` 自动生成；
`<RUN_ROOT>` 内置默认 `<user.home>/.eclipse-ctl/runs`；截图归档目录是 `<RUN_ROOT>/<RUN_ID>/shots/`；
`<TARGET>` 取 `gs32` / `ccs12`；`<TARGET_INSTALL>` 是该 target 的 IDE 安装根
（默认配置见 `design-obs-ux.md` §14.6：`gs32` → `D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2`，
`ccs12` → `D:/ti/ccs1281/ccs/eclipse`）。

---

## 1. `design-obs-ux.md` §14.5 症状表（逐行对齐，全 7 行）

| 症状 | 怎么确认（命令） | 处置 | 如果不行下一步 |
|---|---|---|---|
| `connection refused` | `python -m ctl status --target <TARGET>`（报 bridge not listening / 无 endpoint） | 桥没起：进控制台 `ss` 看 installed/started，看启动 stamp（`<RUN_ROOT>/<RUN_ID>/console.log`） | `python -m ctl doctor --target <TARGET>`；仍不行 `python -m ctl install --target <TARGET> --run-id <RUN_ID>` 重装 |
| recv 超时 | `python -m ctl shell --run-id <RUN_ID> -c "sys.ping"`（客户端 25 s 后超时） | 桥起了但 accept 停摆（**模态框**）：**先截图** `pwsh -NoProfile -File tools/shot-window-pw.ps1 -TitleLike "GS32_Studio" -Out "<RUN_ROOT>/<RUN_ID>/shots/hung.png"` → 读图上按钮文字 → 默认 `pwsh -NoProfile -File tools/win-close.ps1 -TitleLike "Reset Perspective"` 关窗（用例显式声明时才用 `win-click-button.ps1` 按下指定按钮）→ 探活 | 探活仍不通：`pwsh -NoProfile -File tools/win-enum.ps1 -TitleLike ""` 找残留 `#32770`；再不通按硬故障上报（四件套见 §4） |
| `Workbench has not been created yet` | `python -m ctl shell --run-id <RUN_ID> -c "ui.parts"`（桥答 `ERR noWorkbench <bridge message>`） | 工作台没起来（工作区被占）：清场或换工作区，重新 `install` | `python -m ctl uninstall --target <TARGET> --run-id <RUN_ID> --verify-clean` 后重装；仍不行查 `Workspace Cannot Be Locked` 那一行 |
| `oversized` | 用 OCU 截图时 `get_app_state(app="GS32", include_image=true)` 报 `Windows runtime returned oversized output` | 截图超 1 MiB：改用单窗截取 `pwsh -NoProfile -File tools/shot-window-pw.ps1 -TitleLike "GS32_Studio" -Out "<RUN_ROOT>/<RUN_ID>/shots/win.png"`（`PrintWindow` 不受窗口大小与遮挡影响） | 仍是空图：确认窗口可见（后台目标只尝试 `PrintWindow`，可能返回空白） |
| `NotEnabledException` | `python -m ctl cmd <COMMAND_ID> --run-id <RUN_ID> --yes`（桥答 `ERR disabled <bridge message>`） | 命令被 disable：建前置态（开编辑器 / 选 selection）后再发；做不到就把该用例标 skip | `python -m ctl commands find --text "<按钮或菜单文字>" --json` 换成真正 enabled 的 id |
| `NotHandledException` | `python -m ctl cmd <COMMAND_ID> --run-id <RUN_ID> --yes`（桥答 `ERR unhandled <bridge message>`） | **当前活动部件**没有这条命令的 handler（`boundaries.md` N9 / U13，2026-10-05 修正 —— 不是「已知缺口」，也不是 lookup 上下文问题）。part-scoped 命令（如 `org.eclipse.ui.edit.selectAll`）先让目标部件成为活动部件（如 `python -m ctl open <abs file> --yes`）再发一次 | 仍 `unhandled` 就记入缺口，不要反复重试同一 id；注意 `ERR disabled` 是**另一档**（handler 找到但 `canExecute=false`），处置是补前置态 |
| `Workspace Cannot Be Locked` | `pwsh -NoProfile -File tools/win-enum.ps1 -TitleLike "Workspace"`（弹出该对话框） | 同工作区已有实例：清场后重来（每个 run 用新工作区，`--ensure-clean`） | `python -m ctl uninstall --target <TARGET> --run-id <RUN_ID> --verify-clean`，换 `--run-id` 重装 |

---

## 2. 其它常见症状（同格式补充）

| 症状 | 怎么确认（命令） | 处置 | 如果不行下一步 |
|---|---|---|---|
| 端口被别的实例占用 / 连到旧桥 | `python -m ctl status --target <TARGET> --json` 比对 `bundle id` 与本次 `install` 回读 | 归属错实例：`python -m ctl install --target <TARGET> --run-id <RUN_ID> --port <N>` 换端口；跑前 `--ensure-clean` | 杀残留进程（`pwsh -Command "Stop-Process -Id <pid> -Force"`；**不要**用 `taskkill //F`，会被 brush 吃掉参数） |
| 截图抓到的是 IDE 工具栏而不是对话框 | 看图（`shots/` 下那张）而不是只看 rect | 用了已降级的 `CopyFromScreen` 通道：改用 `tools/shot-window-pw.ps1`（`PrintWindow` + DPI 感知） | 确认调用时先执行了 `SetProcessDPIAware`（该脚本已内置） |
| 桥版本漂移（副本里的常驻桥与源码不一致） | `python -m ctl shell --run-id <RUN_ID> -c "sys.env"` 读 `bundle=` / `id=` | 与期望不符先 `uninstall` 再 `install`（`design.md` §12 风险表「桥版本漂移」） | `python -m ctl upgrade --target <TARGET>` = **重编 + 停旧实例 + 重装**（`ctl/__main__.py:_cmd_upgrade`）。**没有对外热更新通道** —— 控制台 `update` 命令不存在，`upgrade` 自己会往 stderr 打 `hot console update is not reachable externally` |
| `sys.env` 缺少 `protocol=` / 协议版本不符 | `python -m ctl shell --run-id <RUN_ID> -c "sys.env"` | 客户端在握手时就会拒绝（`protocol.md` §9）；按报错里的期望版本重装桥 | 报缺陷：这是版本漂移，不是可继续的状态 |
| `ERR notfound no such case` 形态的用例名写错 | `python -m ctl verify --case <NAME> --target <TARGET>` | 用真实用例名；先 `python -m ctl verify --group read --target <TARGET>` 看组内有哪些 | 见 §7 的错误串一行 |
| `--json` 输出混入诊断、stdout 解析失败 | `python -m ctl parts --json 2>err.txt \| python -c "import json,sys; json.load(sys.stdin)"` | 这是 stdout/stderr 分工被破坏的缺陷：诊断必须只走 stderr（`design-project.md` §17.2） | 留原文上报（四件套） |
| 写命令「什么都没发生」（stdout 打印 `DRY-RUN <line>`，退出码 0） | `python -m ctl cmd --run-id <RUN_ID> org.eclipse.ui.views.showView viewId=com.gs.memory.view` | 没带 `--yes`：dry-run 只打印不发送（`design-project.md` §16.2）。补上 `--yes` 重发 | 补 `--yes` 后仍无变化 → 走回读差判定（`protocol.md` §4.2），别信返回值 |
| `verify --group <G>` 退出码 `2` | `python -m ctl verify --group <G> --target <TARGET>` | 该组**命中 0 条**用例即退出码 2（防「空组全绿」）；这是「前置/选择器有问题」，不是「测试失败」 | `python -m ctl verify --all --target <TARGET>` 看实际用例名 |
| 元素寻址歧义 / 找不到控件（`ERR badrequest ambiguous: …` 或 `ERR notfound no visible Button matching …`） | 脚本里 `act_click_button("&OK", title="Reset Perspective", yes=True)`，喂给 `python -m ctl run --target <TARGET>` | 寻址必须**唯一**：先把标题收窄到那扇窗，再把文字收窄到那个控件。**类名**寻址那一族（`act_send_keys` / `act_set_text`）多命中时用 `index=<0 基序位>` 显式指定（序位只在同一会话内稳定，所以永不自动挑）。`--path`（SWT 式下标路径）**已裁决不做**，并随 `act` 子命令一起消失 —— 参数都不存在了（`boundaries.md` N11） | 先枚举看真实标签：`pwsh -NoProfile -File tools/win-click-button.ps1 -ProcId <pid> -TitleLike "<标题片段>" -ListOnly` |
| `recipes run <name>` 报用法错误、退出码 `1` | `python -m ctl recipes run view-and-shot` | 配方文件里还有**未替换的 `<...>` 占位符**：CLI **拒绝执行**（不会把字面量喂给 shell） | 先把 `<RUN_ID>` / `<RUN_ROOT>` 等替换成实际值，再跑 |
| 命令表导出条数异常（比实例里少） | `python -m ctl commands export --json \| python -c "import json,sys; d=json.load(sys.stdin); print(d['total'], d['returned'], d['truncated'])"` | 见 `boundaries.md` §A11（旧产物硬截断 300 条，2026-10-01 已去掉）与 §A9b（`getDefinedCommandIds()` 漏「有 handler 无声明」的 id） | 若 `returned != total`，按缺陷上报；不要拿半份导出当权威命令表 |

---

## 3. 协议错误码 → 处置（8 个码，闭集）

| code | 你看到的 | 处置 |
|---|---|---|
| `badrequest` | `ERR badrequest <bridge message>` | 请求非法：检查 method 拼写与参数形态（`protocol.md` §2） |
| `notfound` | `ERR notfound <bridge message>` | 目标不存在：换 id / 换路径；用 `python -m ctl commands find --text "<文字>" --json` 反查真实 id |
| `disabled` | `ERR disabled <bridge message>` | 同 §1 `NotEnabledException` 行 |
| `unhandled` | `ERR unhandled <bridge message>` | 同 §1 `NotHandledException` 行 |
| `timeout` | `ERR timeout <bridge message>` | 同 §1 recv 超时行 + **回读差复查**（`protocol.md` §4.2） |
| `noWorkbench` | `ERR noWorkbench <bridge message>` | 同 §1 `Workbench has not been created yet` 行 |
| `internal` | `ERR internal <异常类名>: <message>` | 未映射异常：可重试**一次**（仅幂等方法）；仍失败按缺陷上报（带原始异常类名） |
| `busy` | `ERR busy <bridge message>` | 连接数达上限：**指数退避后重试**（不得紧循环轰炸） |

---

## 4. 缺陷上报四件套（缺一件不算）

环境指纹（`python -m ctl doctor --target <TARGET>` 的完整输出）+ 原始回话片段（含 `END` 与耗时）+
截图（`shots/` 下那张，且说明从图上读到了什么）+ 复跑命令（一条可直接执行的完整命令）。
出处：`design-project.md` §17.9。

---

## 5. 五分钟定位流程（照抄）

```bash
python -m ctl doctor --target <TARGET>
python -m ctl status --target <TARGET> --json
python -m ctl shell --run-id <RUN_ID> -c "sys.env"
python -m ctl shell --run-id <RUN_ID> -c "sys.ping"
pwsh -NoProfile -File tools/shot-window-pw.ps1 -TitleLike "GS32_Studio" -Out "<RUN_ROOT>/<RUN_ID>/shots/diag.png"
```

前三条定位「机器/实例/版本」，第四条区分「僵死 vs 可运维」（卡死期间 `sys.ping` 仍通即为可运维），
第五条把界面状态留证。

---

## 6. 已知会踩的坑（症状 → 规避）

| 症状 | 规避 |
|---|---|
| `InvalidPathException: Illegal char <:>`（编译/起进程时） | Windows 的 `-cp` 分隔符是 **`;`**，不是 `:` |
| `NoClassDefFoundError: LiveBridge$1` | 打包时把 `out/` 下**全部** `.class` 打进去，不只主类 |
| `taskkill //F` 报无效参数 | 用 `pwsh -Command "Stop-Process -Id <pid> -Force"` |
| OCU 报 `The requested app was not found` | 应用名先用 `list_apps` 取（本机 GS32 的名字是 **`GS32`**，不是 `GS32.exe`） |
| 子窗类名读取报 `CS1503` | `GetClassNameW(hwnd, sb, len)` 第一个参数是 **hwnd** |
| 高 DPI 下截图错位 | 先 `SetProcessDPIAware()`，再 `PrintWindow`（`tools/shot-window-pw.ps1` 已内置） |

---

## 7. CLI / 库错误串 ↔ 本文件命中行（A12 判据）

规则见 `protocol.md` §11：CLI 把失败写到 stderr，形如 `ERR <code> <message>; retry: <命令>`。

**判据怎么才算成立**：真实输出里的 id / 路径 / 耗时 / 窗口号都是**可变**的，整行 grep 不可能命中。
所以 A12 的判据落在**消息里那段稳定的字面量**上 —— 下表左列即那个字面量，
它必须能在**本文件**里**原样 grep 命中**（命中处即本行）。占位符只出现在中列与右列的说明里。

**三种形态**（中列标注；不要把后两种当 `ERR` 行）：

| 形态 | 出处 | 退出码 |
|---|---|---|
| `ERR <code> <message>; retry: …` | `CtlError.line()`（`ctl/errors.py`）—— 绝大多数 | `1`；`PrereqNotReady` 是 `2` |
| doctor 报告行（`[FAIL] <detail>; retry: …`） | `doctor` 的检查明细（`_check()`），不是 stderr 那一行 | 有任一 FAIL ⇒ `2` |
| `warning: …; retry: …` | 直接 `print(…, file=sys.stderr)` | **不变**（`0`） |

> ⚠️ `PrereqNotReady`（前置未就绪）的**码是 `internal` 但退出码是 `2`** —— 与「真正的内部异常」同码不同退。
> 判「能不能继续」要看**退出码**，不要只看码（`design-obs-ux.md` §14.3 的退出码语义）。

| stderr / 报告里的可 grep 字面量 | 形态 · 码 · 退出码 | 处置与出处 |
|---|---|---|
| `bridge did not answer on port` | `ERR` + 具体码 / **1** | 桥起了但不在超时内回话：**先按 §1 recv 超时行**处置（多半是模态框）。<br>`ctl/lifecycle.py:708` |
| `cannot reach bridge on` | `ERR` + 具体码 / **1** | 连不上端口：实例没起、端口变了、或被杀。`status --json` 看 endpoint；见 §2「端口被别的实例占用」。<br>`ctl/client.py:244` |
| `config file unreadable` | `ERR` + 具体码 / **1** | `~/.eclipse-ctl/config.json` 读不了（坏 JSON/权限）。修好或删掉重建。<br>`ctl/targets.py:359` |
| `console not started` | `ERR` + 具体码 / **1** | 控制台没起：装桥时没带 `-console`，或实例已死。重装。<br>`ctl/console.py:165` |
| `dangerous command refused` | `ERR` + 具体码 / **1** | Gogo 危险命令（`init/close/shutdown/exit/gc`）被拒。确需执行再加 `--allow-dangerous`。<br>`ctl/__main__.py:1240` |
| `failed (rc=` | `ERR` + 具体码 / **1** | 配方某个块执行失败。按 rc 与上一条输出定位那一步。<br>`ctl/__main__.py:1093` |
| `not present after install` | `ERR` + 具体码 / **1** | 装完没看到 bundle。看控制台 `ss` 与 `console.log`。<br>`ctl/lifecycle.py:477` |
| `protocol mismatch: bridge reports` | `ERR` + 具体码 / **1** | 桥自报版本与客户端期望不符。重装/重编桥（`protocol.md` §9 会拒绝不匹配）。<br>`ctl/lifecycle.py:726` |
| `recipe unreadable` | `ERR` + 具体码 / **1** | 配方文件读不了。`ctl recipes list` 核对路径。<br>`ctl/__main__.py:1052` |
| `workbench did not become ready within %.0f s (last` | `ERR` + 具体码 / **1** | 工作台在超时内没就绪（工作区被占）。见 §1「`Workspace Cannot Be Locked`」行。<br>`ctl/lifecycle.py:714` |
| `-- replace it before running` | `ERR badrequest` | 配方块里还有未替换的 `<...>` 占位符：CLI **拒绝执行**（不把字面量喂给 shell）。先替换再跑。<br>`ctl/__main__.py:1085` |
| `index 9 out of range (3 match(es))` | `ERR badrequest` / **1** | `index=` 超出该类名的可见匹配数（`-ListOnly` 先自检，**什么都没点**）。先看候选数再给序位；不给序位而命中 >1 会得到另一条 `ambiguous: N visible children of class …`。<br>`ctl/run.py:348`（歧义侧 `:345`） |
| `--json requires -c` | `ERR badrequest` | `ctl shell --json` 必须配 `-c` 单发；交互模式不能出 JSON。<br>`ctl/__main__.py:1266` |
| `--open needs a frame: use --seq N --open, or --open N` | `ERR badrequest` | `--open` 没给帧号。用 `--seq N --open` 或 `--open N`。<br>`ctl/__main__.py:1424` |
| `--promote and --prune are different actions` | `ERR badrequest` | `--promote` 与 `--prune` 是两种动作，不能同时给。<br>`ctl/__main__.py:1372` |
| `--seq and --promote are different actions` | `ERR badrequest` | `--seq` 与 `--promote` 是两种动作，不能同时给。<br>`ctl/__main__.py:1370` |
| `bridge build entry missing` | `ERR internal` / **2** | `bridge/build.py` 里缺构建入口，源码不完整。<br>`ctl/__main__.py:1507` |
| `bridge jar is stale, none declares` | `ERR internal` / **2** | `dist/` 里的 jar 不是本版编的。`ctl build --target <t>` 重编。<br>`ctl/lifecycle.py:385` |
| `bridge not answering for run` | `ERR internal` / **2** | 该 run 没有可用的桥（没装过/已停）。`install` 或换 `--run-id`。<br>`ctl/verify/runner.py:181` |
| `bridge source missing` | `ERR internal` / **2** | 桥源码树缺失。确认 `bridge/src` 在仓里。<br>`ctl/lifecycle.py:395` |
| `dangerous console command refused` | `ERR disabled` / **1** | 同上行（控制台路径）。<br>`ctl/console.py:65` |
| `endpoint.json for run '` | `ERR notfound` / **1** | `endpoint.json` 里没有 `port` 字段（文件损坏）。重装该 run。<br>`ctl/client.py:88` |
| `endpoint.json unreadable for run '` | `ERR notfound` / **1** | `endpoint.json` 读不了。删掉该 run 重装。<br>`ctl/client.py:84` |
| `ERR notfound no shadow record with seq=` | `ERR notfound` / **1** | 该 run 的影子里没有这个 `seq`。先 `ctl shadow --run-id <id>` 看清单。<br>`ctl/__main__.py:1377` |
| `ERR notfound no such subcommand` | `ERR notfound` / **1** | 子命令拼写错。`design-obs-ux.md` §14.3 是命令面的准绳。<br>`ctl/__main__.py:1927` |
| `has no frame on disk (pruned or never kept` | `ERR notfound` / **1** | 清单里有这条 `seq` 但帧文件已被裁掉（promoted 不会被裁，所以多半是普通帧）。<br>`ctl/__main__.py:1417` |
| `IDE process is not accepting console input (rc=` | `ERR internal` / **1** | IDE 不接收控制台输入（进程已死/未起 `-console`）。看 `console.log`，必要时重装。<br>`ctl/console.py:196` |
| `is already held by another run (live listener pid` | `ERR internal` / **2** | 目标端口上已有**别的 run** 的活桥。修前会与它**共用端口**（连到旧桥 ⇒ 测量作废），`--stop` 还会**按端口收尸**误杀旁人的实例。**换 `--port <free port>`**，或 `--ensure-clean` 显式清掉它（注意：那会**停掉**那个实例）。<br>`ctl/lifecycle.py:669` |
| `is missing (source present` | `ERR internal` / **2** | 桥不可构建（源码在但构件缺）。看 `doctor` 的 ECJ 一行。<br>`ctl/lifecycle.py:392` |
| `is not a bridge method (Gogo console forwarding is not wired in this round` | `ERR badrequest` / **1** | `ctl shell` 只转桥方法；Gogo 控制台转发本轮未接。<br>`ctl/__main__.py:1244` |
| `launcher not found for target` | `ERR internal` / **2** | 找不到该 target 的启动器（`GS32.exe`/`ccstudio.exe`）。核对 `source_dir`。<br>`ctl/lifecycle.py:585` |
| `missing tool` | `ERR internal` / **2** | `tools/` 下的窗口脚本缺失 —— 仓库不完整。<br>`ctl/run.py:254`（`act_click_button`）/ `:300`（`act_send_keys` / `act_set_text`） |
| `name different frames` | `ERR badrequest` | `--open` 与 `--seq` 指的不是同一帧。<br>`ctl/__main__.py:1401` |
| `no bash found to run recipe` | `ERR internal` / **2** | 跑配方需要 bash，本机没找到。<br>`ctl/__main__.py:1080` |
| `no bridge jar built yet` | `ERR internal` / **2** | 还没编过桥。`ctl build --target <t>`。<br>`ctl/lifecycle.py:389` |
| `no visible Button matching` | `ERR notfound` / **1** | 该窗口里没有含这段文字的可见 Button。先 `win-click-button.ps1 -ListOnly` 看真实标签。<br>`ctl/run.py:275` |
| `no cases matched (case=` | `ERR internal` / **2** | 选择器没命中任何用例（防「空组全绿」）。`verify --group read` 看组内有哪些。<br>`ctl/__main__.py:1456` |
| `no command whose name contains` | `ERR notfound` / **1** | 命令表里没有名字含该文字的命令。`ctl commands --json` 看全量。<br>`ctl/__main__.py:998` |
| `no endpoint for run '` | `ERR notfound` / **1** | 该 run 没有 `endpoint.json` = 没装过或已被清。见 §2「端口被别的实例占用」行。<br>`ctl/client.py:77` |
| `no run` | `ERR notfound` / **1** | 显式 `--run-id` 指到不存在的 run（**拼写错**）。`ctl shadow --run-id <id>` 与 `install` 都受此检查。<br>`ctl/__main__.py:1318` |
| `no run for target` | `ERR notfound` / **1** | 该 target 下没有 run。**新会话撞的第一条**：先 `ctl install --target <t>`。<br>`ctl/__main__.py:444` |
| `no run-id given, cannot locate endpoint.json` | `ERR notfound` / **1** | 既没给 `--run-id` 也没有可用 endpoint。先 `install`。<br>`ctl/client.py:73` |
| `no such case` | `ERR notfound` / **1** | 用例名写错。见 §2「`ERR notfound no such case` 形态的用例名写错」行。<br>`ctl/verify/runner.py:264` |
| `no such recipe` | `ERR notfound` / **1** | 没有这个配方。`ctl recipes list` 看五个内置配方。<br>`ctl/__main__.py:1076` |
| `no such target` | `ERR notfound` / **1** | target 名不在册。`ctl targets list` 列出 `gs32` / `ccs12`。<br>`ctl/targets.py:493` |
| `no visible window matching` | `ERR notfound` / **1** | 没有匹配该标题的可见窗口。标题可能含零宽字符，改用更短片段。<br>`ctl/run.py:271`（`act_click_button`）/ `:334`（`act_send_keys` / `act_set_text`） |
| `parameter must be key=value, got` | `ERR badrequest` | `ctl cmd` 的参数必须 `key=value`。<br>`ctl/__main__.py:1197` |
| `pwsh not found` | `ERR internal` / **2** | 本机没有 pwsh。元素寻址输入与截图都依赖它。<br>`ctl/run.py:257` / `:303`；截图侧 `ctl/screen.py` |
| `addressing must be unique` | `ERR badrequest` / **1** | 寻址命中了多个控件（必须唯一）：标签侧报 `ambiguous: N Buttons match …`，类名侧报 `ambiguous: N visible children of class …`。改用更精确的文字，或（类名侧）给 `index=`。<br>`ctl/run.py:277` / `:345` |
| `unknown commands action` | `ERR badrequest` / **1** | `commands` 的子动作拼错。<br>`ctl/__main__.py:1006` |
| `unknown recipes action` | `ERR badrequest` / **1** | `recipes` 的子动作拼错。<br>`ctl/__main__.py:1096` |
| `unknown targets action` | `ERR badrequest` / **1** | `targets` 的子动作拼错。<br>`ctl/__main__.py:831` |
| `verify needs --case, --group or --all` | `ERR badrequest` / **1** | `verify` 必须给 `--case` / `--group` / `--all` 之一。<br>`ctl/__main__.py:1449` |
| `cannot write under` | doctor 报告行 | `run_root` 不可写：换 `--config` 指到可写目录。doctor 会因此判 FAIL ⇒ **退出码 2**。<br>`ctl/__main__.py:605` |
| `in use by foreign pid(s` | doctor 报告行 | 端口被**外来进程**占用：`doctor --ensure-clean` 清场，或换端口。doctor 判 FAIL ⇒ **退出码 2**。<br>`ctl/__main__.py:557` |
| `protocol` | doctor 报告行 | 桥协议版本与客户端不符：按 §2「`sys.env` 缺 `protocol=`」处置。doctor 判 FAIL ⇒ **退出码 2**。<br>`ctl/__main__.py:619` |
| `warning: bridge reported total=` | **警告**（rc 不变） | 命令表被截断（`total > returned`）。见 §2「命令表导出条数异常」行；不要拿半份导出当权威。<br>`ctl/__main__.py:944` |
| *(无字面量，见右列)* | `badrequest` / `notfound` / **1** | **兜底模板**：argparse 用法错误统一走这里（`invalid choice` ⇒ `notfound`，其余 ⇒ `badrequest`）。<br>`ctl/__main__.py:116` |
| `invalid run-id` | `ERR badrequest` / **1** | run-id 形状不合法（含路径分隔符 / 前导点 / 空格 / 空串）。用**字母数字开头**、只含 `[A-Za-z0-9._-]` 的**单个路径分量**；或省掉 `--run-id` 交给 `make_run_id` 生成。<br>`ctl/lifecycle.py:107` |
| `ERR badrequest run takes a single --target, got` | 裸 stderr 行 / **1** | `ctl run` 只吃**一个** `--target`（它跑的是单实例里的脚本）。`--config` 里配了多 target 不影响这条路，但显式给多个就会拒。<br>`ctl/run.py:568` |
| `ERR notfound no such target` | 裸 stderr 行 / **2** | `ctl run` 的 `--target` 名不在册。`ctl targets list` 列出 `gs32` / `ccs12`。<br>`ctl/run.py:573` |
| `ERR no instance` | 裸 stderr 行 / **2** | `--no-start` 下该 run 没有活桥（`ctl run` 走库路径，起实例要靠 `install`）。去掉 `--no-start`，或先 `install` 再跑。<br>`ctl/run.py:584` |
| `retry: python -m ctl run --target gs32 < script.py` | 重试后缀（**非独立行**） | `ctl run` 一族错误统一挂的"下一步"（重跑那条脚本）。它是**后缀模板**，出现在约 18 处：门面 3 条 + `act_*` 库原语的寻址/工具缺失各条。<br>`ctl/run.py:47` |
| `retry: python -m ctl build --target` | 重试后缀（**非独立行**） | 桥 jar 缺失 / 过期 / 源码不全时统一挂的"下一步"：`ctl build --target <t>`。用在 `stale jar` / `no jar` / `source missing` 三条正文后面。<br>`ctl/lifecycle.py:364`（用在 `:405` / `:408` / `:412`） |

> **兜底说明**：`ctl/__main__.py` 里的 argparse `error()` 覆写是所有用法错误的统一出口，
> 它按 `invalid choice` 分派码（子命令拼错 ⇒ `notfound`，其余 ⇒ `badrequest`）。
>
> **本表的覆盖度由脚本判定，不由这句话判定**（判据会漂，故不写死数字）。复跑：
> `python <工作区>/.trellis/tasks/archive/2026-10/10-01-eclipse-ctl-dialog-rc-and-troubleshooting/research/check-error-coverage.py`
> （`--repo D:/gitclone/eclipse-ctl`；判据 = 把模板按 `%s/%d/%r` 切段，取 **≥6 字符**的片段，
> 只要有**一段**能在本表原样 grep 命中即算覆盖；**脚本随该任务已归档**，路径见上）。
> **实测（2026-10-05）**：`templates=58 checked=57 exempt=1 missing=0` ⇒ **`coverage: PASS`**。
> ⚠️ **判据自身的盲区（实测踩到）**：它按**子串**命中 —— 正文里（哪怕是在描述缺口时）
> **提到**某个候选串，就会把对应模板算成"已覆盖"。所以**别在本段里罗列那些串**，
> 也别把"提到了"当成"写好了处置行"。
>
> **缺口史（保留，供追溯）**：`2026-10-01` 交付时 **59/59** 全绿；`2026-10-04` 拆掉 `act` 子命令后
> 模板集缩到 **58**（`act` 一族随之消失），其中 **6 条**未被覆盖，当时**如实记成 FAIL** 并留下"补表"指令；
> `2026-10-05` 补上这 6 条（`ctl run` 门面 3 条 + 两条"重试后缀" + run-id 校验 + 桥构建重试提示），回到 **0 缺失**。
> ⇒ **本表会随源码漂**：加/改错误串后跑一次上面的脚本。
> 把它接进 `preflight`（自动防漂）是一个**改对外契约的独立决定，尚未拍板** —— 脚本已写好，
> 提升成本约 25 行 + 两处契约文字。

**退出码**：`0` 成功 / `1` 失败（含用法与查找错误）/ `2` 前置未就绪
—— `design-obs-ux.md` §14.3。注意 **`rc=0` 不代表没有弹框**：写命令的弹框只在回话的 `dialog=` 负载行里，
桥只交事实、判断留给调用方（`protocol.md` §4.3）。
