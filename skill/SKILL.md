---
name: eclipse-ctl
description: 从外部读取或控制 Eclipse 系 IDE（GS32_Studio / CCS 等）。当需要看 IDE 此刻的界面、部件、命令表，执行 IDE 自己的命令，开文件，对原生控件做元素寻址输入，或排查桥超时与模态框卡死时使用。关键词：eclipse-ctl、ctl run、GS32_Studio、CCS、工作台、模态框、sys.ping、ui.parts。
---

# eclipse-ctl —— 能力、纪律与自救

**一句话**：往 Eclipse 系 IDE 进程里热接一个薄桥，**一个门**（`python -m ctl run`，脚本进 stdin）
即可「读界面 / 发命令 / 合成输入」；写操作靠**回读差 + 弹框回报**判定；看不懂就**自己截图**看。

> 这份文档只做**约束**：什么时候用、脚本怎么写、超时后怎么办、不许做什么。
> 它**不是**命令表 —— 方法面用 `sys.help` 自省（桥会把每个方法的参数、是否写、幂等档位列出来）。

## 一、何时用

**用它的场合**：

- 要看一个 Eclipse 系 IDE **此刻**的界面状态：透视图、已打开的视图与编辑器、控件树、命令表。
- 要让 IDE 用**自己的命令框架**做事：开视图、切透视图、开文件、跑一条已注册命令。
- 要对**原生控件**做元素寻址输入：点按钮 / 按键 / 写文本。
- 桥没回话、超时、或界面疑似卡死 —— 按 §三 自救，**不要问用户**。

**先别用它的场合**（这些有更好的通道，别绕 GUI）：

- 编译 / 构建。
- 烧写 / 擦除 / 改芯片型号 / 选项字节。
- 改工程配置（`.cproject` / `.project` 这类文本）。
- 调试（断点 / 单步 / 变量）。

⇒ 一句话：**能走文件或产品自带 CLI 的，不绕 GUI**。`ctl` 补的是「没有别的通道」的那部分。

## 二、怎么写脚本

**唯一的门**：

```bash
python -m ctl run --target gs32 < job.py
```

- **连不上就自己起实例**（隔离的运行配置区，源安装树零触碰）。`--stop` 跑完收干净并逐项报告清洁判据。
- `--helpers <path>`：先把该文件 `exec` 进同一命名空间（放你的常用函数），再跑 stdin 的脚本。
- `--no-start`：没有活实例就直接失败退出（`rc=2`），不替你起。
- `--doctor`：先打一份就绪自检。**仅供参考** —— 它扫整个运行根，健康会话里也会报 FAIL，
  所以**它的退出码永远不参与判定**。
- `--retry <秒>`：连不上时按指数退避重试到该秒数（`0` = 立刻失败，默认）。
- `--no-shadow` / `--shadow-only-changes`：影子留档**默认开**，不需要就关。
- `--json`：机器可读输出。

**stdout 只放结果，诊断走 stderr**；脚本自己的 `print()` 独占 stdout。

脚本里**已预导入**这些名字（不要自己 `import ctl`）：

| 名字 | 作用 |
|---|---|
| `run(req)` | 发一行原始请求，回原始回话串 |
| `resp(req)` | 发一行 → `(状态行, 负载行列表, 原始串)` |
| `parts()` | 透视图 + 视图 id 列表 + 编辑器数 |
| `viewids(prefix="")` / `persp()` / `tree(depth)` / `commands(prefix="")` | 读面快捷方式 |
| `cmd(id, yes=False, **params)` | 走命令框架；**默认 dry-run**，真发要 `yes=True` |
| `open_file(path, yes=False)` / `close_view(id, yes=False)` | 打开文件 / 关视图；同样默认 dry-run |
| `act_click_button(text, case=None, title=None, yes=False)` | 元素寻址点按钮；默认 dry-run |
| `act_send_keys(key, title=None, class_="Edit", index=None, yes=False)` | 元素寻址按键（`WM_KEYDOWN/UP`）；默认 dry-run |
| `act_set_text(text, title=None, class_="Edit", index=None, yes=False)` | 元素寻址写文本（`WM_SETTEXT`）；默认 dry-run |
| `shadow(seq=None)` | 影子留档清单（**留档，不是判据**） |
| `log(msg)` | 往 stderr 打诊断 |
| `client` | 底层连接对象（其余名字都闭包在它上面） |

也可以在**自己的进程**里直接 `import ctl`（`Client` / `talk` / `resp` / `snap` / `discover_endpoint`）——
`ctl run` 只是同一个库的一扇门，不是第二套实现。

### 四条铁律

1. **`OK` ≠ 到位。** 写操作一律「**前回读 → 动作 → 后回读 → 取差**」，**不采信方法自己的返回值**。
2. **`OK` 还会撒谎。** 写方法的回话里若出现 `dialog=appeared "…"` 负载行，说明动作前后冒出了**新的可见窗**
   —— 那条命令**可能失败，也可能它本来就该弹框**。看到这一行就**别当成功**：先截图、处置掉、再回读一次。
   （实测：`viewId` 写错时回话是 `OK executed`，屏幕上却是 `Problem Occurred`，而回读差 `views 8→8`
   与「幂等成功」**长得一模一样** —— 只看回读差必然把失败读成成功。）
   **冒没冒弹框，只在回话的 `dialog=` 行里。**
3. **`ERR timeout` ≠ 未生效。** 桥用 `asyncExec`，超时只结束**等待**，排队的动作仍可能生效（见 §三）。
4. **看不懂就自己截图**，不许把观察外包给用户。

### 发写方法之前先自证身份

连上先发 `sys.env`：必须报 `protocol=1`，且 `bundle=` 的值是 `eclipse-ctl.bridge`。不符就**先别发写方法**。
**端口不要假设** —— 真实端口写在那个运行目录的 `endpoint.json` 里，`ctl run` 会自己找。

### 几条容易踩的

- **参数别硬编码**：跑某条命令前先 `cmd.query <id>` 取 `parameters[]`，再拼 `cmd(id, **params)`。
- **`ToolItem` / `MenuItem` / `CTabItem` / `TreeItem` 不是 `Control`**：`getChildren()` **拿不到**它们，
  要走 `getItems()`。工具栏按钮的语义常在 `getToolTipText()`（`getText()` 可能是空的）。
- **幂等三档**（决定能不能自动重试）：`true` 可重试；`false` 不可；**`per-command`** ——
  一个方法名承载任意命令、方法级无从保证（`cmd.run` / `cmd.runp` 就是这档）
  ⇒ **与 `unknown` 同等保守，一律不重试**（实测：开关型命令连点两次会**回到原状**）。

## 三、超时后怎么办

**不许**认定「没执行」—— 桥用 `asyncExec`，超时只结束等待，排队的动作**仍可能生效**。

1. **先枚举，拿到那个框的真标题**（不要先猜、不要问用户）：

   ```bash
   pwsh -NoProfile -File tools/win-enum.ps1 -Class "#32770"
   ```

   `#32770` 是原生对话框的窗口类。**顺序不能反** —— 弹框标题通常不含产品名，而按主窗名去截
   会拍到**一张没有框的图**，正好把你推向「一切正常」。

2. **再按那个标题截图**（多实例时用 `-ProcId` 认准自己那扇）：

   ```bash
   pwsh -NoProfile -File tools/shot-window-pw.ps1 -TitleLike "<上一步枚举到的标题>" -ProcId <pid> -Out "<运行目录>/hung.png"
   ```

3. **处置**：默认**只关窗**（等同点右上角 X）：

   ```bash
   pwsh -NoProfile -File tools/win-close.ps1 -TitleLike "<真标题>" -ProcId <pid>
   ```

   只有用例**显式声明**了按钮时才按下它（点按钮 = 替用户做不可逆决定）：

   ```bash
   pwsh -NoProfile -File tools/win-click-button.ps1 -TitleLike "<真标题>" -ProcId <pid> -Text "&No"
   ```

   > 同名按钮不止一个时**不要挑第一个**：`-Text` 命中 **0 或 >1 都 `exit 1`**（后者列出候选）。
   > 确实要选第 n 个，就**显式**给 `-Index <n>`（0 基；序位**只在同一会话内**稳定，跨运行会漂移）。

4. **探活 —— 但「ping 得通」证明不了「界面没卡」**：模态框在屏上时，**另一条连接**的
   `ui.parts` / `ui.tree` / `sys.ping` **全都正常返回**（SWT 模态框跑的是嵌套事件循环）；
   只有**发起那次请求自己**会 `ERR timeout`。
   ⇒ **别拿「`ui.*` 通不通」判断界面卡没卡**，直接**枚举/截图看那个框在不在**。
   ⇒ 反过来也要记住：**你发的那次请求超时了，不代表别的连接也干不了活**。

5. **再取一次回读差**，把差值归因到先前那次超时请求 —— **这一步不能省**，
   否则会把迟到的副作用算到下一次动作头上。

## 四、不许做什么

- **不要一次开一堆连接压桥**：全功能槽只有 **8** 个，而且**连着的空闲连接也算占槽**。
  满员后只有 `sys.ping` / `sys.env` / `sys.help` 还能答，其余回 `ERR busy`
  （**可重试**，别当成故障）。**用完就关**。
- **不要用坐标点击**（该路线**未证实**，且**决定不投入**）；要动手柄一律**元素寻址**。
- **不要把影子留档当判据**：它是留档。截图通道有「返回 TRUE 却画出整张全黑」的真实失败模式 ——
  **一个会撒谎的通道不能当断言**。判据只认**回读差**与回话里的 **`dialog=` 行**。
- **不要反复重试** `ERR disabled` / `ERR unhandled`（enablement / handler 问题，重试无用）。
  `ERR busy` 相反 —— **它就该重试**（可配退避）。
- **不要在 `--json` 场景把 stderr 混进 stdout**：诊断只走 stderr，stdout 只放结果。
- **不要用 `taskkill //F`**（参数会被 shell 吃掉）；用
  `pwsh -Command "Stop-Process -Id <pid> -Force"`。而且**要认准自己的 pid** ——
  按映像名杀会连带杀掉别人的实例。
- **不要假设合成输入在所有平台等价**。实测（2026-10-02，同一个夹具、同一条消息、同一套启动方式）：
  `BM_CLICK`（点按钮）与 `WM_SETTEXT`（写文本）**两侧都通**；但 `WM_KEYDOWN`（按键）
  在 **Eclipse 4.30 / SWT 3.124 通**、在 **Eclipse 4.23 / SWT 3.119 不通** ——
  换 JVM（11 ↔ 23）、补 `WM_SETFOCUS`、置前台**都不改变结果**。
  ⇒ **按键原语要按平台核对**，别当成到处都行。
- **不要在真 IDE 的**主窗**里找输入目标**：实测主窗的 `Button` 与 `Edit` **各为 0**；
  元素寻址的真实适用面是**对话框**（那里才有 `&Reset Perspective` / `&No` 这类真按钮）。
