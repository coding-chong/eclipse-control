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
| `NotHandledException` | `python -m ctl cmd <COMMAND_ID> --run-id <RUN_ID> --yes`（桥答 `ERR unhandled <bridge message>`） | part-scoped 命令无 handler（已知缺口，`boundaries.md` N9/U13）：改走命令框架的等价命令 | 记入缺口，不要反复重试同一 id |
| `Workspace Cannot Be Locked` | `pwsh -NoProfile -File tools/win-enum.ps1 -TitleLike "Workspace"`（弹出该对话框） | 同工作区已有实例：清场后重来（每个 run 用新工作区，`--ensure-clean`） | `python -m ctl uninstall --target <TARGET> --run-id <RUN_ID> --verify-clean`，换 `--run-id` 重装 |

---

## 2. 其它常见症状（同格式补充）

| 症状 | 怎么确认（命令） | 处置 | 如果不行下一步 |
|---|---|---|---|
| 端口被别的实例占用 / 连到旧桥 | `python -m ctl status --target <TARGET> --json` 比对 `bundle id` 与本次 `install` 回读 | 归属错实例：`python -m ctl install --target <TARGET> --run-id <RUN_ID> --port <N>` 换端口；跑前 `--ensure-clean` | 杀残留进程（`pwsh -Command "Stop-Process -Id <pid> -Force"`；**不要**用 `taskkill //F`，会被 brush 吃掉参数） |
| 截图抓到的是 IDE 工具栏而不是对话框 | 看图（`shots/` 下那张）而不是只看 rect | 用了已降级的 `CopyFromScreen` 通道：改用 `tools/shot-window-pw.ps1`（`PrintWindow` + DPI 感知） | 确认调用时先执行了 `SetProcessDPIAware`（该脚本已内置） |
| 桥版本漂移（副本里的常驻桥与源码不一致） | `python -m ctl shell --run-id <RUN_ID> -c "sys.env"` 读 `bundle=` / `id=` | 与期望不符先 `uninstall` 再 `install`（`design.md` §12 风险表「桥版本漂移」） | `python -m ctl upgrade --target <TARGET>` 走控制台 `update` 热更 |
| `sys.env` 缺少 `protocol=` / 协议版本不符 | `python -m ctl shell --run-id <RUN_ID> -c "sys.env"` | 客户端在握手时就会拒绝（`protocol.md` §9）；按报错里的期望版本重装桥 | 报缺陷：这是版本漂移，不是可继续的状态 |
| `ERR notfound no such case` 形态的用例名写错 | `python -m ctl verify --case <NAME> --target <TARGET>` | 用真实用例名；先 `python -m ctl verify --group read --target <TARGET>` 看组内有哪些 | 见 §7 的错误串一行 |
| `--json` 输出混入诊断、stdout 解析失败 | `python -m ctl parts --json 2>err.txt \| python -c "import json,sys; json.load(sys.stdin)"` | 这是 stdout/stderr 分工被破坏的缺陷：诊断必须只走 stderr（`design-project.md` §17.2） | 留原文上报（四件套） |
| 写命令「什么都没发生」（stdout 打印 `DRY-RUN <line>`，退出码 0） | `python -m ctl cmd --run-id <RUN_ID> org.eclipse.ui.views.showView viewId=com.gs.memory.view` | 没带 `--yes`：dry-run 只打印不发送（`design-project.md` §16.2）。补上 `--yes` 重发 | 补 `--yes` 后仍无变化 → 走回读差判定（`protocol.md` §4.2），别信返回值 |
| `verify --group <G>` 退出码 `2` | `python -m ctl verify --group <G> --target <TARGET>` | 该组**命中 0 条**用例即退出码 2（防「空组全绿」）；这是「前置/选择器有问题」，不是「测试失败」 | `python -m ctl verify --all --target <TARGET>` 看实际用例名 |
| `ctl act click-button --index` / `--path` 被拒绝 | `python -m ctl act click-button --title "ctl-fixture" --index 0` | `--index` / `--path` 参数存在但**显式拒绝**——当前只实现 `--text` 文本寻址（`boundaries.md` N11） | 改用 `python -m ctl act click-button --title "ctl-fixture" --text "&Go" --yes` |
| `recipes run <name>` 报用法错误、退出码 `1` | `python -m ctl recipes run view-and-shot` | 配方文件里还有**未替换的 `<...>` 占位符**：CLI **拒绝执行**（不会把字面量喂给 shell） | 先把 `<RUN_ID>` / `<RUN_ROOT>` 等替换成实际值，再跑 |
| 命令表导出条数异常（比实例里少） | `python -m ctl commands --json \| python -c "import json,sys; d=json.load(sys.stdin); print(d['total'], d['returned'], d['truncated'])"` | 见 `boundaries.md` U5（旧产物硬截断 300 条）与 U11（`getDefinedCommandIds()` 漏「有 handler 无声明」的 id） | 若 `returned != total`，按缺陷上报；不要拿半份导出当权威命令表 |

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

## 7. CLI 错误串 ↔ 本文件命中行（A12 判据）

规则见 `protocol.md` §11：CLI 的 stderr 一行形如 `ERR <code> <message>; retry: <命令>`，
且该串必须能在本文件 grep 命中**同一行**。下表左列即 **CLI 原样输出**，右列给出本文件里含该串的那一行。

| CLI 错误串（原样 grep 目标） | 本文件命中位置 |
|---|---|
| `ERR badrequest <detail>; retry: python -m ctl --help` | §7 本行（写法非法 / 未知 method 的参数形态见 `protocol.md` §2） |
| `ERR notfound no such case: <name>; retry: python -m ctl verify --case read.ping` | §2「`ERR notfound no such case` 形态的用例名写错」行 |
| `ERR notfound no such subcommand: <name>; retry: python -m ctl --help` | §7 本行（子命令拼写错；退出码 1，`design-obs-ux.md` §14.3 退出码语义） |
| `ERR notfound no such target: <name>; retry: python -m ctl targets list` | §7 本行（target 名不在册：`python -m ctl targets list` 列出全部） |
| `ERR notfound no endpoint for run '<run_id>' (<path>); retry: python -m ctl install --target <target> --run-id <run_id>` | §2「端口被别的实例占用 / 连到旧桥」行（无 `endpoint.json` = 该 run 没装过或已被清理） |
| `ERR timeout no response within 25000 ms; retry: python -m ctl shell --run-id <run_id> -c "sys.ping"` | §1 recv 超时行 |
| `ERR badrequest <detail>; retry: python -m ctl doctor --target <target>` | §7 本行（写方法未带 `--yes`；dry-run 规则见 `design-project.md` §16.2） |
| `ERR internal <detail>; retry: python -m ctl doctor --target <target>` | §3 `internal` 行 |
| `ERR disabled <bridge message>; retry: python -m ctl doctor --target <target>` | §1 `NotEnabledException` 行 |
| `ERR unhandled <bridge message>; retry: python -m ctl commands find --text "Select All"` | §1 `NotHandledException` 行 |
| `ERR noWorkbench <bridge message>; retry: python -m ctl status --target <target>` | §1 `Workbench has not been created yet` 行 |
| `ERR busy <bridge message>; retry: python -m ctl status --target <target>` | §3 `busy` 行 |

> 桥侧码（`disabled` / `unhandled` / `noWorkbench` / `busy`）的 `<bridge message>` 由桥原样给出，
> 只有 `; retry: <命令>` 是 CLI 追加的（`protocol.md` §11）。
> **退出码**：`0` 成功 / `1` 失败（含用法与查找错误）/ `2` 前置未就绪（`doctor` 有 FAIL 即 2）
> —— `design-obs-ux.md` §14.3。
