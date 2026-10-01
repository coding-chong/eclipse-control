# 边界清单（能做 / 不能做 / 未验证）

**粒度**：方法级。**读者**：所有人（含 AI 会话）。
**条目格式**：`- **能力**：<内容>` / `- **证据**：<出处或实测原文片段>`（「未验证」条目再加 `- **验证入口**：<可复跑命令>`）。
**措辞纪律（不得混用）**：`未证实` / `已否决` / `决定不投入` 三者含义不同——
`未证实` = 试过但没有可观测的正证据；`已否决` = 有**方法无效**级别的证据；`决定不投入` = 用户口径的选择，
**不是**实验结论（出处 `design-project.md` §18.2、`research/facts-baseline.md` §12、`prd.md` §5）。

**本文件条目数**：能做 9 条 / 不能做 11 条 / 未验证 13 条，共 **33 条**，每条恰好一个「证据」字段。

---

## 1. 能做

### A1 控制台层（framework 级，不进进程）
- **能力**：热装/热更/启停/卸载 bundle、列服务（支持 LDAP 过滤）、查扩展点、读 Error Log、应用管理（apps/startApp）、`fork`（不等）/`exec`（等待）起外部进程。
- **证据**：`research/facts-baseline.md` §2 三层能力表；控制台实测 65 条命令去重清单见 `route-comparison.md` §9.5。

### A2 桥读面（已通 + 新增已在源码实现）
- **能力**：既有 9 个方法 `sys.ping` `sys.env` `ui.shells` `ui.parts` `ui.viewids` `ui.persp` `ui.tree` `cmd.list` `cmd.query` 已通；新增 2 个 `sys.wait [<ms>|jobs-idle]`（D2）与 `ui.console [--tail <n>]`（D3）**已在桥源码实现**（`bridge/src/ctl/bridge/LiveBridge.java` 的方法注册表），验收面 11。
- **证据**：`prd.md` F3；`research/facts-baseline.md` §3 方法面表（标注「待实现 ⇒ 不计入已通」）；源码实现见桥的方法注册表（`sys.wait` / `ui.console` 两条 `add(...)`）。

### A3 SWT 控件树的正确读法
- **能力**：能读到 `ToolItem` / `MenuItem` / `CTabItem` / `TreeItem` / `TableItem`（它们**不是** `Control`，必须走 `getItems()`）；`ToolItem.getToolTipText()` 是按钮语义的权威来源。
- **证据**：`research/facts-baseline.md` §4 容器/成员读法表与 `ui.tree 7` 实测结构。

### A4 桥写面四类（各有回读差）
- **能力**：开厂商视图（5 个逐个 added：views 8→9→10→11→12→13）、关视图（13→12→…→8，`stillOpen=False`；此处 `…` 表示逐个递减）、切透视图（id 如实变化）、开文件进 CDT 编辑器（editors 0→1→2，class=`org.eclipse.cdt.internal.ui.editor.CEditor`）。
- **证据**：`research/facts-baseline.md` §5 「已通过的写路径」表；`prd.md` F4。

### A5 跨产品复现
- **能力**：同一套技术对 CCS 12（Eclipse 4.23 / JRE 11）复现成功，不只 GS32（4.30 / JRE 23）。
  **两个 target 各自跑通全量门禁**（2026-10-02 实测）：

  | 门禁 | gs32 | ccs12 |
  |---|---|---|
  | `verify --all` | **23 PASS + 1 SKIP / 0 FAIL** | **19 PASS + 5 SKIP / 0 FAIL** |

  **差异逐条**（6 条 SKIP **全部**是"声明式 skip"或"判据不适用"，**无一条是失败**）：

  | 差异 | gs32 | ccs12 | 原因 |
  |---|---|---|---|
  | 命令总数 | 666 | **807** | 厂商 bundle 数 `com.gs` 15 个 vs `com.ti` 177 个 |
  | 厂商命令数 | `com.gs` **7** | `com.ti` **115** | 两家产品命令面不同 |
  | 活动透视图 | `org.eclipse.cdt.ui.CPerspective` | `com.ti.ccstudio.TICPerspective` | 厂商产品自带透视图 |
  | `read.console` | PASS | **SKIP** | 该 ccs12 实例**没有 console 页**（`Console view has no console page`）⇒ 判据不适用 |
  | `write.close-view` / `write.runp-show-view` / `resilience.modal-reset` / `resilience.timeout-applied` | PASS | **SKIP** | 四条用例声明 `targets=("gs32",)`，**按 target 声明 skip 而非 fail** |

- **兼容矩阵**（五项列）：

  | 列 | gs32（GS32_Studio v1.2.5.2） | ccs12（CCS 12.8.1） |
  |---|---|---|
  | 平台版本 | Eclipse Platform **4.30.0** | Eclipse Platform **4.23.0** |
  | JRE 模块数 | **30**（JustJ JRE 23.0.2） | **55**（JRE 11.0.13） |
  | 命令服务 bundle 版本 | `org.eclipse.ui.workbench` **3.131.0** | `org.eclipse.ui.workbench` **3.125.0** |
  | 厂商命令数 | `com.gs` **7**（总 666） | `com.ti` **115**（总 807） |
  | 必须重编的产物 | `eclipse-ctl.bridge_3.1.0_gs32.jar`（class-file **61** = Java 17） | `eclipse-ctl.bridge_3.1.0_ccs12.jar`（class-file **55** = Java 11） |

  > **同一份源码、两个字节码级别**：ccs12 的 JRE 是 11 ⇒ `-source/-target 11`；gs32 是 17。
  > 两个 jar **按 target 命名并存**（此前同名会互相覆盖），`doctor` 会校验 jar 内 class-file 级别
  > 与目标声明的 `java_target` 一致。ccs12 **不带 JDT**，其 ECJ 从 gs32 安装树外借。

- **证据**：`research/facts-baseline.md` §1 目标环境表；`prd.md` F5（出处 `route-comparison.md` §9.12）；
  2026-10-02 实测：`verify --all --target gs32` / `verify --all --target ccs12` 的逐条输出、
  `commands.json`（gs32 自省产物，`total=666`）、`ctl commands --run-id ccs12-p42`（807 / `com.ti` 115）；ccs12 侧截图归档
  `<run_root>/ccs12-p42/shots/errors.plugin-id-as-view-005355-Problem_Occurred.png`。

### A6 Input 域 · 元素寻址的输入原语
- **能力**：`EnumChildWindows` 定位窗口内的**控件自身 HWND**，把消息直接发给它 —— **不用鼠标、不要求前台**。
  审批口径见 `design-project.md` §18.2/§18.3；**坐标注入不在产品面内**（见下表末三行，只作定论记录）。

  **原语表**（A14：每行给「原语 / 寻址 / 实测结果 / 证据」）

  | 原语 | 寻址 | 手段 | 实测结果 | 性质 |
  |---|---|---|---|---|
  | **点 `Button`** | 窗口标题 + 控件**文本**（必须唯一） | `SendMessage(hwnd, BM_CLICK=0x00F5, 0, 0)` | ✅ 标题 `ctl-fixture` → **`GO n`** | **能力** |
  | **按键** | 窗口标题 + **类名 + 序位** | `WM_KEYDOWN/WM_KEYUP`（`0x0100`/`0x0101`） | ✅ 标题 → **`KEY 13`**（VK_RETURN） | **能力** |
  | **文本输入** | 窗口标题 + **类名 + 序位** | `WM_SETTEXT`（`0x000C`） | ✅ 标题 → **`TEXT <载荷>`** | **能力**（与焦点/键盘布局无关） |
  | 点**不存在**的控件 | 文本 | `ctl act click-button` | ✅ **退出码 1**（存在控件为 0） | **证伪** |
  | 坐标 → **按钮 HWND** | client 坐标 | `WM_LBUTTONDOWN/UP`（`0x0201`/`0x0202`） | ✅ 标题 → `GO n+1`（**有效**） | 定论记录 |
  | 坐标 → **顶层 Shell**（同一坐标、同一消息） | client 坐标 | 同上 | ⚠️ 标题**不变**（**无效**） | 定论记录（**对照组**） |
  | 坐标 → 空白 (5,5) | client 坐标 | 同上 | ✅ 标题**不变** | **证伪** |

  > **②a vs ②b 是本域最有价值的一条**：两条**坐标相同、消息相同**，只差**收件人** —— 发给按钮自己的
  > HWND 有效，发给顶层 Shell 无效（`PostMessage` **不做命中测试**，顶层窗不会把落在子控件区域的
  > 鼠标消息转给子控件）。⇒ **决定成败的是「寻址」，不是「SWT 不认合成输入」。**

  **寻址纪律**（`design-project.md` §18.3）：**命中 0 或 >1 一律失败**（fail closed），不允许「挑第一个」——
  否则同名 `&Save`/`&OK` 会**静默点错**。三个 `act` 动作**都不带 `--yes` 只打印 `DRY-RUN`**（§16.2 的 `act *` 口径）。

  **CLI 入口**：`act click-button`（文本寻址）/ `act send-keys --key <名>` / `act set-text --text <载荷>`
  （后两者按 `--class`（缺省 `Edit`）+ 可选 `--index` 寻址）。命令面定义见 `design-obs-ux.md` §14.3。

  **已知差距**（如实）：`act click-button` **只支持文本寻址**，`--index`/`--path` 显式拒绝（见 N11）；
  **路径（下标路径）**这一档仍未实现。

  **已修（2026-10-02）**：下层 `tools/win-click-button.ps1` 曾**违反上面那条寻址纪律** ——
  「命中 0」只打印 `no visible Button matching` 而 **`exit 0`**（静默成功），
  「命中 >1」**静默点第一个**。现改为 **0 命中与 >1 命中都 `exit 1`**（后者列出候选）。
  CLI 层本来就是这个契约（`_act_click_button` 先 `-ListOnly` 自检），这次是**下层工具对齐上层**，
  免得直接调工具的调用方（如 `ctl/screen.py` 的模态框处置路径）把「没点到」读成「点到了」。

### A6b 控件类别的元素寻址结论（P6.4）

夹具 v2 加了 `Menu` / `ToolBar` / `Tree` 后重测。**做法**：先枚举子窗看**谁有自己的 HWND**，再对有的那几类试消息注入。

| 控件 | 自己的 HWND？ | 元素寻址（消息注入） | 实测证据 |
|---|---|---|---|
| `Button` | ✅ `Button` | ✅ **可行** | `BM_CLICK` → 标题 `GO n`（用例 `input.fixture` ①） |
| `Text` | ✅ `Edit` | ✅ **可行** | `WM_KEYDOWN` → `KEY 13`；`WM_SETTEXT` → `TEXT <载荷>`（③④） |
| `Tree` | ✅ `SysTreeView32` | ✅ **可行**（**对树内坐标**发鼠标消息） | 树内 (30,12) 点一下 → 标题 `TREE 1` |
| **`ToolItem`** | ❌ **无独立 HWND** | ⚠️ **只能对工具栏坐标点**（**未验**） | `ToolbarWindow32` 的子窗数 = **0** |
| **`MenuItem`** | ❌ **根本不是窗口** | ❌ **不可行** ⇒ **必须走命令框架** | 子窗清单里**没有任何菜单窗口**（Win32 菜单是 `HMENU` 条目） |

> **一条负结果（有价值）**：对 `SysTreeView32` 单独发 `TVM_SELECTITEM`(`0x110B`, `TVGN_CARET`)
> **不产生** SWT 的选中事件（标题不变）；能产生的是**对树内坐标发鼠标消息**。
> ⇒ 「有 HWND」**不等于**「有对应的语义消息」。

**替代路径（本条的落点）**：**菜单项与工具项一律走命令框架**（`cmd.run` / `cmd.runp`）——
它们在 Eclipse 里基本都有对应 command。这不是"退而求其次"，是**正解**：
§18.3 早就写了「菜单 / 工具栏 / 树节点 —— **优先走命令框架**」，本次实测**正好证实该预案**。

### A6c 输入与桥的相互影响（F11 / P6.6）

**分两面写，别混。**

| 面 | 状态 | 内容 |
|---|---|---|
| **机制**（推论，已标注） | `[INFERENCE]` | 合成输入与真实输入**走同一条投递路径**，都由 UI 线程处理。因此**只有当某个输入触发了"阻塞 UI 线程的行为"**（弹模态框、跑长任务）时才可能停摆 —— 与 F7 是**同一个失败面**，不是新的一类。空闲点击的 handler 微秒级返回，**观测不到**。 |
| **实测** | ❌ **本轮未做** | **不得**用"命令弹模态框"的场景（§6 那次）冒充"输入场景"。见下方验证入口。 |

**为什么本轮不做（不是遗漏，是刻意）**：把合成点击打进**真 IDE 的工作台**，等于**在不知会用户的情况下替它按下一个未知按钮**
——坐标落点不可预判，可能触发 `Open Perspective` 之类会弹框的操作。
仓库纪律是「点按钮 = 替用户做不可逆决定 → **只有用例显式声明时才点**」（`design-obs-ux.md` §13.2.2）。
在**没有声明目标按钮**的前提下做这件事，与纪律直接冲突。**所以本轮如实标为"未验"，而不是偷偷做掉。**

**验证入口（安全做法，供后续执行）**：
1. `install --target gs32 --run-id gs32-p66` 起实例，`sys.ping` 确认桥活；
2. **先在夹具上**（`verify --case input.fixture`）确认原语能用 —— 夹具已证明「SWT 认，且成败在寻址」；
3. **再由用例显式声明**一个**已知无害**的目标（如状态栏 `Label` 区域、或某个可回读的只读视图标题），
   发一次 `WM_LBUTTONDOWN/UP`，**同时**以 ≤50 ms 间隔轮询 `sys.ping`；
4. 判据：`sys.ping` 全程 p95 **仍 ≤ 50 ms** ⇒ 输入不停摆桥；若出现停摆，**必须先截图**确认是不是弹了框（§13.2.1）；
5. 把结果回填本节，并把 `[INFERENCE]` 换成实测。

- **证据**：`research/p6-input-fixture-2026-10-01.md` §2（六条断言首次实测）与 §7（P6.4 五类控件）；
  **用例化复现（2026-10-02，`target=gs32`）**：`python -m ctl verify --case input.fixture --target gs32` → **PASS**，
  证据逐条给出 ① `ctl-fixture`→`GO 1`、②a `GO 1`→`GO 2`、②b 同坐标同消息发顶层 Shell **不变**、
  ③ →`KEY 13`、④ →`TEXT P6CASE`、⑤ `ctl act click-button --text &NoSuchButton` **退出码 1**、⑥ (5,5) **不变**。
  夹具源码 `tools/fixture-swt/Fixture.java`；探针 `tools/fixture-swt/probe.ps1`（随夹具走，取证装置，不属产品）；
  用例 `ctl/verify/cases/input_fixture.py`（`requires_bridge=False`，自带夹具启停）。

### A7 观测装置 · 截图
- **能力**：`tools/shot-window-pw.ps1`（`PrintWindow` + 先 `SetProcessDPIAware`）为**主通道**，不受遮挡、不受 DPI 虚拟化影响；OCU 的 `get_app_state(include_image=true)` 为**备用**（小窗可用）。
- **证据**：`design-obs-ux.md` §13.1 两条通道表；`research/facts-baseline.md` §11.1（rect 513×132 → 1154×296 的修法实测）。

### A8 热装即起 + 桥常驻
- **能力**：控制台 `install file:<jar>` → `start <id>` 即起；桥被 OSGi 记进**当前使用的配置区**（`configuration/org.eclipse.osgi/<id>/`），跨工作区、跨重启都在；`uninstall <id>` 或删该目录后 `-clean` 可清。
- **证据**：`research/facts-baseline.md` §7；`prd.md` F6（出处 `route-comparison.md` §9.16）。

### A9 命令表反查
- **能力**：`ctl commands find --text <S>` 可按 UI 文字反查命令 id（A8 的判据：`--text "Reset Perspective"` 必须包含 `org.eclipse.ui.window.resetPerspective`）。**状态**：设计已定（`design-obs-ux.md` §14.3），落地由 P5.3 验。
- **证据**：`design-obs-ux.md` §14.3 命令表 `commands find` 行；`prd.md` A8 反查判据。

---

## 2. 不能做

### N1 控制台不能反射调用任意 Java 方法（**已否决**）
- **不能做**：从控制台对任意对象调任意方法；`inspect` 不是那条路。
- **证据**：`prd.md` F10；`route-comparison.md` §9.5 原文——`inspect` 是 **Felix Gogo 的** `inspect`（`scope: felix`，签名 `(String 'capability'|'requirement', String <namespace>|'service', Bundle[])`），不是 Equinox 那个能对任意对象反射调方法的同名命令；⇒「控制台无法调用任意 Java 方法」。三档归类见 `design-project.md` §18.2 第 3 行。

### N2 桥只在**已创建的 UI** 上工作
- **不能做**：工作台尚未创建时读界面/发 UI 命令。此时桥**仍会启动并监听**，但 UI 方法抛 `java.lang.IllegalStateException: Workbench has not been created yet`。
- **证据**：`research/facts-baseline.md` §7「探针」段；`prd.md` F6 同段。

### N3 弹模态框会把桥堵到不使用（机制已实证；**其中一处数字属转述**）
- **不能做**：让桥自己处理模态框。任何会弹模态确认框的命令（`resetPerspective`、`Delete resource?` 等）都会占住 UI 线程；旧的单线程 accept 使桥连 `sys.ping` 都不回。**桥内不自动点按钮**（不可逆决定留在调用方）。
- **证据**：`research/facts-baseline.md` §6（两层根因 + bg_201 对照）；⚠️ 该节自带诚实性标注：「`sys.ping` 由 0.0 s 变 8.0 s 超时」是**手写转述**，桥侧 stamp 只记成功的 `SERVED`、超时不落痕（`bg_201/README.md §3(b)`）；`prd.md` F7 同此标注。

### N4 控制台层够不到 UI 层
- **不能做**：从 OSGi 服务表拿 `ICommandService` / `IHandlerService` / `EModelService` / `ISelectionService` / `IPartService` / `Display`——实测**全部 0 命中**；要读控件树 / 执行 IDE 命令必须让一个 bundle 进入进程。
- **证据**：`research/facts-baseline.md` §2「OSGi 服务表实测」段（仅 `IWorkbench`（220）、e4 `IWorkbench`（207）、`IEventBroker` 在册）。

### N5 控制台不能承担 Java 编译，桥也不能「等外部编译」
- **不能做**：① 用控制台编译 Java——本机**无 `javac` / 无 `jar.exe`**，控制台 65 条命令里**没有**编译命令；编译只能走 ③ 工具链（目标安装树自带的 ECJ 批编译器 / `headlessbuild` 外部进程），且 SWT 类与 `IStartup` 真身都在目标平台的片段 jar 里。② 用桥「等一次外部编译完成」——桥的 `sys.wait` 等的是 IDE 内部的 `JobManager`，**不是** UI 事件、也不是外部进程；外部 `headlessbuild` 的完成必须由发起它的那个外部进程自己等。
- **证据**：`research/facts-baseline.md` §8 编译链事实表（免 JDK：ECJ `org.eclipse.jdt.core.compiler.batch_3.36.0.v20231114-0937.jar`、`-cp` 用 `;`、无 `jar.exe` ⇒ Python `zipfile` 打包）；`route-comparison.md` §9.5 命令分类表（无编译族）；`implement.md` P6.1（「本机无 javac」）；`design.md` §6 `sys.wait` 行（「桥侧读 `JobManager`；**不是** UI 事件等待」）。

### N6 `ui.console` 只读**活动** Console
- **不能做**：一次读多个 Console。`ui.console` 只返回**活动** Console 的文本尾 N 行；要读另一个必须先把它激活。
- **证据**：`design.md` §6 `ui.console` 行（「只读**活动** Console；多个需先激活（**D3 新增**）」）；裁决见 `design-project.md` §18.7 D3。

### N7 OCU 整窗截图有 1 MiB 上限
- **不能做**：用 OCU 截大窗。2700×1832 的 GS32 主窗 `include_image=true` 实测触发 `Windows runtime returned oversized output`（OCU 自身载荷上限）；`include_image=false` 正常返回小树，小窗单截可用。
- **证据**：`design-obs-ux.md` §13.1 B 行；`research/facts-baseline.md` §11「大窗上限」行。

### N8 `CopyFromScreen` 截图通道在本机不可用
- **不能做**：用 `tools/shot-window.ps1`（`CopyFromScreen` 版）作主通道。实测 rect 报 513×132（真实 1154×296），抓到的却是 IDE 工具栏——遮挡 + DPI 虚拟化双重坑。它已**降级为备用**。
- **证据**：`research/facts-baseline.md` §11.1 两种成因与修法；`design-obs-ux.md` §13.1 A′ 行。

### N9 `executeCommand(id, null)` 不路由到 part-scoped handler
- **不能做**：用 `IHandlerService.executeCommand(id, null)` 驱动部件级命令（`org.eclipse.ui.edit.selectAll` 永远 `NotHandled`）。另外 `org.eclipse.ui.file.saveAll` 在开编辑器前后都是 `NotEnabledException`——它的条件是「有**脏**编辑器」，不是「有编辑器」。
- **证据**：`research/facts-baseline.md` §5「enablement 的两条实测结论」（1、2 两条）；出处 `route-comparison.md` §9.13.1。

### N10 桥没有 dry-run 概念
- **不能做**：指望桥自己「先空跑一遍」。dry-run 只能落在**客户端**，且**只作用于会改 IDE 状态的方法**（`cmd.run` / `cmd.runp` / `ui.open` / `ui.close` / `act *`）；只读方法默认真发，dry-run 也不阻止建立连接。不带 `--yes` 时 CLI 的行为是**打印 `DRY-RUN <line>` 到 stdout 并以退出码 0 结束**——**桥侧零请求**。
- **证据**：`design-project.md` §16.2（含审计修正：「否则 `ctl parts` 会变成空操作」）；`--yes` 只挂在 `cmd` / `open` / `close` / `act` 四个写子命令上。

### N11 `ctl act click-button` 当前只支持**文本**寻址
- **不能做**：用 `--index` / `--path` 寻址。这两个参数**存在但会显式拒绝**（底层 `tools/win-click-button.ps1` 只做 `--text` 文本匹配）。
- **证据**：`design-project.md` §18.3 的「寻址稳定性契约」把**路径（下标）列为首选**、文本列次选 —— 但
  **`act click-button` 只落到「文本」这一档**，`--index`/`--path` 参数存在却被显式拒绝（实测
  `ctl act click-button --index 0` 报错）。**范围限定**：这是 `click-button` 一条的差距；
  同族新增的 `act send-keys` / `act set-text` **已支持「类名 + 序位」寻址**（`--class` / `--index`）。
  本条的**剩余**差距是「路径（下标路径）」这一档仍未实现。这条是**设计 ↔ 实现的差距**，不写成「已证伪」。

---

## 3. 未验证

> 本节每条的形态：**不是**「能做」也不是「不能做」，**禁止当结论用**。

### U1 「同时只能用一个实例」是**旧产物限制**，不是桥的固有性质
- **未验证**：现行三册设计文档里**没有这句话的逐字出处**；可核到的只是三个可能成因——① 旧产物端口写死 `8777`；② Equinox **除工作区外还锁 configuration 区**，同一安装目录的两个实例会互相干扰；③ 旧 accept 循环单线程串行 `handle(c)`。三条成因各自的修法（端口可配 / 运行配置区隔离 / 每连接一线程）都是**设计决定**，其效果**尚未验证**。
- **验证入口**（三项全满足才算「一份安装树能跑多实例」，判定程序见 `implement.md` P0.4b）：
  ```bash
  python -m ctl install --target gs32  --run-id A --port 8877
  python -m ctl install --target ccs12 --run-id B --port 8878
  python -m ctl shell --run-id A -c "ui.parts"
  python -m ctl shell --run-id B -c "ui.parts"
  ```
  ① 启动后 `<run_root>/<run_id>/configuration/config.ini` 存在且 `eclipse.product` 为该产品值；
  ② 控制台 `install file:<jar>` + `start` 后桥日志落在该配置区，**且跑前/跑后对 `<source_dir>/configuration/` 递归清单取哈希必须不变**；
  ③ 同一 `source_dir` 同起第二实例（不同 `-configuration` / `-data` / `--port`），两边 `sys.ping` + `ui.parts` 都通。
- **证据**：端口写死 → `implement.md` P0.4a（旧写法 `Integer.getInteger("livebridge.port", 8777)`）；配置区互锁 → `design-project.md` §16.1；单线程 accept → `design.md` §4 现状表（`research/facts-baseline.md` §6 机制①）。

### U2 坐标注入 / SWT 上的合成输入 —— **未证实**
- **未验证**：审计 3 次 `app_post` 全无变化，且审计原文明确「**不能**据此判定方法无效」；用户口径**决定不投入**（**不是**「已证伪」）。本条按缺口保留为「未验证」。
- **验证入口**：`design-project.md` §18.4 最小 SWT 夹具的 6 条断言，其中 **②**（坐标点同一位置）与 **⑥**（坐标点空白处必须无变化）即为把本条结掉的断言；构建/运行照 `design-project.md` §18.6，用例入口 `python -m ctl verify --group input --target fixture`。
- **证据**：`prd.md` §6.5（含「不投入是用户口径的决定，不是实验结论」）；`design-project.md` §18.2 第 2 行；出处 `09-30-gs32-no-gui-audit/research/ocu-coordinate-click.md §1`。

### U3 元素寻址输入原语的**泛化**
- **未验证**：`BM_CLICK` 按控件文本点 `Button` 已实测可行，但此前**只验证过「解除模态框」这一个用例**；作为通用原语（任意控件 / 菜单 / 工具栏 / 树节点 / 按键 / 文本输入）**未验**。文本输入与按键「完全未验」（桥内 `Display.post` 与外部消息注入两条路都没试过）。
- **验证入口**：`python -m ctl verify --group input --target fixture`（夹具断言 ③ 按键、④ 文本输入）；菜单/工具栏/树节点按 `implement.md` P6.4 各自给结论，**能走命令框架的一律优先走命令**。
- **证据**：`prd.md` §6.7、§6.8（含 prior art：真按键合成走 `Display.post` 且**要求目标是前台窗口，否则拒绝**；文本输入更稳的是直接改编辑器 document——出处 `routes/eclipse-mcp-vogella.md:62-64`）。

### U4 运行配置区隔离（`-configuration`）是否生效
- **未验证**：默认方案是「传 `-configuration <run_root>/<run_id>/configuration`，一份源安装树跑多实例、不碰源树」；生效前**不得**宣称「源安装目录零触碰」。
- **验证入口**：`implement.md` P0.4b 三项判据（同 U1 的 ①②③）；不生效则回退 `--copy`（`design-project.md` §16.1 回退列）。
- **证据**：`design.md` §8「**待 P0.4b 实测确认**」；`research/facts-baseline.md` §1 的「候选做法，`P0.4b` 待实测」限定词（证据库 `route-comparison.md:78` 记为「未验」）。

### U5 `cmd.list` 的全量导出
- **未验证（修正已在源码落地，运行期未验）**：修正后的契约是「空前缀 = 全量导出」且必须带 `total` / `returned` / `truncated`（见 `protocol.md` §8）。桥源码已去掉默认 300 上限、改为**只在显式 `--limit <n>` 时**截断，并如实报 `total` / `matched` / `returned` / `truncated`；`ui.viewids` 同改。**但这一行为尚无运行期实测**（本文件写作时未在真实例上跑过），旧产物的 `total=666` 只列 300 的陷阱仍须在验收时逐条比对。
- **验证入口**：
  ```bash
  python -m ctl commands --json | python -c "import json,sys; d=json.load(sys.stdin); print(d['total'], d['returned'], d['truncated'])"
  ```
  必须 `returned == total >= 666` 且 `truncated == False`。
- **证据**：`research/facts-baseline.md` §3 陷阱段与 §11.2 第 1 行（「现产物 `cmd.list` 空前缀也只吐前 300 条」，源码硬截断 `if (n <= 300)`）；`design.md` §6 `cmd.list` 行；`design-project.md` §16.5「命令表全量导出：`cmd.list` 空前缀 = 全量」；修正实现见桥的 `cmd.list` / `ui.viewids` 处理（默认无上限 + 三字段）。

### U6 并发行为
- **未验证**：除「单连接串行」外的并发行为未测——多连接同时发、长请求期间的第二请求，都未验。且按 `design.md` §4，N=8 的线程池不区分 UI 与非 UI；若 8 条 UI 请求都被模态框堵住，`sys.ping` 只会拿到 `ERR busy`（审计已点出这会动摇 G3 的判据）。
- **验证入口**：`implement.md` 门禁 G3 的**两档并发探针**（1 个 UI 卡死 / N 个 UI 卡死时 `sys.ping` 仍通），用例 `python -m ctl verify --group resilience`。
- **证据**：`prd.md` §6.1；`research/audit-round3-2026-10-01.md`（`design.md:98 与 implement.md 门禁 G3` 条目）。

### U7 深层控件树
- **未验证**：CCS 12 上 `ui.tree 5` 只展开到 `Composite`，更深层读取未解决。
- **验证入口**：`python -m ctl tree --depth <N>` 逐步加大 N，直到出现目标控件（用例须显式给 depth，`design.md` §12 风险表「深层树读不到」）。
- **证据**：`prd.md` §6.4；`design.md` §12 风险表同项。

### U8 e4 应用模型层寻址
- **未验证**：`EModelService` / `MApplication` / `MWindow` 层寻址未实测。
- **验证入口**：先 `python -m ctl parts --json` 确认 `EModelService=true`，再按 `implement.md` 增一条用例，以 `ui.parts` 回读差为判据。
- **证据**：`prd.md` §6.3；`design.md` §6 `ui.parts` 行（负载含 `EModelService`）。

### U9 JDI / JDWP 求值通道
- **未验证，本轮不投入**（D6）：它是唯一能补 F10「控制台无法求值」的已知路线（CDP `Runtime.evaluate` 的对应物）；代价是新子系统 + **挂起会冻死整个 IDE**，需独立安全设计。
- **验证入口**：`jdb -attach <host>:<port>` 对已带 `-agentlib:jdwp=<opts>` 起的实例（调研实测该路可达 suspend / 列线程 / 求值）。
- **证据**：`prd.md` §6.9；`design.md` §11 取舍表「JDI / JDWP | 不投入本轮（D6）」。

### U10 输入是否占用 UI 线程（F11 是**归类判断**，不是实测）
- **未验证**：桥的 `syncExec` 与「任何占用 UI 线程者」互斥——**外部输入（点击/按键）是否也算占用同一线程，未验**。从未观察到「点击导致桥停摆」。
- **验证入口**：`implement.md` P6.6——桥**正常服务期间**用 `tools/win-click-button.ps1`（`BM_CLICK`）点主窗一个**无害按钮**，同时在**另一条连接**上量 `sys.ping` 往返与 `ui.parts` 是否被拖慢。**不得**再用「重发 `resetPerspective`」当输入场景（那是**命令**弹框，不是输入）。
- **证据**：`prd.md` F11 与 §6.10；`design.md` §18.1（F7 的机制直接落在 Input 域上）。

### U11 `getDefinedCommandIds()` 结构性漏项
- **未验证（恢复路径已在源码落地，运行期未验）**：`getDefinedCommandIds()` 只含**有 `<command>` 声明**的 id，**结构性漏掉**「有 handler 无声明」者——典型正是厂商 OptionBytes = `com.gs.chipsetting.commands.opthandler`。桥源码已增加恢复路径：从活动 bundle 的 `org.eclipse.ui.handlers` 扩展点收集这类 id，并在 `cmd.list` 的 **`handlerOnly`** 块中单独报出。**但它是否真能补上厂商那一条，尚未在真实例上验过。**
- **验证入口**：
  ```bash
  python -m ctl commands --json | python -c "import json,sys; d=json.load(sys.stdin); print('opthandler' in json.dumps(d))"
  ```
  以及 `python -m ctl commands find --text "OptionBytes"` 必须能命中该 id。
- **证据**：`prd.md` A8 的 ⚠️ 注；`research/facts-baseline.md` §3 陷阱段末句（「`getDefinedCommandIds()` 还漏掉「有 handler 无声明」的 id（典型：厂商 OptionBytes）」）；恢复实现见桥的 `cmd.list` 处理里的 `handlerOnly` 块。

### A12 三个 `idempotent` 值**已实测回填**（2026-10-01）
- **能做**：`protocol.md` §7 表与 `sys.help` 的 `idempotent` 列现为实测值 ——
  `ui.open` = **`true`**（同一文件连开两次，`editors` **1→1**，Eclipse 复用已开的编辑器）；
  `cmd.run` / `cmd.runp` = **`per-command`**。
- **`per-command` 的含义（重要）**：一个方法名承载**任意**命令，方法级无从保证 ⇒
  与 `unknown` **同等保守**（**不允许自动重试 / rollback**）。
  依据：`org.eclipse.ui.window.fullscreenmode` 是**开关型**命令，连点两次**回到原状** ——
  幂等性取决于**被调命令**，不是方法。**别拿 `showView` 一个用例推广到整个 `cmd.runp`。**
- **证据**：`protocol.md` §7 的取值表；实测四元组见任务侧
  `research/facts-baseline.md` §7.3。

### N15 `cmd.run` / `cmd.runp` 的失败可能**异步**表现出来，且**监听器抓不到**
- **不能做**：**不能**靠协议回话判断写命令成功了。实测 `cmd.runp … viewId=<不存在的视图>`：
  回话 `OK`、`executeCommand returned: null`，而 Eclipse 随后弹出 `Problem Occurred` 错误框，
  且 `ui.parts` 的 `views` 纹丝不动 —— **界面没变 + 回话说成功**。
  同样**不能**靠 `ICommandService.addExecutionListener`（`org.eclipse.core.commands.IExecutionListener`）
  抓：handler 正常返回，错误在 UI 线程空闲**之后**才弹框，**监听器看到的是成功**。
- **能做**：桥会回报 `dialog=appeared "<标题>"` 负载行（动作前后各取一次「可见且有标题的顶层窗口」快照）；
  桥外 `tools/win-enum.ps1` 也可做同样前后比对。
- **仍然不够**：**不弹框的失败**（只写日志）它看不见 ⇒ 必须配合「回读差」。
  而「回读差没变化」本身**分不清「幂等」与「失败」** ⇒ **三层缺一不可**。
- **证据**：`protocol.md` §4.3；任务侧 `research/facts-baseline.md` §7.2。

### A13 模态框**不传染**（2026-10-01 实测，推翻旧表述）
- **能做**：模态框在屏时，**另一条连接**照常干活 —— 实测 `Reset Perspective` 在屏的那一刻，
  另一条连接的 `ui.parts` / `ui.tree` / `ui.persp` / `sys.ping` **全部正常返回**（0.00–0.02 s）。
- **不能做**：**不能**用「`ui.*` 是否 `ERR timeout`」判断界面有没有被模态框占住 —— 它不会超时。
  判断依据是**窗口枚举 / 截图**（那个框在不在）+ **你发的那次请求**是否超时。
- **会超时的只有发起那次自己**：实测 **15.4 s** 后回
  `ERR timeout UI task did not finish within 15000 ms; …`。
  原因：SWT 模态框跑**嵌套事件循环**，`Display.asyncExec` 队列照常派发。
- **证据**：`protocol.md` §4.2 第 5 条；任务侧 `research/p3-gate.md`。

### N16 连接槽是全桥的**单点容量**：满员后连 `sys.ping` 都会 `ERR busy`
- **不能做**：**不能**假定「桥总能用 `sys.ping` 探活」。容量按 `accept()` 计，**8 条只是连着、
  不发任何请求**的连接就能把全功能槽占满（每条占满 `SOCKET_READ_TIMEOUT_MS`=60 s），
  此后连 `sys.ping` 都拿不到 —— **观测能力被平凡打掉**，且从外面**分不清「忙」与「死」**。
- **能做**：`1..8` 全功能；`9..12` **只准** `sys.ping`/`sys.env`/`sys.help`（`sys.wait` 会阻塞，不放行）；
  `>=13` 直接拒。两种拒绝的 `ERR busy` 消息文本不同，**按错误码判断、不要按字面匹配**。
- **`ERR busy` 一律可重试**（它就在错误码闭集里，语义即「稍后重试」）。
- **降级**：保留槽只有 4 个，所以「满员 + 4 条活体探测同时在飞」的下一瞬仍会 `ERR busy` ——
  这是有界的退化，不是死锁：探测是瞬时的，退避重试即可。
- **证据**：`protocol.md` §4.4；任务侧 `research/p3-gate.md`。

### U13 part-scoped 命令的驱动方法
- **未验证**：已知 `executeCommand(id, null)` **不**路由到部件级 handler（见 N9）；但**如何设置 selection / 构造 Event** 才能驱动这类命令，未验。
- **验证入口**：以 `org.eclipse.ui.edit.selectAll` 为靶——先 `python -m ctl cmd org.eclipse.ui.edit.selectAll --yes` 复现 `ERR unhandled`，再按 `implement.md` 增一条用例，判据为该命令回读差非空。
- **证据**：`prd.md` §6.2；`research/facts-baseline.md` §5 enablement 结论 2。

---

## 4. 本文件不含的结论（防误引）

- 「坐标注入」**不是**「已证伪」，也**不是**「能做」——它是 U2 的**未证实 + 决定不投入**。
- 「控制台反射调 Java」**是** N1 的**已否决**（有方法无效级证据）。
- 「同一个源，两套编译参数（gs32 = 17 / ccs12 = 11）」是 `design.md` §9 的**设计决定**，不是本文件的边界条目。
