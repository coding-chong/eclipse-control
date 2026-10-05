---
name: eclipse-ctl
description: 从外部读取或控制 Eclipse 系 IDE（GS32_Studio / CCS 等）。当需要看 IDE 此刻的界面、部件、命令表，执行 IDE 自己的命令，开文件，对原生控件做元素寻址输入，截图留证，或排查桥超时与模态框卡死时使用。关键词：eclipse-ctl、ctl run、GS32_Studio、CCS、工作台、模态框、sys.ping、ui.parts、截图、see、windows。
---

# eclipse-ctl —— 能力、纪律与自救

**一句话**：往 Eclipse 系 IDE 进程里热接一个薄桥，**一个门**（`python -m ctl run`，脚本进 stdin）
即可「读界面 / 发命令 / 合成输入」；写操作靠**回读差 + 弹框回报**判定；看不懂就**自己截图**看。

> 这份文档只做**约束**：什么时候用、脚本怎么写、超时后怎么办、不许做什么。
> 它**不是**命令表 —— 方法面用 `sys.help` 自省（桥会把每个方法的参数、是否写、幂等档位列出来）。
> **深度在 [`references/`](references/)**，按下表读；正文只留契约。

### 索引：什么时候读哪一份

| 你要做的事 | 读 |
|---|---|
| 桥超时 / 界面疑似卡死 / 换一台机器（内置 target 的安装根不是你的） | [`references/recovery.md`](references/recovery.md) |
| 点按钮 / 按键 / 写文本（元素寻址输入） | [`references/input.md`](references/input.md) |
| 截图 / 窗口枚举 / `shots` 与 `shadow` 的区别 | [`references/observation.md`](references/observation.md) |

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

**stdout 只放结果，诊断走 stderr**；脚本自己的 `print` 独占 stdout。

脚本里**已预导入**这些名字（不要自己 `import ctl`）：

| 名字 | 作用 |
|---|---|
| `run(req)` | 发一行原始请求，回原始回话串 |
| `resp(req)` | 发一行 → `(状态行, 负载行列表, 原始串)` |
| `parts()` | 透视图 + 视图 id 列表 + 编辑器数 |
| `viewids(prefix="")` / `persp()` / `tree(depth, shell=None)` / `commands(prefix="")` | 读面快捷方式 |
| `cmd(id, yes=False, **params)` | 走命令框架；**默认 dry-run**，真发要 `yes=True` |
| `open_file(path, yes=False)` / `close_view(id, yes=False)` | 打开文件 / 关视图；同样默认 dry-run |
| `act_click_button(text, case=None, title=None, yes=False)` | 元素寻址点按钮；默认 dry-run |
| `act_send_keys(key, title=None, class_="Edit", index=None, yes=False)` | 元素寻址按键（`WM_KEYDOWN/UP`）；默认 dry-run |
| `act_set_text(text, title=None, class_="Edit", index=None, yes=False)` | 元素寻址写文本（`WM_SETTEXT`）；默认 dry-run |
| `see(name=None, title=None)` | 拍一帧**证据**图（`shots/`，走 `shot-window-pw.ps1`）；回「真路径 + 窗口行」。只读 |
| `windows()` | 本 run 的可见顶层窗 `{hwnd: (pid, class, title)}`。只读 |
| `close_window(title, cls="", yes=False)` | 按标题关窗（`WM_CLOSE`）；默认 dry-run |
| `shadow(seq=None)` | 影子留档清单（**留档，不是判据**） |
| `log(msg)` | 往 stderr 打诊断 |
| `client` | 底层连接对象（其余名字都闭包在它上面） |

> **排版约定（也是闸门的判据）**：skill 里带括号的反引号名 = 上表的名字；
> 桥方法（`cmd.query`）、SWT/Java 方法（`getChildren`）、命令与文件名**都不带括号**写。
> 这条让闸门能把「库函数名」与普通行内代码分开 —— 见 `ctl/__main__.py` 的
> `_skill_namespace_consistency`。

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

### 换一台机器：内置 target 的安装根不是你的

内置 `gs32` / `ccs12` 的安装根是**参考机**的值。换机器后第一次连接会停在这一条上，
并把可复跑的修法**印在错误里**（逐字原文、两种措辞见 [`references/recovery.md`](references/recovery.md)）：

```bash
python -m ctl targets add gs32 --source-dir <你的 GS32_Studio 安装根>
```

两个 target 各设一次（`gs32` / `ccs12`），`python -m ctl targets list` 的 INSTALL_DIR 列应是你的路径。

### 几条容易踩的

- **参数别硬编码**：跑某条命令前先 `cmd.query <id>` 取 `parameters[]`，再拼 `cmd(id, **params)`。
- **`ToolItem` / `MenuItem` / `CTabItem` / `TreeItem` 不是 `Control`**：`getChildren()` **拿不到**它们，
  要走 `getItems()`。工具栏按钮的语义常在 `getToolTipText()`（`getText()` 可能是空的）。
- **读控件树要给够深度**：默认 `tree(3)` 只到深度 3，很容易停在 `Composite` 上被误判成「读不到」。
  实测（2026-10-05，CCS 12.8.1 与 GS32 1.2.5.2 同值，**主可见 shell 域**）：编辑器内部的 `StyledText` 在**深度 15**，
  视图内部更浅（Project Explorer 的 `Tree` 深度 8 / Outline 的 12）⇒ **要读部件内部，给 `tree(15)` 起步**。
- **默认只看「最大的可见 shell」**：e4 会把**尚未渲染**的部件停在不可见的
  `PartRenderingEngine's limbo` shell 里 —— 那时**任何深度**都读不到它们（GS32 上 Welcome 最大化时
  编辑器与 4 个视图栈全在里面）。`tree(depth, shell=…)` 可按 `all` / 下标 / 标题子串换 shell：
  每个 shell 的 `root` 头带 `shell=i/n`，标题与下标先用 `resp("ui.shells")` 取。
- **幂等三档**（决定能不能自动重试）：`true` 可重试；`false` 不可；**`per-command`** ——
  一个方法名承载任意命令、方法级无从保证（`cmd.run` / `cmd.runp` 就是这档）
  ⇒ **与 `unknown` 同等保守，一律不重试**（实测：开关型命令连点两次会**回到原状**）。

## 三、超时后怎么办

**不许**认定「没执行」—— 桥用 `asyncExec`，超时只结束等待，排队的动作**仍可能生效**。

**主路径全在库函数里**（`ctl run` 脚本命名空间，不必 shell 出去）：

1. **先看**：`windows()`（本 run 的可见顶层窗，只读）—— 拿到那个框的**真标题**，
   不要先猜、不要问用户。`#32770` 是原生对话框的窗口类。
2. **再拍**：`see(name="hung")` —— 走 `shot-window-pw.ps1` 落到 `<run 目录>/shots/`，
   回「真路径 + 窗口行」；不给 `title` 时它**优先拍对话框**（没框才拍工作台主窗）。
   **顺序不能反** —— 弹框标题通常不含产品名，按主窗名去截会拍到**一张没有框的图**，
   正好把你推向「一切正常」。
3. **处置**：默认**只关窗**（等同点右上角 X）—— `close_window("<真标题>", yes=True)`（默认 dry-run）。
   只有用例**显式声明**了按钮时才按它（点按钮 = 替用户做不可逆决定）：
   `act_click_button("<真标题>", text="&No", yes=True)`。
   同名按钮不止一个时**不要挑第一个**（命中 0 或 >1 都失败并列出候选；确实要选第 n 个就显式给 `index=`，
   0 基、只在同一会话内稳定）。
4. **探活 —— 但「ping 得通」证明不了「界面没卡」**：模态框在屏上时，**另一条连接**的
   `ui.parts` / `ui.tree` / `sys.ping` **全都正常返回**（SWT 模态框跑的是嵌套事件循环）；
   只有**发起那次请求自己**会 `ERR timeout`。
   ⇒ **别拿「`ui.*` 通不通」判断界面卡没卡**，直接**枚举/截图看那个框在不在**。
   ⇒ 反过来也要记住：**你发的那次请求超时了，不代表别的连接也干不了活**。
5. **回看留档** —— **先看当时那一帧，再看现在**。顺序有方向性：留档是"**当时**"的唯一来源，
   而"现在"随时可取。

   `write` 类动作每拍一次会自动留一帧到 `<run 目录>/shadow/`（清单 `manifest.jsonl`）。
   出事时它是「**当时那一刻**屏幕长什么样」的**唯一**来源 —— `windows()` / `see()` 只能告诉你**现在**。

   ```python
   print(shadow())          # 本 run 的留档清单（纯读盘；带 seq / 时刻 / 是否 promoted）
   print(shadow(seq=3))     # 按序号取某一条
   ```

   - 出事的那几帧会被**自动标 `promoted`**（`outcome != ok` ∨ 回话含 `dialog=` ∨ `ERR timeout`）
     ⇒ **先看它们**；手动改判用 `python -m ctl shadow --promote N`。
   - **产生**要桥活着（触发判据走桥的 `sys.help`）；**读**它**不需要桥**
     ⇒ **桥后来死了，死前拍下的帧仍然列得出来**。
   - **不能承诺的**：桥**从头**就不可达 ⇒ 该 run **一张帧都没有** —— 那时只剩
     `windows()` / `see()`（看现在，也需桥）与 `<run 目录>/console.log`（纯文件）。
   - 帧**不是判据**，是**留档**（像素通道会撒谎，且留档通道**没有** `see()` 那层空白拒收）：
     判据仍然只认回读差与 `dialog=` 行。
6. **再取一次回读差**，把差值归因到先前那次超时请求 —— **这一步不能省**，
   否则会把迟到的副作用算到下一次动作头上。

**Fallback（库函数这条路走不通时才用）**：同一套动作的 shell 版
（`tools/win-enum.ps1` / `tools/shot-window-pw.ps1` / `tools/win-close.ps1` / `tools/win-click-button.ps1`）
在 [`references/recovery.md`](references/recovery.md)，含逐条命令与 `-Index` 纪律。

## 四、不许做什么

- **不要一次开一堆连接压桥**：全功能槽只有 **8** 个，而且**连着的空闲连接也算占槽**。
  满员后只有 `sys.ping` / `sys.env` / `sys.help` 还能答，其余回 `ERR busy`
  （**可重试**，别当成故障）。**用完就关**。
- **不要用坐标点击**（该路线**未证实**，且**决定不投入**）；要动手柄一律**元素寻址**。
- **不要拿观测当判据**：`see()` 的照片是**证据**，`shadow()` 的帧是**留档**；两者都**不能**充当 PASS/FAIL。
  截图通道有「返回 TRUE 却画出整张全黑」的真实失败模式 —— **一个会撒谎的通道不能当断言**。
  判据只认**回读差**与回话里的 **`dialog=` 行**。（两条通道的分工见 `references/observation.md`。）
- **不要以为按键原语「到处都能打字」**。真 IDE 实测（2026-10-04，GS32 4.30 的 Preferences 过滤框）：
  **非字符键（`BACK` / `DELETE` / 方向键 / `RETURN`）可行**（`DELETE` 把 `proxy` 删成 `roxy`，过滤树清空）；
  **可打印字符无效果**（`X` 无回读差）—— 要「打字」一律走 `act_set_text`；
  结果还取决于**插入点**（`BACK` 在插入点 0 时无可删，**不是**原语失效）。
  ⇒ 一条「无回读差」**先排除目标自身状态**（插入点 / 选区 / 只读 / IME）再下结论。全文见 `references/input.md`。
- **不要反复重试** `ERR disabled` / `ERR unhandled`（enablement / handler 问题，重试无用）。
  `ERR busy` 相反 —— **它就该重试**（可配退避）。
- **不要在 `--json` 场景把 stderr 混进 stdout**：诊断只走 stderr，stdout 只放结果。
- **不要用 `taskkill //F`**（参数会被 shell 吃掉）；用
  `pwsh -Command "Stop-Process -Id <pid> -Force"`。而且**要认准自己的 pid** ——
  按映像名杀会连带杀掉别人的实例。
- **不要在真 IDE 的**主窗**里找输入目标**：实测主窗的 `Button` 与 `Edit` **各为 0**；
  元素寻址的真实适用面是**对话框**（那里才有 `&Reset Perspective` / `&No` 这类真按钮）。
