# 边界清单（能做 / 不能做 / 未验证）

**粒度**：方法级。**读者**：所有人（含 AI 会话）。
**条目格式**：`- **能力**：<内容>` / `- **证据**：<出处或实测原文片段>`（「未验证」条目再加 `- **验证入口**：<可复跑命令>`）。
**措辞纪律（不得混用）**：`未证实` / `已否决` / `决定不投入` 三者含义不同——
`未证实` = 试过但没有可观测的正证据；`已否决` = 有**方法无效**级别的证据；`决定不投入` = 用户口径的选择，
**不是**实验结论（出处 `design-project.md` §18.2、`research/facts-baseline.md` §12、`prd.md` §5）。

**本文件条目数**（2026-10-05 复算；判据 = §1–§3 内每个条目小节各计一条，
`grep -cE '^### (A|N|U)[0-9]'`）：能做（`A*`）**19** 条 / 不能做（`N*`）**16** 条 /
「未验证」区（`U*`）**12** 条（其中 **10** 条已标「已闭合 / 已定论」、仍开放 **2** 条：U2 / U9
—— U3 于 2026-10-04 收口，见 §1 的 A6b-3；**U8 于 2026-10-05 定论**：可用性成立（实测
`services: EModelService=true`）、「经 e4 模型层寻址」在本代码库里不存在且按 §N9′ 不需要 ⇒
`决定不投入`，见 §U8），
共 **47** 条。（A18 → A19 是同日新增：被 promote 的帧自我报告，见 §1 A19；**N18** 同日新增：
回收通道没有「豁免某个 run」的入口。）§3 里另并入了 4 条 `A`/`N` 编号条目（`A12` / `A13` / `N15` / `N16`），已按编号计入上面的
`A*` / `N*`。§4 / §5 的小节不计入条目。
（旧注记 —— 2026-10-02 的 `12 / 11 / 16 = 39` —— **已作废**：它与任何机械计数都对不上，
且此后新增 / 闭合条目时都没跟着更新；同处原写的「每条恰好一个证据字段」也不成立 —— 全文里
`A6b` / `A6c` 两条各有 2 个 `- **证据**`。）

---

## 1. 能做

### A1 控制台层（framework 级，不进进程）
- **能力**：热装/热更/启停/卸载 bundle、列服务（支持 LDAP 过滤）、查扩展点、读 Error Log、应用管理（apps/startApp）、`fork`（不等）/`exec`（等待）起外部进程。
- **证据**：`research/facts-baseline.md` §2 三层能力表；控制台实测 65 条命令去重清单见 `route-comparison.md` §9.5。

### A2 桥读面（已通 + 新增已在源码实现）
- **能力**：既有 9 个方法 `sys.ping` `sys.env` `ui.shells` `ui.parts` `ui.viewids` `ui.persp` `ui.tree` `cmd.list` `cmd.query` 已通；新增 2 个 `sys.wait [<ms>|jobs-idle]`（D2）与 `ui.console [--tail <n>]`（D3）**已在桥源码实现**（`bridge/src/ctl/bridge/LiveBridge.java` 的方法注册表），验收面 11。
- **证据**：`prd.md` F3；`research/facts-baseline.md` §3 方法面表（标注「待实现 ⇒ 不计入已通」）；源码实现见桥的方法注册表（`sys.wait` / `ui.console` 两条 `add(...)`）。

### A3 SWT 控件树的正确读法
- **能力**：`ToolItem` / `MenuItem` / `CTabItem` 的**文本**能读到（它们**不是** `Control`，必须走 `getItems()`）；
  `Tree` / `Table` **只读到条目数**（`[TreeItems=N]` / `[TableItems=N]`），**条目的文本读不到**
  —— `walk()` 不迭代 `TreeItem` / `TableItem`（`bridge/src/ctl/bridge/LiveBridge.java:852-853`）。
  `ToolItem.getToolTipText()` 是按钮语义的权威来源。
- **证据**：`bridge/src/ctl/bridge/LiveBridge.java:836-853`（`getItems()` 的三个调用点 vs `Tree`/`Table` 的计数）；
  `research/facts-baseline.md` §4 容器/成员读法表与 `ui.tree 7` 实测结构。
  **2026-10-06 更正**：在 CCS 12.8 上做的全量树转储里 `TreeItem text=` / `TableItem text=` **零命中**
  （复跑：对任一 `ui.tree` 输出 `grep -c "TreeItem text="` ⇒ 0）。本行此前把 `TreeItem` / `TableItem`
  与前三者并列成「能读到」，与实际不符 —— 故改判：**读得到的是它们的数量，不是内容**。

### A4 桥写面四类（各有回读差）
- **能力**：开厂商视图（5 个逐个 added：views 8→9→10→11→12→13）、关视图（13→12→…→8，`stillOpen=False`；此处 `…` 表示逐个递减）、切透视图（id 如实变化）、开文件进 CDT 编辑器（editors 0→1→2，class=`org.eclipse.cdt.internal.ui.editor.CEditor`）。
- **证据**：`research/facts-baseline.md` §5 「已通过的写路径」表；`prd.md` F4。

### A5 跨产品复现
- **能力**：同一套技术对 CCS 12（Eclipse 4.23 / JRE 11）复现成功，不只 GS32（4.30 / JRE 23）。
  **两个 target 各自跑通全量门禁** —— **当前数字以 §5.2 / §5.3 为唯一权威**：
  `verify --all` 实测（**28 用例**，2026-10-09 重跑）**GS32 26 PASS + 2 SKIP / 0 FAIL**（rc=0）；
  **CCS12 列待重跑** —— 旧快照（24 PASS + 1 SKIP / 1 FAIL）已按 §13.8 撤下，理由与复跑命令见 §5.2 合计行
  （`--all` 不按 target 过滤 ⇒ 用例集 +1 后该列也必须同批重跑）。
  那条已归因的 FAIL（`input.fixture` 的 `key`）属**平台版本 / SWT 派发行为**（§5.3），**未结案 0 条**。
  （比旧快照多 `realflow.build_artifact` 与**两条板级用例** —— 见 §5.2 / §5.4。）
  > ⚠️ **本节此前那张旧表已于 2026-10-02 作废 —— 按 §13.8，只留指针，不留作废的数字。**
  > 作废原因：那是 **CCS 腿双 target 化之前**的快照，与现在两条腿都跑满 26 用例的事实不符
  > （`read.console` 两侧同因 SKIP），两张表并存在同一文件里属自相矛盾。
  > **逐条对照与归因见 §5.2 / §5.3。**

- **兼容矩阵**（五项列；**A5′ 要求的六列版见 §5.1** —— 多「厂商命令 id 清单」一列）：

  | 列 | gs32（GS32_Studio v1.2.5.2） | ccs12（CCS 12.8.1） |
  |---|---|---|
  | 平台版本 | Eclipse Platform **4.30.0** | Eclipse Platform **4.23.0** |
  | JRE 模块数 | **30**（JustJ JRE 23.0.2） | **55**（JRE 11.0.13） |
  | 命令服务 bundle 版本 | `org.eclipse.ui.workbench` **3.131.0** | `org.eclipse.ui.workbench` **3.125.0** |
  | 厂商命令数 | `com.gs` **7**（总 666） | `com.ti` **115**（总 807） |
  | 必须重编的产物 | `eclipse-ctl.bridge_0.2.0_gs32.jar`（class-file **61** = Java 17） | `eclipse-ctl.bridge_0.2.0_ccs12.jar`（class-file **52** = Java 8） |

  > **同一份源码、两个字节码级别**：gs32 是 17；ccs12 是 **8**（见下）。
  > 两个 jar **按 target 命名并存**（此前同名会互相覆盖），`doctor` 会校验 jar 内 class-file 级别
  > 与目标声明的 `java_target` 一致。
  >
  > **ccs12 的级别是 8，不是 11**（2026-10-06 改）。该树**不带 JDT**，它唯一的编译器来自**同产品**的
  > XDCtools 组件（`<ccs_root>/xdctools_*/packages/xdc/shelf/java/ecj.jar`，`_find_ecj` 向上两层找到），
  > 而那份是 **ECJ 3.14.0**：`-source/-target` 上限 9，`-source 11` 直接 `rc=255`。
  > 8 是任何候选编译器都能发的级别；桥源码零 Java 9+ API（常量池扫描），降到 8 无功能损失。
  > **级别是 target 的属性、不由「发现了哪个编译器」推导** —— 否则同一 target 换台机器产出不同字节码，
  > `doctor` 的 `class-file == java_target + 44` 这条精确判据就失去意义。

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
  | 点**不存在**的控件 | 文本 | `act_click_button`（库） | ✅ **退出码 1**（存在控件为 0） | **证伪** |
  | 坐标 → **按钮 HWND** | client 坐标 | `WM_LBUTTONDOWN/UP`（`0x0201`/`0x0202`） | ✅ 标题 → `GO n+1`（**有效**） | 定论记录 |
  | 坐标 → **顶层 Shell**（同一坐标、同一消息） | client 坐标 | 同上 | ⚠️ 标题**不变**（**无效**） | 定论记录（**对照组**） |
  | 坐标 → 空白 (5,5) | client 坐标 | 同上 | ✅ 标题**不变** | **证伪** |

  > **②a vs ②b 是本域最有价值的一条**：两条**坐标相同、消息相同**，只差**收件人** —— 发给按钮自己的
  > HWND 有效，发给顶层 Shell 无效（`PostMessage` **不做命中测试**，顶层窗不会把落在子控件区域的
  > 鼠标消息转给子控件）。⇒ **决定成败的是「寻址」，不是「SWT 不认合成输入」。**

  **寻址纪律**（`design-project.md` §18.3）：**命中 0 或 >1 一律失败**（fail closed），不允许「挑第一个」——
  否则同名 `&Save`/`&OK` 会**静默点错**。三个原语**不带 `yes=True` 时只返回 `DRY-RUN …`**（§16.2 的口径）。

  **库入口**（`ctl run` 脚本命名空间；`deliverable-shape.md` C3 / R10′.1「只有一个门」）：
  `act_click_button(text, case=None, title=None, yes=False)`（文本寻址）/
  `act_send_keys(key, title=None, class_="Edit", index=None, yes=False)` /
  `act_set_text(text, title=None, class_="Edit", index=None, yes=False)`（后两者按**类名** + 可选**序位**寻址）。
  命令面定义见本仓 `python -m ctl --help`（实现）与 `protocol.md`（对外形状）—— 两者都在本仓闸门
  `_doc_command_consistency` 的扫描范围内；`design-obs-ux.md` §14.3 已降为**历史设计记录**（2026-10-04，
  `deliverable-shape.md` C8：闸门必须能看见它守的东西）。`act` 子命令 **2026-10-04 已整体删除**
  （现在它是未知子命令：`ERR notfound no such subcommand: act`）。

  **寻址档位现状（2026-10-04）**：**类名**那一族支持「类名 + 序位（`index=`）」—— `index=` 是「命中 >1」时
  **唯一**的显式解药（不给就 fail closed）；**标签**那一族（`act_click_button`）**要求标签唯一**，
  产品面不再暴露序位（底层 `tools/win-click-button.ps1` 的 `-Index` 仍在）。
  **「路径」已裁决不做**（见 N11），且**参数本身已随子命令消失**：
  它不是本层的寻址形态（本层打的是 **Win32 子窗**，不是 §18.3 引文里那个**SWT 控件树**的下标路径）。

  **已修（2026-10-02）**：下层 `tools/win-click-button.ps1` 曾**违反上面那条寻址纪律** ——
  「命中 0」只打印 `no visible Button matching` 而 **`exit 0`**（静默成功），
  「命中 >1」**静默点第一个**。现改为 **0 命中与 >1 命中都 `exit 1`**（后者列出候选）。
  寻址层本来就是这个契约（`ctl/run.py::_click_button` 先 `-ListOnly` 自检），这次是**下层工具对齐上层**，
  免得直接调工具的调用方（如 `ctl/screen.py` 的模态框处置路径）把「没点到」读成「点到了」。
- **证据**：原语表七行逐条实测 —— `research/p6-input-fixture-2026-10-01.md` §2（六条断言首次实测）、
  §5（下层工具三态）、§7（夹具 v2 五类控件）；下层工具 fail-closed 三态另有 `facts-runtime.md` §12
  （唯一命中 `rc=0` ／ 0 命中 `rc=1` ／ >1 命中 `rc=1` + 候选）。**在真 IDE 主窗上的适用面见 §A6b-2。**
- **序位的端到端证据（2026-10-04，`implement.md` P6.3）**：对**真模态 `#32770`**（Abort/Retry/Ignore 三个真
  `Button`，由一次性测试进程持有）逐个跑通 —— 文本唯一 ⇒ `rc=0` 且**点到 Abort**（Harness 退出码 `3`）；
  文本 0 命中 ⇒ `rc=1` **不点**；文本 >1 不给序位 ⇒ `rc=1` + 3 条候选**不点**；
  给序位 `1` ⇒ `rc=0` 且**点到 Retry**（退出码 `4`）；序位 `2`（不给文本）⇒ 点到 **Ignore**（`5`）；
  序位 `9` ⇒ `rc=1 out of range`。**退出码 3/4/5 分别指认了被按下的那一个按钮** ——「动作 → 回读差」闭环。
  当时经 CLI 门驱动；门拆除后**同一套判据**落在寻址层（`tools/win-click-button.ps1` 的 `-ListOnly` 自检 +
  `-Index`，与 `tools/win-send-input.ps1` 同构）由 `ctl/run.py` 调用。

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

#### A6b-2 真 IDE 工作台的控件清单（2026-10-02 实测，**改变了 P6.6 的可行性**）

对运行中的 GS32_Studio 实例（`gs32-verify`，pid 15484）的**工作台主窗**（`SWT_Window0`，
标题 `ws - … - GS32_Studio`，hwnd `0x508CC`）做 `EnumChildWindows` 全量子窗枚举，类名分布：

| 类名 | 个数 | 说明 |
|---|---|---|
| `SWT_Window0` | 52 | SWT 的 `Shell`/`Composite`/`Canvas` 等（**部件与编辑器都在这层**） |
| `ToolbarWindow32` | 18 | 工具栏 —— 其**子窗数 = 0**，工具项**无独立 HWND**（见上表 `ToolItem`） |
| `msctls_progress32` | 4 | 状态栏进度条 |
| `Static` | 2 | 静态文本 |
| `Shell` | 2 | 子壳 |
| `Internet` | 1 | Welcome 视图的内嵌浏览器 |

**`Button` = 0，`Edit` = 0。**

⇒ **三条硬结论**：

1. **`act_click_button` 在真 IDE 的「主窗」上没有目标** —— 它按 `Button` 类的**文本**寻址，
   而工作台主窗里**一个 `Button` 也没有**。它的真实适用面是**对话框**（`#32770`，那里实测有
   `&Reset Perspective` / `&No` 这类真按钮）。
2. 同理，`act_set_text` / `act_send_keys` 的 `class_` 缺省是 `Edit`，**主窗也没有 `Edit`**
   ⇒ 文本输入/按键的**元素寻址**在真 IDE 主窗同样无目标。
3. 因此 **P6.6 要求的「用 `BM_CLICK` 点主窗一个无害按钮」在真 IDE 上不存在可寻址目标**。
   要按原意做，只能换成**坐标消息打到某个子控件 HWND**（`SWT_Window0` / `ToolbarWindow32`），
   或者换到**对话框**上 —— 后者会与"不得用命令弹框冒充输入场景"的纪律冲突。

**复跑命令**（只读，不点任何东西）：

```powershell
pwsh -NoProfile -File tools/win-click-button.ps1 -ProcId <instance-pid> \
     -TitleLike "ws - C:" -ListOnly   # 标题片段取唯一者，勿用 GS32_Studio（启动器控制台撞车）
```

- **证据**：夹具 v2 重测逐行见 `research/p6-input-fixture-2026-10-01.md` §7（含 `SysTreeView32` 上
  `TVM_SELECTITEM` 不产生 SWT 选中事件的**负结果**）；§A6b-2 的类名分布来自对运行中实例
  （`gs32-verify`，pid 15484）**工作台主窗**的 `EnumChildWindows` 全量枚举，复跑命令见本节末。

#### A6b-3 真 IDE 对话窗上的端到端四元组（2026-10-04 实测，**闭合 §6.7 / §6.8**）

上面三节证明的是「真 IDE **主窗**没有可寻址目标」。本节补的是另一半：**对话窗上有，而且产品库点得动、写得进、按得响**。
实例 `gs32-p67real`（pid 5924 / 端口 8911，不复用任何既有实例的端口），三条原语**全部走 `ctl run` 脚本命名空间**。

| 原语 | 真 IDE 载体与寻址 | 动作原文 | 可观测回读差 | 结论 |
|---|---|---|---|---|
| **点 `Button`** | `#32770` 标题 `Reset Perspective`；可见 `Button` ×2：`&Reset Perspective` / `&No` | `BM_CLICK sent to hwnd=0x715DA text="&No"` | `ui.shells` 3→2（框消失）+ 独立 `win-enum -Class "#32770"` **空** + `parts` **不变**（8 views）+ `ping OK` | **可行** |
| **写文本** | `#32770` 标题 `Preferences`；可见 `Edit` **3 个**（过滤框 `0x1E12F4` 在最前） | `sent WM_SETTEXT "proxy" -> hwnd=0x1E12F4` | 框内出现 `proxy` **且**左树按它过滤成 `General > Network Connections`（SWT `ModifyListener` 真跑） | **可行（行为级）** |
| **按键（非字符键）** | 同上 | `sent WM_KEYDOWN/WM_KEYUP vk=0x2E -> hwnd=0x1E12F4` | 框内 `proxy` → **`roxy`**，左树**清空** | **可行** |
| 按键（**可打印字符**，`X`） | 同上 | `vk=0x58` | **无**回读差（插入点在 0 也不该无变化 ⇒ 见下第 1 条） | **不可行**（范围限定） |
| 负例：不给序位 | 同上 | `act_set_text(…, index 缺省)` | `ERR badrequest ambiguous: 3 visible children of class 'Edit'`，**写之前**拒 | **fail closed 成立** |

**三条新增事实（写用例时必读）：**

1. **按键要分字符键 / 非字符键** —— `BACK`（`vk=0x8`）与 `X`（`vk=0x58`）都**无**回读差，
   但原因**不是同一个**：`WM_SETTEXT` 之后插入点在 **0**，`DELETE` 删掉的正是**后面**那个字符
   （`proxy`→`roxy`）⇒ `BACK` 的"无效"是**无可删**（插入点位置）；而 `X` 在插入点 0 处**本应**插入字符。
   **`[INFERENCE]`（机制未单独验证）**：本层是 `SendMessage` **直达子窗 HWND**，消息**不进目标线程的消息队列**
   ⇒ `TranslateMessage` **从不运行** ⇒ **不生成 `WM_CHAR`** ⇒ 可打印字符不产生输入；`BACK`/`DELETE`
   属非字符键，由编辑控件自己的 `WM_KEYDOWN` 分支直接处理，故生效。
   ⇒ **范围限定：本原语对非字符键可行；可打印字符无效果** —— 要"打字"走 `act_set_text`，
   **不要**用 `act_send_keys` 逐字敲。没有 `DELETE` 做对照，会把"插入点在 0"误读成"按键原语不生效"（F9 的假阴性形态）。
2. **跨进程 `GetWindowText` 对 `Edit` 不回内容** —— 同一次子窗枚举里 `Button` 的文字读得到
   （`Apply and Close` / `Cancel`），而刚被写过的 `Edit` 仍读回 `text=""`。
   ⇒ `tools/win-send-input.ps1 -ListOnly` **只许用于寻址**（类名 / 可见性 / 矩形），
   **不得当文本值的判据**；文本值与行为都走**像素**（`shot-window-pw.ps1`）。
3. **建议显式给 `title=`** —— `ctl/run.py::_window_title()` 只在 `ui.shells` 里**按面积**挑
   （先取最大的当主窗，再取其余里最大的）；**有多个非主窗时谁更大**才是那个不稳定因素
   （不是枚举顺序）。给标题就把寻址钉死在一次枚举结果上。

**复跑命令**（全流程；`<script.py>` 见任务侧 `research/probes/p67-step*.py`）：

```bash
python -m ctl run --target gs32 --run-id gs32-p67real --port <free> --no-start < <script.py>
python -c "print(act_click_button('&No', title='Reset Perspective', yes=True))"   # 经 stdin 喂给上面那条
```

- **证据**：`research/p67-realide-input-2026-10-04.md`（四元组 + 原始输出 + 复跑命令 + 收工四项 `[clean]`）；
  截图六张在任务侧 `research/shots/p67-*.png`（`PrintWindow`，**agent 自己读的图**）。
- **别读错 prior art**：`prd.md` §6.8 那条「真按键合成要求前台，否则拒绝」说的是 `Display.post`；
  本层的跨进程 `WM_KEYDOWN` **不需要前台**（实测该窗 `hwndFocus=0x1E12F4`，`GetForegroundWindow()` 是别人的窗）。

### A6c 输入与桥的相互影响（F11 / P6.6）

**分两面写，别混。**

| 面 | 状态 | 内容 |
|---|---|---|
| **机制** | ✅ **已实测（2026-10-04）** | 合成输入与桥的 `asyncExec` **走同一个 UI 线程**。判据：`SendMessage` **同步**往返 = 「UI 线程处理一次坐标点击」的耗时，5 次为 **4.684 / 0.492 / 0.431 / 0.296 / 0.244 ms**（第 1 次含首次跨进程附加开销）；`SendMessage` 只在目标窗口过程返回后才返回 ⇒ **消息确实被投递并在 UI 线程上处理**。 |
| **实测（空闲单击）** | ✅ **无争用** | 与点击**同时**、在**另一条连接**上以 ~25 ms 轮询：`sys.ping` n=254 p50=14.8 p95=17.9 max=27.6 ms；`ui.parts` n=230 p50=14.9 p95=20.6 max=27.8 ms（与基线同量级）；回读 `ui.shells`/`ui.parts` **逐字不变**（`shellCount=2`，无弹框）。⇒ 空闲点击的 handler 微秒级 ⇒ **观测不到** —— 原 `[INFERENCE]` 由此升级为实测。 |
| **实测（输入积压）** | ✅ **争用可测、且只在 UI 线程上** | 突发 3000 对 `WM_LBUTTONDOWN/UP` 到同一目标：`ui.parts` 出现**孤立尖峰 1142.5 / 1174.9 / 1227.9 ms**（3 次复跑，均在点击后 +483..+494 ms）；`sys.ping` 三趟 max **26.2 / 26.7 / 28.0 ms**；`--burst 1` 对照组无尖峰（max 35.0 ms，排除 CPU 饥饿与探针自身开销）。⇒ 与 F7 **同一个失败面**：只有**输入造成的 UI 线程工作量**才会拖慢 `ui.*`，**不碰 UI 线程的 `sys.ping` 不受影响**。 |

**复跑（2026-10-04 执行的配方）**：`install --target gs32 --run-id <id>`（端口先确认空）→ 枚举主窗子窗
（`research/probes/p66-coord-target.ps1 -ListOnly`）→ 选一个**显式声明的** `SWT_Window0` 目标 →
`research/probes/p66-contention.py [--sync | --burst N]`。**目标**：状态行消息区
`class=SWT_Window0 hwnd=0x2311CA rect=70,1527,2020x52`，客户区坐标 (101,26)（左端 5%、纵向居中；
状态行左侧消息区，无 contribution、**不弹框**）。**证据**：`research/batch2-2026-10-04.md` §3（子项 2.2）。

**⚠️ 2026-10-02 修正：本节要求的目标在真 IDE 上不存在。**
原文写「用 `BM_CLICK` 点**主窗一个无害按钮**」，但 §A6b-2 的全量子窗枚举实测：
**工作台主窗里 `Button` = 0、`Edit` = 0**（只有 52×`SWT_Window0` / 18×`ToolbarWindow32` /
4×`msctls_progress32` / 2×`Static` / 2×`Shell` / 1×`Internet`）。
⇒ 元素寻址的**文本输入/按键/点按钮**在真 IDE **主窗**上**都没有可寻址目标**；
它在真 IDE 的真实适用面是**对话框**（`#32770`，那里实测有 `&Reset Perspective` / `&No` 这类真 `Button`）。
这不是"做不到"，是**原写法选错了目标**：把「主窗」换成「某个子控件 HWND」或「对话框」，命题才可测。

**为什么当时标"未验"（不是遗漏，是刻意）**：把合成点击打进**真 IDE 的工作台**，等于**在不知会用户的情况下替它按下一个未知按钮**
——坐标落点不可预判，可能触发 `Open Perspective` 之类会弹框的操作。
仓库纪律是「点按钮 = 替用户做不可逆决定 → **只有用例显式声明时才点**」（`design-obs-ux.md` §13.2.2）。
在**没有声明目标**的前提下做这件事，与纪律直接冲突。**所以当时如实标为"未验"，而不是偷偷做掉。**

**2026-10-04 的解法（把命题改成可测且安全）**：目标不改按钮、不改对话框，改成**显式声明一个已知无害的
`SWT_Window0` 子控件 = 状态行消息区**，只发**坐标消息**（不是 `BM_CLICK`、不是未知控件）；并在发输入时
**同时**在另一条连接上量两条通道 —— 判据与结果见上表。四条纪律照旧：不碰会弹框的目标、不拿命令弹框
冒充输入、写方法要回读差、**点之前目标先声明**。
> 本节原先的第 1–5 步「验证入口」已被上表的**已执行配方**取代；其中第 2 步
> （`verify --case input.fixture` 先确认原语能力）仍然成立，见本节末「证据」。

- **证据**：`research/p6-input-fixture-2026-10-01.md` §2（六条断言首次实测）与 §7（P6.4 五类控件）；
  **用例化复现（2026-10-02，`target=gs32`）**：`python -m ctl verify --case input.fixture --target gs32` → **PASS**，
  证据逐条给出 ① `ctl-fixture`→`GO 1`、②a `GO 1`→`GO 2`、②b 同坐标同消息发顶层 Shell **不变**、
  ③ →`KEY 13`、④ →`TEXT P6CASE`、⑤ `act_click_button("&NoSuchButton", …)` **退出码 1**、⑥ (5,5) **不变**。
  夹具源码 `tools/fixture-swt/Fixture.java`；探针 `tools/fixture-swt/probe.ps1`（随夹具走，取证装置，不属产品）；
  用例 `ctl/verify/cases/input_fixture.py`（`requires_bridge=False`，自带夹具启停）。
- **证据（P6.6 实测，2026-10-04，run `gs32-p66b`）**：`research/batch2-2026-10-04.md` §3（子项 2.2）；
  探针 `research/probes/p66-coord-target.ps1`（`-Sync` / `-Burst`）与 `research/probes/p66-contention.py`；
  该实例的起停四件（端口先空 / `bundle id` 比对 / `--stop` 四项清洁）见同档 §1。

### A7 观测装置 · 截图
- **能力**：`tools/shot-window-pw.ps1`（`PrintWindow` + 先 `SetProcessDPIAware`）为**主通道**，不受遮挡、不受 DPI 虚拟化影响；OCU 的 `get_app_state(include_image=true)` 为**备用**（小窗可用）。
- **证据**：`design-obs-ux.md` §13.1 两条通道表；`research/facts-baseline.md` §11.1（rect 513×132 → 1154×296 的修法实测）。
- **A9 自证实例（自己看图 → 改变动作，R9）**：模态框处置链路上有一处**完整**的实例 ——
  ① 发 `cmd.run org.eclipse.ui.window.resetPerspective` 后**超时**；② 先 `win-enum.ps1` 枚举拿标题，
  再 `shot-window-pw.ps1 -TitleLike "Reset Perspective"` **自己拍下图**（用例归档
  `<run_root>/<run_id>/shots/resilience.modal-reset-*.png`，GS32 **14057 B** / CCS **28119 B**）；
  ③ **从图里读出**标题 `Reset Perspective` 与两个按钮 **`&Reset Perspective` / `&No`**；
  ④ 据此把动作从「盲发 `WM_CLOSE`」改成**按下图上读到的那个按钮**（`BM_CLICK`）——
  `applied=yes … gained=['org.eclipse.ui.views.ProblemView']` 就是这次改变的**后果**。
  · 全报告**无**把观察外包给用户的措辞：`grep -nE '请用户截图|你截图|截图给我|麻烦你截图|请反馈'` 在
  `boundaries.md` / `README.md` / `skill/SKILL.md` / `TROUBLESHOOTING.md` 上**零命中**（实测 2026-10-02）。

### A8 热装即起 + 桥常驻
- **能力**：控制台 `install file:<jar>` → `start <id>` 即起；桥被 OSGi 记进**当前使用的配置区**（`configuration/org.eclipse.osgi/<id>/`），跨工作区、跨重启都在；`uninstall <id>` 或删该目录后 `-clean` 可清。
- **证据**：`research/facts-baseline.md` §7；`prd.md` F6（出处 `route-comparison.md` §9.16）。

### A9 命令表反查与自省（**2026-10-02 实测收口**）
- **能力**：`ctl commands find --text <S>` 按 UI 文字反查命令 id；`ctl commands export --full` 导出**六字段**机读表
  （`id / name / category / parameters / handled / vendor`），产物 `commands.json`（`COMMANDS.md` 由 `tools/make-commands-md.py` 同源渲染）。
- **反查判据（实测原文，GS32 实例）**：`find --text "Reset Perspective"` →
  `org.eclipse.ui.window.resetPerspective  Reset Perspective`；该 id 送 `cmd.run` 后**回读差非空**：
  ```
  1. request sent='cmd.run org.eclipse.ui.window.resetPerspective'
  2. initiator answered 16.05s -> ERR timeout … read back before retrying
     applied=yes (apply): …ProblemView before=False after=True | lost=[] gained=['org.eclipse.ui.views.ProblemView']
  ```
  ⇒ 命令发出 → 模态框被答复后**副作用真的落地**，回读差非空（这条同时是 A4-⑥「超时 ≠ 未生效」的例子）。
- **⚠️ 判据名称修正（按实测）**：A8 原文写「`ui.persp` 回读差非空」，但 `ui.persp` 报的是**透视图注册表**
  （`perspectives=5`，不随 reset 变），真正敏感的回读是 **`ui.parts`**（活动透视图的视图布局）。判据据此改名，
  不改成「两条都测」—— 否则就是拿一个结构性不敏感的读法凑数。
- **证据**：本文件 §5.1；`research/facts-baseline.md` §3；产物 `commands.json`（GS32：**666** 条 × 6 字段）。

### A9b `getDefinedCommandIds()` 漏项**已闭合**（2026-10-02；原 §3 的 U11）
- **能做**：桥的 `cmd.list` 除 `definedCommandIds`（只含**有 `<command>` 声明**者）外，另报 `handlerOnly` 块，
  **实测正好命中了点名的那一条**：GS32 `handlerOnly registry=ok total=1` → `com.gs.chipsetting.commands.opthandler`
  （厂商 OptionBytes）。⇒ 「有 handler 无声明」这个**结构性盲区已闭合**。
- **客户端侧（2026-10-02 修）**：`commands.json` 现在把 `handler_only` 作为顶层字段**单独携带**（不混进 `commands`，
  因为它们 `cmd.query` 会 `notfound`，拿不到 name/category）。此前导出器把它整块丢掉。
- **同时修掉的静默丢数据**：id 块改为**按两行签名行框定**（头 `ICommandService …`、尾 `definedCommandIds …`），块内逐行照抄。
  原先的启发式兜底要求 id **含点**，于是 CCS 的 `redo` / `undo`（Eclipse 遗留短 id，**不带点**）被静默吞掉
  —— 客户端报 `returned=805` 而桥说 `returned=807`。修后两侧实测：GS32 `666/666`、CCS `807/807`，均 `truncated=false`。
  教训同 `measurement-hygiene.md` §13.4：**按签名字段定位，不按启发式**。
- **证据**：`research/facts-baseline.md` §3（桥侧 `cmd.list` 原文）；`ctl/__main__.py:_fetch_command_ids`。

### A10 环境隔离：**一份安装树跑多实例**，且**源树零触碰**（原 §3 的 U1 / U4，2026-10-01 实测闭合）
- **能做**：起进程时给 `-configuration <run_root>/<run_id>/configuration`（+ `-data <run_root>/<run_id>/ws`）**生效** ——
  Equinox 建的是**「链接配置」(linked configuration)**：运行区 `config.ini` **全文只有 3 行**，
  `osgi.sharedConfiguration.area` **指回源树**；运行区仍被真用（`org.eclipse.osgi/.manager/` 会建出来）。
- **能做的第二半**：同一 `source_dir` **可同起两实例** —— 顺序（8877 / 8878）各自 `sys.ping` 通；
  **真并行**（两实例同时在驻）各自 `ui.parts` 返回 **9** 行视图，且**互相探对方端口也通**。
- **源树零触碰**：一次完整启动（Gogo 就绪 → `install` → `start` → 探活 → 优雅停机）之后，对
  `<source_dir>/configuration/` 递归清单（相对路径 + 大小 + `mtime_ns`）取 SHA-256，**前后完全一致**
  （`59e7ec61733f4e1c` / **232** files；两实例各一次、**共 4 次比对全一致**）。新装 bundle 的存储落在
  `<run>/configuration/org.eclipse.osgi/<bid>/<gen>/bundleFile`，**源树区没有对应目录**。
- **⇒ 不回退「每实例一份副本」**（`design-project.md` §16.1 的回退分支本次**未被触发**）；
  **⇒「同时只能用一个实例」是旧产物限制**（端口写死 / 配置区互锁 / 单线程 accept 三者都已改），**不是桥的固有性质**。
- **⚠️ 两条会把判定带偏的坑（实测踩到）**：
  ① `<run>/configuration/config.ini` 里**永远没有 `eclipse.product`** —— 拿「新 config.ini 有没有产品值」判隔离**必得假阴性**
     （原 P0.4b 判据 1 就是这样，已按实测改写）；
  ② **陈旧 jar 会把「端口没生效」伪装成「隔离失败」**：旧 `livebridge_3.0.0.jar` 类文件里只有字面量 `8777`、
     没有 `ctl.port`，用它跑隔离实验时桥仍监听 `8777` ⇒ 判任何隔离/端口结论前**先确认 jar 与源码一致**。
- **证据**：任务侧 `research/p04b/README.md` §1（判定原文 `C1=True  C2a=True  C2b=True  C3=True  => 生效`）
  与**原始产物** `research/p04b/p04b-full.json` / `p04b-pair.json`；`research/facts-runtime.md` §7.1。
- **复跑**（在两个脚本所在目录即任务 `research/` 下跑；脚本自带起停与指纹）：
  ```bash
  python p04b/p04b-probe.py --stage full --jar <repo>/bridge/dist/eclipse-ctl.bridge_<ver>.jar \
    --log --report p04b/p04b-full.json
  python p04b/p04b-pair.py  --jar <repo>/bridge/dist/eclipse-ctl.bridge_<ver>.jar \
    --report p04b/p04b-pair.json
  ```

### A11 `cmd.list` 空前缀 = **全量导出**（原 §3 的 U5，2026-10-01/02 实测闭合）
- **能做**：`cmd.list` 空前缀**全量**返回命令 id，并如实报 `total` / `matched(prefix=)` / `returned` / `truncated`；
  **只在显式 `--limit <n>` 时**才截断（`ui.viewids` 同改）。旧产物的 `if (n <= 300)` 硬截断**已去掉**。
- **两侧实测原文**：
  ```
  definedCommandIds total=666 matched(prefix=)=666 returned=666 truncated=false      ← GS32
  definedCommandIds total=807 matched(prefix=)=807 returned=807 truncated=false      ← CCS 12
  ```
  ⇒ `returned == total` 且**远大于**旧产物的 300（GS32 666 / CCS 807）。
- **客户端同源产物**：`ctl commands export [--full] --json` 的载荷带 `total` / `returned` / `truncated` 三字段
  （`handler_only` 另列，见 §A9b）。
- **⚠️ 两个解析陷阱（实测已修）**：① `total=` **不在行首**（它是 `definedCommandIds total=666 …` 的第二个 token），
  按行首匹配则 `truncated` **恒 `False`**；② id 块必须**按两行签名行**框定（头 `ICommandService …` / 尾 `definedCommandIds …`），
  旧的「含点」启发式会把 CCS 的 `redo` / `undo`（Eclipse 遗留短 id）**静默吞掉**（客户端 805 vs 桥 807，且**只在一侧显形**）。
- **证据**：任务侧 `research/p0-gate.md:48`（`total=666 returned=666 truncated=False commands=666`）、
  `research/p1-gate.md:64`、`research/realflow-scenario-2026-10-02.md:897`（CCS `807/807`）；
  契约见 `protocol.md` §8。
- **复跑**（需活实例；`--json` 输出可直接 `json.load`）：
  ```bash
  python -m ctl commands export --full --json --run-id <id> \
    | python -c "import json,sys; d=json.load(sys.stdin); print(d['total'], d['returned'], d['truncated'])"
  ```

---

### A11b `ui.tree` 的 **shell 面**：默认只读「最大的可见 shell」，`--shell` 把它放宽（2026-10-05）

- **能力**：`ui.tree [depth] [--shell <all|index|title>]`。**默认行为一字未改**（仍是最大的可见 shell）；
  `--shell` 给三条新路：`all` / `Display.getShells()` 下标 / 标题子串（命中 0 或 >1 一律 `ERR`，**不猜**）。
  每个 shell 输出一行 `root` 头，带 `vis=` 与 `shell=<i>/<n>`（`protocol.md` §7.1）。
- **为什么需要**（**实测量到的盲区**）：e4 的 `PartRenderingEngine` 把**尚未渲染**的部件停在不可见的
  `PartRenderingEngine's limbo` shell 里。同一时刻、同一实例，**默认 `ui.tree` 任何深度都读不到它们**：

  | target（2026-10-05，jar 0.2.0） | 默认（可见 shell） | `--shell limbo` | `--shell all` |
  |---|---|---|---|
  | GS32（Welcome 最大化；编辑器已开） | 138 行 · `StyledText` **0** · `Tree` **0** | **117 行 · `StyledText` 1 · `Tree` 3** | 255 行（`138+117`，逐行无多无少） |
  | CCS12（编辑器 + 导航器已开） | 170 行 · `StyledText` 1 · `Tree` 1 | 38 行 · `Tree` 1 · `Text` 1 | 210 行（`170+38+2`，逐行无多无少） |

  GS32 那一列里，limbo 躺着的是 **8 个 `CTabItem`**：编辑器（`ctl_depth_fixture.c` 的 `StyledText`）、
  `Project Explorer`、`Outline`/`Build Targets`、`Problems`/`Tasks`/`Console`/`Properties` 四个部件的 `Tree`
  ——**都是部件内部的控件**，即「按部件读」这件事的实物。
- **边界（同刻实测）**：`--shell` **不解决**「部件没被渲染」这个前提 —— 它只是把**已经在读的那棵树**
  从「一个可见 shell」放宽到「指定 shell / 全部 shell」。部件→控件根的真映射仍要 e4（见 U7 的结论二）。
- **证据**：`protocol.md` §7.1；任务侧 `research/tree-p2-*.txt`（原始输出）；`ui.shells` 是寻址入口。

### A18 跨 run 自动回收（`lifecycle.auto_gc()`，2026-10-05 新增）

- **能力**：收工路径（`ctl uninstall` 与 `ctl run --stop`，后者复用同一条）在**拆除实例之后**按
  **target** 各自保留最新 **3** 个 run，其余目录回收；配置键 `auto_gc`（默认 `true`），
  环境变量 `ECLIPSE_CTL_AUTO_GC=false` 可关。
- **分组键**：`endpoint.json` 新增 `target` 字段（`ctl/client.py write_endpoint()`），分类走既有的
  `discover_endpoint()` 校验读。**老 run（无该字段 —— 实测改造前的存量 47/47 全部如此）不进任何组
  ⇒ 永不自动删**。
- **8 条护栏**（**①–⑤ 各有单测与变异**，M1–M6 见任务侧 `implement.md` §S7；**⑥–⑧ 只有实现、
  本轮无单测** —— 故本条**不**写成"逐条有测试"）：① 恒定 `skip_live`（活 run 不删，且**不暴露**
  `--force-live`）；② 当前 run 永不删（仍占一个保留位）；③ 判不出 target 的一律不删；
  ④ `keep < 1` ⇒ 不做 + warn；⑤ 任何异常 ⇒ **零删除** + warn（fail-closed：两阶段实现，
  先全部分类选择、再删除）；⑥ **绝不改变命令退出码**（回收不是清洁判据；目前由一次真实
  `ctl uninstall` 的 `rc=0` 验证，非单测）；⑦ 删了必报一行 stderr（无删除不报，
  `skipped_unclassified` 不报；同上，非单测）；⑧ 只碰 `run_root` 的直接子目录（与 `gc()` 同界）。
- **与手动刻意不同**：手动保持**全局** keep 且**照删**老 run —— 它是**唯一**能清那些无 `target`
  字段的老 run 的通道（`gc --help` 与 `gc()` 的 docstring 都写明这套分工）。
- **证据**：`ctl/lifecycle.py::auto_gc()`；`ctl/__main__.py::_collect_old_runs()`；
  `tests/unit/test_auto_gc.py`（8 例，期望值全是本文件字面量 —— `deliverable-shape.md` C10）；
  变异账本 M1–M6 见任务侧 `implement.md` §S7。

### A19 被 promote 的留档帧会自己报出来（`ctl/shadow.py::_capture`，2026-10-05）

- **能力**：一次写动作失败（`outcome=err` / `timeout`）或**出现对话框**时，那一帧被 promote（永不裁）；
  此前**没有任何一行**告诉调用方去哪看 —— 现在在**本层唯一的出声通道**（`warn()` → stderr）打**一行**：
  `WARN: shadow promoted frame <seq> (<原因>); see it: python -m ctl shadow --run-id <run> --seq <seq>`。
  **成功路径一如既往静默**（没 promote 就不打）。
- **指向"真有文件"的那个 seq**：像素与更早一帧相同时文件落在那一帧（`row["same_as"]`），
  指向一个没有文件的 seq 就是**死指针** —— 故取 `same_as or seq`。
- **与 `ctl/run.py` 的 `_auto_shot`（`:255-277`）是两个装置，不是两份实现**。`run.py:171-172` 原文写着
  "The shadow frames (`tools/win-probe.ps1`, `<run>/shadow/`) are a **different device**"：
  那条在**失败之后现拍**一帧、打的是 **`shots/`（证据）** 的路径，且只覆盖 `_watched` 包住的 **7 个** helper
  （`:308-317`）；这条打的是写动作**发出时**自动留的 **`shadow/`（留档）** 帧，覆盖**每一次被桥判为写**的动作
  （含 raw `run()` / `ctl shell` / CLI 门）。"当时那一刻"是留档独有的 —— `see()` 永远给不了。
- **护栏**：**不改**触发判据（`_promote_reasons`）与单 run 裁剪（`prune`）—— `design.md` §9 的"不动"照旧成立；
  **不新增命令面**（只用既有的 `python -m ctl shadow --seq N`）；帧仍**不进任何判据**（R5 构造性保证）。
  **与 A11b′ 不冲突**（A11b′ 原文，任务侧 `09-30-eclipse-ctl-project/prd.md:275`：
  「`--json` 输出可被 `json.load` 解析且 **stderr 为空**；制造一次错误时**诊断只走 stderr**」）——
  「stderr 为空」是**成功例**的要求（`implement.md:610-621`：`rc=0` ⇒ stderr 空；`rc=1/2` ⇒ stderr 有 `ERR`），
  而本行**只在失败/弹窗时**出现（成功路径实测 `stderr` 为空），**正落在"错误例"那一半**。
- **证据**：`ctl/shadow.py` 的 `_capture` 里 `if reasons:` 块；`tests/unit/test_shadow_promote.py`（3 例，
  期望值全是本文件字面量 —— `deliverable-shape.md` C10）。
  **变异账本 M1**（删掉该块）：`FAIL: test_a_failed_action_names_the_frame_on_stderr` +
  `FAIL: test_the_pointer_names_the_frame_that_owns_the_file` ⇒ `FAILED (failures=2)`；
  第三条断言"静默"的用例**保持绿**（它断言的是缺失，检测不到删除 —— 这正合 C12 要的形状）；
  恢复后 `ctl/shadow.py` sha256 `9620ef25` 逐字节回原值、`Ran 3 tests ... OK`。

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

### N9 `executeCommand(id, null)` 的 **lookup 上下文**不是它找不到 handler 的原因（**2026-10-05 修正**）

- **原条目（现被推翻一半）**：「用 `IHandlerService.executeCommand(id, null)` 驱动部件级命令
  （`org.eclipse.ui.edit.selectAll` **永远** `NotHandled`）」。
- **现在能说清的是三条**（2026-10-05 实测，两侧，jar 0.1.0 与 0.2.0 同结论）：
  1. **不是「永远」**。窗口级的 `IHandlerService` **会**路由到活动部件自己的 handler ——
     同一个命令 id 有三种结局，取决于**哪个部件是活动部件**、以及它的 handler 是否 enabled：

     | 状态（CCS 12.8.1 / GS32 1.2.5.2 同刻实测） | `Command.isHandled()` | 结局 |
     |---|---|---|
     | 编辑器是活动部件 | `true` | **`OK`**（`executeCommand returned: null`） |
     | 视图是活动部件、该部件无 selectAll handler | `false` | `ERR unhandled` |
     | 视图是活动部件、handler 找到了但 `canExecute=false`（GS32 上导航器活动时） | `true` | **`ERR disabled`** |

     第 2、3 两行是**同一个靶**在同一台机器上的两种失败 —— 这正是 `unhandled` / `disabled`
     **不可混**的活例（`protocol.md` §3）。
  2. **换 lookup 上下文不管用**：把来源从「窗口级」换成「活动部件站级 + 窗口级回落」后，
     同一个状态下的结局**逐条相同**（Problems 视图活动时两级都返回**同一个**
     `org.eclipse.ui.internal.views.markers.MarkerSelectAllHandler`；导航器活动时两级都 `not-handled`）。
     ⇒ 这不是 lookup 的问题，**已不投入**（`M1` 已否决并回滚）。
  3. **`null` 事件不是拦路虎**：上面第 1 行的 `OK` 就是**原样的** `executeCommand(id, null)` 跑出来的
     ⇒ 「传 `null` 事件」本身不构成障碍，`M2`（构造带 selection 的 `ExecutionEvent`）**没有可测的缺口要补**，
     本轮不投入。
- **仍然成立的部分**：`org.eclipse.ui.file.saveAll` 的 `NotEnabledException` 条件是「有**脏**编辑器」，
  不是「有编辑器」——两者不可混。
- **证据**：任务侧 `research/p3-selectall-terminal.txt`；另 `errors.unhandled` 用例的 docstring 早就把
  `selectAll` 记为「focus-dependent，只作证据不作断言」（2026-10-01 实测过一半）。

### N9′ 部件→控件根（part → widget）没有非 e4 的公共入口

- **不能做**：用 `IWorkbenchPart` 拿它自己的 SWT 控件根 —— 公共 API 里**没有** `getControl()`
  （`IWorkbenchPartSite.getShell()` 只到 shell；`ISelectionService` 给的是模型对象）。
- **能用什么**：e4 侧（`MUIElement.getWidget()` 一类）—— 那是 `prd.md` §6.3 的领域，本轮**停手**。
- **不需要它的理由**：`ui.tree <N≥15>` 已经能读到部件内部的控件（见 U7），所以这条**不是**读不到的原因。
- **证据**：任务侧 `research/p3-selectall-terminal.txt` 的结论段；`boundaries.md` U8（e4 层仍挂未验证）。

### N10 桥没有 dry-run 概念
- **不能做**：指望桥自己「先空跑一遍」。dry-run 只能落在**客户端**，且**只作用于会改 IDE 状态的方法**（`cmd.run` / `cmd.runp` / `ui.open` / `ui.close` / 元素寻址的三个库原语）；只读方法默认真发，dry-run 也不阻止建立连接。不带 `--yes` 时 CLI **打印 `DRY-RUN <line>` 到 stdout 并以退出码 0 结束**；库原语不带 `yes=True` 时**返回 `DRY-RUN …`**——两条路都**桥侧零请求**。
- **证据**：`design-project.md` §16.2（含审计修正：「否则 `ctl parts` 会变成空操作」）；`--yes` 只挂在 `cmd` / `open` / `close` 三个写子命令上（元素寻址原语用库参数 `yes=True`）。

### N11 「路径（下标）」**已裁决不做**；「序位（`index`）」**已实现**（2026-10-04）
- **不能做**：用「下标路径」寻址控件。**现在连参数形态都没有** —— `act` 子命令 2026-10-04 被整体拆除
  （`deliverable-shape.md` C3 / R10′.1：只有一个门），库函数签名里没有它
  （`act_click_button(text, case, title, yes)` / `act_send_keys(…, index=None, …)` / `act_set_text(…, index=None, …)`）；
  拆门之前它在 parser 里也只是被**显式拒绝**，从未实现。
- **为什么不做（裁决，不是「没空做」）**：`design-project.md` §18.3 把「路径（下标）」列为首选，出处是调研里
  **SWT 控件树**的下标路径（`routes/eclipse-mcp-vogella.md:58`，`0/i2` 那种，由**IDE 进程内**读 SWT 对象模型得到）。
  而本层是**进程外**的：它通过 `EnumChildWindows` 打 **Win32 子窗**，两者**不是同一棵树** ——
  §A6b-2 实测工作台主窗的 Win32 子窗里有 **52 个 `SWT_Window0`**（SWT 的 `Composite`/`Canvas` 共享同一窗口类），
  即某一个 SWT 控件的「下标路径」在 Win32 侧无从计算，而 Win32 同级序位**没有任何稳定性契约**
  （`EnumChildWindows`/`GetWindow(GW_HWNDNEXT)` 的顺序是实现细节）。要**诚实**地支持 §18.3 那个语义，
  只能在**桥里**新增一个「SWT 控件路径 → 目标」的读方法（协议面变更）—— 那是另一件事，不在本层这一档。
  ⇒ 在本层**硬造**一个 Win32 版「路径」就是「名字与理由都换了的新 flag」，故**不做**。
- **改做**：`index`（**「类名」命中 >1 时的显式序位**）—— 由 `act_send_keys` / `act_set_text` 暴露
  （`act_click_button` 的标签寻址要求**唯一**，不再有序位档）。真模态上端到端实测见上（§A6 末条：
  文本唯一 / 0 命中 / >1 不给序位 / >1 给序位，分别得到「点到 Abort(3)」「不点」「不点」「点到 Retry(4)」）。
  **原位序只在同一会话内稳定**，故**永不自动挑**。
- **证据**：产品侧 `ctl/run.py`（`_click_button` / `_send_input`：寻址唯一性 + `-ListOnly` 先自检）、
  `tools/win-click-button.ps1` 的 `-Index`、`tests/unit/test_act_addressing.py`（13 例，含「工具自身的 markup
  不算命中」「不可见控件不参与计数」「标签里的一个换行不是两个控件」三条回归）；任务侧 `research/` 的 P6.3
  实测记录与 `design-project.md` §18.3 的原文出处。
- **本条的旧表述**（「`--index`/`--path` 都未实现，差别只是 index 也缺」）**已作废** —— 那时 `--index` 确实未实现。

### N17 自动回收**不碰**判不出 target 的 run，也**不碰**帧

- **不能做**：① 指望收工时的自动回收把**老 run**（`endpoint.json` 没有 `target` 字段，或该文件
  缺失 / 损坏）清掉 —— 这类一律进 `skipped_unclassified`，**目录原样留着**。这是**刻意的**：
  它的失效方向必须是「少删」，因为猜错就是删错（`design.md` §2 实测：按 run id 前缀猜 target
  的简单规则在 47 个里只认出 **19** 个）。要清它们只有手动那条**全局**通道。
  ② 指望自动回收按 **`shadow/` 里的帧**决定删谁 —— 它**只读** `endpoint.json` 的 `target`
  与目录 mtime，**从不读帧**（R5：帧不进判据）。
- **代价（接受）**：`unclassified` 组的磁盘占用会**缓慢增长**；手动通道是完整出口。
- **证据**：`ctl/lifecycle.py::auto_gc()` 的两阶段实现与 `skipped_unclassified` 桶；
  `tests/unit/test_auto_gc.py::UnclassifiedImmunityTest`（四种判不出形状，`keep=1` 下仍免疫，
  变异 M3）；构造性判据 `grep -rn shadow ctl/verify ctl/screen.py` 零输出。

### N18 回收通道**没有「豁免某个 run」的入口**（2026-10-05）

- **不能做**：让 `ctl gc` 保住一个**具名**的 run。保留只有两个旋钮 —— `--keep <n>`（**全局**、
  按目录 mtime 留最新 n 个）与恒定的 `skip_live`（活实例不删）。**没有** `--protect` /
  `--keep-name` / 「引用保护清单」这类入口；`endpoint.json` 的 `target` 字段只被**自动**回收
  （`auto_gc()`）用来分组，**手动那条路不读它**（见 N17 与 `design.md` §3.6：
  手动刻意保持「全局 + 照删老 run」）。
- **代价（接受）**：被文档当作**证据**引用的 run，只能靠「它正被活实例持有」或「人工把它移出
  `run_root`」存活 —— **活实例一退出，下一次 `ctl gc --yes` 就会删掉它**。
  2026-10-05 实测清盘（6.54 GB → 1.85 GB，删 35 个 run）：`gs32-handoff` / `gs32-handoff2`
  是**人工临时移出 `run_root`** 才活下来的；清完复跑 `python -m ctl gc`，它们**仍在
  `would remove` 名单内**（同一份输出里另有 7 条靠活 listener 被 `skip_live` 挡住 —— 那个
  「保护」随实例退出即失效）。
- **证据**：`ctl/lifecycle.py::gc(run_root, keep, dry_run, skip_live)` 的签名**只有这四个参数**
  （2026-10-05 实读）；`python -m ctl gc --help` 无任何保护类选项；清盘后 dry-run 原始输出
  含 `would remove … gs32-handoff2 / gs32-handoff`。
- **未定**：要不要加 `--protect <run_id>`（或一份引用清单）—— 那属**新能力**，**用户未拍板**；
  本条只记「今天没有它」。反向约束同时成立：手动通道是**唯一**能清老 run 的出口（N17 /
  `design.md` §3.6），加保护时**不得把那个出口关掉**。

---

## 3. 未验证

> 本节每条的形态：**不是**「能做」也不是「不能做」，**禁止当结论用**。
> **例外（转指条）**：**已实测闭合**的原条目（`U1` / `U3` / `U4` / `U5` / `U6` / `U10` / `U11` / `U13`）在这里只留**指针**，
> 内容与证据在 §1 / §2 —— 不要让一条已验证的结论继续挂在「未验证」区。

### U1（**已闭合 2026-10-01 → 见 §1 的 A10**）
- 原条目：「同时只能用一个实例」是**旧产物限制**，不是桥的固有性质 —— 三个可能成因（端口写死 `8777` /
  Equinox 配置区互锁 / 单线程 accept）已各自改掉，但效果当时未验。
- **已闭合**：一份安装树**可同起两实例**（顺序 + **真并行**都跑过），两实例交叉探活通；
  **不做**副本回退。详见 §1「A10 环境隔离」。
- **证据**：§1「A10」的三项实测（`C1/C2a/C2b/C3 = True`，4 次递归清单 SHA-256 同值）；
  本条目**不再是「未验证」结论**，只作旧编号的转指。

### U2 坐标注入 / SWT 上的合成输入 —— **未证实**
- **未验证**：审计 3 次 `app_post` 全无变化，且审计原文明确「**不能**据此判定方法无效」；用户口径**决定不投入**（**不是**「已证伪」）。本条按缺口保留为「未验证」。
- **验证入口**：`design-project.md` §18.4 最小 SWT 夹具的 6 条断言，其中 **②**（坐标点同一位置）与 **⑥**（坐标点空白处必须无变化）即为把本条结掉的断言；构建/运行照 `design-project.md` §18.6，用例入口 `python -m ctl verify --group input --target gs32`
  （`fixture` **不是** target —— 实测 `python -m ctl verify --group input --target fixture` ⇒ `ERR notfound no such target: fixture`，rc=1；`python -m ctl targets list` 只有 `gs32` / `ccs12`。该组用例自带夹具、`requires_bridge=False`，`--target` 只用来挑**借哪套工具链**）。
- **证据**：`prd.md` §6.5（含「不投入是用户口径的决定，不是实验结论」）；`design-project.md` §18.2 第 2 行；出处 `09-30-gs32-no-gui-audit/research/ocu-coordinate-click.md §1`。

### U3（**已闭合 2026-10-04 → 见 §1 的 A6b-3**）元素寻址输入原语的**泛化**
- 原条目：点按钮 / 按键 / 文本输入三条原语，在**夹具**与**真 IDE** 两个作用域下是否可用
  —— 两个作用域**必须分开读**，勿混。
- **夹具侧 2026-10-01 已实测**（§A6 原语表）：`BM_CLICK` / `WM_KEYDOWN` / `WM_SETTEXT` **三条都通**；
  `Tree` 按树内坐标可行；`MenuItem` 根本不是窗口、`ToolItem` 无独立 HWND ⇒ 这两类改走**命令框架**。
- **真 IDE 侧 2026-10-04 已补齐**（§A6b-3）：点 `Button` / 写文本 / 按键（**非字符键**）三条
  **走产品库**在真 `#32770` 对话窗上跑通**且有回读差**；可打印字符**无效果**（范围限定，
  机制与"必须给 `DELETE` 做对照"见 §A6b-3 第 1 条 ⇒ 要打字走 `act_set_text`）；
  不给序位 ⇒ `ERR badrequest ambiguous` 在**写之前**拒（fail closed 实测成立）。
  ⚠️ **主窗仍没有可寻址目标**（§A6b-2 实测 `Button` = 0 / `Edit` = 0）—— 真实适用面是**对话框**。
- **验证入口**：夹具侧 `python -m ctl verify --group input --target gs32`（断言 ③ 按键、④ 文本输入；
  `input` 组用例自带夹具、`requires_bridge=False`，**不需要 `install`**，但 `--target` 仍须是**真实 target**）。
- **证据**：§A6 原语表、§A6b-2、§A6b-3；`prd.md` §6.7 / §6.8；
  任务侧 `research/p6-input-fixture-2026-10-01.md` §2 / §7 与 `research/p67-realide-input-2026-10-04.md` §1–§4
  （含 prior art：真按键合成走 `Display.post` 且**要求目标是前台窗口，否则拒绝**）。
- 本条目**不再是「未验证」结论**，只作旧编号的转指。

### U4（**已闭合 2026-10-01 → 见 §1 的 A10**）
- 原条目：运行配置区隔离（`-configuration`）是否生效 —— 生效前**不得**宣称「源安装目录零触碰」。
- **已闭合**：**生效**（Equinox「链接配置」）；源树 `configuration/` 递归清单 SHA-256 前后同值（232 files）；
  桥的新装存储落在运行区、源树区无对应目录 ⇒ **不回退 `--copy`**。
- **证据**：§1「A10」；任务侧 `research/p04b/README.md` §2（链接配置的两个连带后果）。
  **注意**：`p2/` 的落位**有时序**（启动早期查是 `false`、停机后是 `true`）⇒ **不要拿它当实时判据**。

### U5（**已闭合 2026-10-01/02 → 见 §1 的 A11**）
- 原条目：`cmd.list` 的全量导出（当时「修正已在源码落地，运行期未验」）。
- **已闭合**：两侧真跑过 —— GS32 `total=666 returned=666 truncated=false`、CCS `807/807`，`returned == total`。
- **证据**：§1「A11」；任务侧 `research/facts-baseline.md` §3（桥侧 `cmd.list` 原文）。
  **旧验证入口已废**：`python -m ctl commands --json` 现在**不是合法命令**（`commands` 需 `export`/`find`）——
  改成 `python -m ctl commands export --full --json --run-id <id>`（见 §A11 的复跑段）。

### U6（**已闭合 2026-10-01 → 见 §2 的 N16 与 §3 的 A13**）
- 原条目：除「单连接串行」外的并发行为未测（多连接同时发、长请求期间的第二请求）。
- **已闭合**：P3.5 **两档并发探针 13/13** —— 档 1（一条连接卡住，另连接 `sys.ping` 0.01 s / `ui.parts` 0.02 s /
  `ui.tree` 0.00 s 全通，同刻模态框仍在屏）；档 2（连接槽边界：`1..8` 全功能 / `9..12` 保留槽只答
  `sys.ping`/`sys.env`/`sys.help` / `≥13` 拒）。
- **落点**：「不能做」半在 §2 的 **N16**（连接槽是单点容量）；「模态框不传染」在 §3 的 **A13**。
- **证据**：任务侧 `research/p3-gate.md` §1（含两种 `ERR busy` 的原文与 `rejectBusy` 的 RST 缺陷修复）。

### U7 深层控件树（**已闭合 2026-10-05** —— 结论就在本条，复跑入口见文末）

- 原条目：CCS 12 上 `ui.tree 5` 只展开到 `Composite`，更深层读取未解决。
- **结论一：不是读不到，是 N 不够。** `walk()` 只有四个停法（深度 / 3000 条预算 / 非 `Control` 的特判 /
  别的 shell），**只有深度在拦**：行数从未接近 3000（最大 255 行）；**主可见 shell 域**（编辑器已开）
  两侧同值：**最小可读 N = 15**：

  | N | 12 | 13 | 14 | **15** | 16 | 20 / 30 / 60 |
  |---|---|---|---|---|---|---|
  | CCS12 行数 / 有没有编辑器 `StyledText` | 161 / ✗ | 163 / ✗ | 165 / ✗ | **169 / ✓** | 171 / ✓ | 171 / ✓（**已到叶子，逐档一致**） |
  | GS32 行数 / 有没有编辑器 `StyledText` | 197 / ✗ | 202 / ✗ | 207 / ✗ | **221 / ✓** | 224 / ✓ | 224 / ✓（同上） |

  深度 15 是**编辑器客户端区**的深度（`Canvas → StyledText`）；视图内部更浅 —— Project Explorer 的
  `Tree` 在**深度 8**、Outline 的 `Tree` 在**深度 12**。
  · **这个 15 带 shell 作用域**（2026-10-05 复核补，`measurement-hygiene` §13.8）：它是**主可见 shell** 里的数。
    GS32 的 `PartRenderingEngine's limbo` shell 里，**同一个** `StyledText` 在**深度 13** 即到
    （复核实测：`tree 13 --shell limbo` → `StyledText vis=false en=true`，缩进 26 空格 ⇒ 深度 13）。
    ⇒ 引用这个数**必须带 shell 作用域**；跨 shell 比较行数也不成立（两边不是子集关系，见 §1 A11b）。
  ⇒ 旧条文里「更深层读取未解决」的真相是「`ui.tree 5` 只走到深度 5」，**不是**平台读不到；
  `route-comparison.md:415` 的「这是桥要改进的点」也据此更正为：**桥不需要改默认**，需要的是**写明最小可读 N**。
- **结论二：`--shell` 把另一个真盲区补上（不是深度问题）。** 默认只挑「最大的可见 shell」，
  而 e4 会把**尚未渲染**的部件停在不可见的 `PartRenderingEngine's limbo` —— GS32 上编辑器与 4 个视图栈
  **全部**在 limbo，**任何 N 都读不到**；`ui.tree 20 --shell limbo` 一次读到（`StyledText` 1 / `Tree` 3）。
  细节与对照表见 §1 的 **A11b**、`protocol.md` §7.1。
- **结论三（停手）：真正的「部件 → 控件根」要 e4，本轮不做。** 公共 API 没有 `IWorkbenchPart.getControl()`
  （见 §2 的 **N9′**）；既然结论一已经证明**不需要**它，就**不**在本轮碰 `prd.md` §6.3 的 e4 模型层。
- **复跑入口**（两条，都不改默认语义）：
  ```bash
  python -m ctl tree 15 --run-id <id> --port <p>                     # 到最小可读 N（**主可见 shell** 域；编辑器控件深度 15）
  python -m ctl tree 15 --shell limbo --run-id <id> --port <p>       # 读不可见 shell 里的部件
  ```
  `depth` 是**位置参数**（`python -m ctl tree --depth 3` ⇒ `ERR badrequest unrecognized arguments: --depth`，2026-10-05 复现）。
- **证据**：任务侧 `research/final-depth-*.txt`（10 档原始输出）、`research/tree-p2-*.txt`（多 shell 对照）、
  `research/p1-depth-table.md`（汇总与分因）。

### U8 e4 应用模型层寻址（**已定论 2026-10-05** —— 结论就在本条，复跑入口见文末）
- 原条目：`EModelService` / `MApplication` / `MWindow` 层寻址未实测。
- **2026-10-05 实测（由当前源码构建的实例，身份已按 `measurement-hygiene` §13.10 反例 A 第 2 条对拍）**：
  · 起实例前确认 `8777` **无活监听**；起来后 `sys.env` 回读
    `bundle=eclipse-ctl.bridge version=0.2.0 id=351 state=32`，与
    `bridge/dist/eclipse-ctl.bridge_0.2.0_gs32.jar` 的 `Bundle-Version: 0.2.0`（及
    `bridge/build.py:34` `DEFAULT_VERSION = "0.2.0"`）**逐字一致** ⇒ 测的是本轮构出来的产物。
  · `ui.parts` 负载**逐字**含 `services: EModelService=true` ⇒ **可用性成立**。
- **但"经该层寻址"这件事在本代码库里不存在，且不需要**（两条都实测）：
  · `bridge/src/` 全文搜索 `EModelService|MApplication|MWindow|MPart|EObject`：
    **`EModelService` 只出现一次**，且只作可用性探针
    （`bridge/src/ctl/bridge/LiveBridge.java:904`）；`MApplication` / `MWindow` / `MPart` / `EObject`
    **零命中**。其余 `getService` 命中是 `ICommandService`(`:1092`) / `IEclipseContext`(`:1095`) /
    `IHandlerService`(`:1277`/`:1304`)，与 e4 模型层无关。
  · §N9′ 已证读控件树**不需要**它（`ui.tree --shell` 已可达全部部件）。
- **结论**：本条**不是**"在现有能力上补一条用例"的缺口 —— 它是一条**刻意不存在、且不需要**的能力。
  故**不新增用例**（给不存在的能力补判据 = 凭空造范围）；`ui.parts` 那行 `services:` **已有用例钉住存在性**
  （`ctl/verify/cases/read_parts.py`：`if "services: EModelService=" not in text`）。
  三措辞里取 **`决定不投入`**（理由见上），**不是**"已证伪"、也不是"未证实"。
- **复跑入口（只读；需一台由当前源码构建的活实例）**：

```bash
# ① 起一台由当前源码构建的实例（会在桌面弹窗），再对拍身份
python -m ctl run --target gs32
# ② 身份：version 必须逐字等于 bridge/dist 的 Bundle-Version（否则该次测量作废）
# ③ 可用性：ui.parts 负载须含该行
python -m ctl parts --run-id <run_id> | grep "services: EModelService="
# ④ 寻址不存在：期望**只**命中 LiveBridge.java:904 那一行
grep -rn "EModelService\|MApplication\|MWindow\|MPart" bridge/src/
```

### U9 JDI / JDWP 求值通道
- **未验证，本轮不投入**（D6）：它是唯一能补 F10「控制台无法求值」的已知路线（CDP `Runtime.evaluate` 的对应物）；代价是新子系统 + **挂起会冻死整个 IDE**，需独立安全设计。
- **验证入口**：`jdb -attach <host>:<port>` 对已带 `-agentlib:jdwp=<opts>` 起的实例（调研实测该路可达 suspend / 列线程 / 求值）。
- **证据**：`prd.md` §6.9；`design.md` §11 取舍表「JDI / JDWP | 不投入本轮（D6）」。

### U10（**已闭合 2026-10-04 → 见 §1 的 A6c**）
- 原条目：桥的 `syncExec` 与「任何占用 UI 线程者」互斥——**外部输入（点击/按键）是否也算占用同一线程，未验**。
  从未观察到「点击导致桥停摆」。
- **已在真实例上验证闭合**（2026-10-04，run `gs32-p66b`）：合成输入与桥的 `asyncExec` **确实共用同一个 UI 线程**
  （同步 `SendMessage` 往返 = 「UI 线程处理这一次点击」的耗时）；是否被观测到则取决于**输入造成的 UI 线程工作量**
  （空闲单击微秒级 ⇒ 不可观测；输入积压 ⇒ `ui.*` 排队而 `sys.ping` 不受影响）。
  内容移至 §1「A6c 输入与桥的相互影响（F11 / P6.6）」；此处只留指针，避免「未验证」区里挂着一条已验证的条目。
- **注**：原「验证入口」已作废 —— 它要求「用 `BM_CLICK` 点主窗一个无害按钮」，而实测真 IDE 主窗里
  **`Button` = 0、`Edit` = 0**（§A6b-2），该目标不存在；实际改用 §A6c 的**坐标消息打到显式声明的 `SWT_Window0` 子控件**。
- **证据**：§1「A6c」的实测原文与「已执行配方」；任务侧 `research/batch2-2026-10-04.md` §3（子项 2.2）；
  探针 `research/probes/p66-coord-target.ps1`（`-Sync` / `-Burst`）与 `p66-contention.py`；
  `prd.md` F11 与 §6.10（同处**已同步为已实测**）。

### U11（**已闭合 2026-10-02 → 见 §1 的 A9b**）
- 原条目：`getDefinedCommandIds()` 只含**有 `<command>` 声明**的 id，结构性漏掉「有 handler 无声明」者
  （典型：厂商 OptionBytes = `com.gs.chipsetting.commands.opthandler`）。
- **已在真实例上验证闭合**，内容移至 §1「A9b `getDefinedCommandIds()` 漏项**已闭合**」；此处只留指针，避免
  「未验证」区里挂着一条已验证的条目。
- **证据**：§1「A9b」的实测原文（GS32 `handlerOnly registry=ok total=1` → `com.gs.chipsetting.commands.opthandler`；
  `commands.json` 顶层 `handler_only` 字段）；本条目**不再是「未验证」结论**，只作旧编号的转指。

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

### U13 part-scoped 命令的驱动方法（**已闭合 2026-10-05** —— 见 §2 的 N9）

- 原条目：已知 `executeCommand(id, null)` **不**路由到部件级 handler（见 N9）；但**如何设置 selection /
  构造 Event** 才能驱动这类命令，未验。
- **终局：靶不再失败，而且不需要改桥。** `org.eclipse.ui.edit.selectAll` 在**编辑器是活动部件**时
  （`python -m ctl open <file> --yes` 之后）回 **`OK`**，且**有可归因回读差**（见下）。
  这一条 2026-10-05 在两侧复跑过；payload 原文 `before: defined=true handled=true` +
  `executeCommand returned: null`。
- **可归因回读差**（2026-10-05，CCS 12，run `p2-ccs12-focus`，端口 8783）：动作前编辑器无选中、
  状态栏 `3 : 1 : 79`；动作后 79 个字符全选、状态栏 `3 : 1 [79]`（`[n]` 就是 Eclipse 文本编辑器的
  「已选中 n 个字符」字段，79 = 该文件字节数）。两帧截图：
  任务侧 `research/` 记录的路径（`a3-before-011557-*.png` / `a3-after-011636-*.png`）。
  ⚠️ **现有方法面没有读选区的方法**，所以这条回读差**走的是截图通道**（`see()`，`skill/references/observation.md`
  的证据通道），不是协议回读 —— 这条缺口如实记下，不冒充。
  **补（2026-10-05 复核独立复跑，CCS 12 run `chk-ccs12-1005`/端口 8830，jar 0.2.0）**：方法面确实没有
  **直接**读选区的方法，但选区的**存在性**有一条**协议级**（非像素）回读通道 —— 挑一条**以选区为前提**
  的命令，读它的 enablement。同一编辑器上 `python -m ctl cmd org.eclipse.ui.edit.copy … --yes`：
  **刚打开、无选区**时回 `ERR disabled`（连测两次都是，排除「暖机」），`selectAll` 之后回 `OK`
  （`copy` 把选区写进系统剪贴板 —— 只动剪贴板，不动被测编辑器的状态）。
  ⇒ A3 的「可归因回读差」**可以在协议级成立**（不再只有像素）；要读**选区大小**才仍需像素通道
  （状态栏 `[n]`）—— `ui.tree` 读不到它：`describe()` 只给 `Item` 输出 `text=`，`Label`/`CLabel`/`StatusLine` 没有。
- **三种结局与不变量**：`OK` / `ERR unhandled` / `ERR disabled` 三档的判据表与「换 lookup 上下文无效」
  的实测见 §2 的 **N9**；`file.saveAll` 仍是 `ERR disabled`（「有脏编辑器」的条件），未与 `unhandled` 混。
- **复跑入口**：
  ```bash
  python -m ctl open <abs .c> --run-id <id> --port <p> --yes          # 让编辑器成为活动部件
  python -m ctl cmd org.eclipse.ui.edit.selectAll --run-id <id> --port <p> --yes   # 期望 OK + 上面那对截图
  python -m ctl cmd org.eclipse.ui.file.saveAll  --run-id <id> --port <p> --yes   # 期望 ERR disabled（对拍）
  ```
- **证据**：任务侧 `research/p3-selectall-terminal.txt`。

---

## 4. 本文件不含的结论（防误引）

- 「坐标注入」**不是**「已证伪」，也**不是**「能做」——它是 U2 的**未证实 + 决定不投入**。
- 「控制台反射调 Java」**是** N1 的**已否决**（有方法无效级证据）。
- 「同一个源，两套编译参数（gs32 = 17 / ccs12 = 11）」是 `design.md` §9 的**设计决定**，不是本文件的边界条目。

---

## 5. A5′ 双 target 兼容矩阵与两列对照（R5′ / 门 G4，2026-10-02）

> 数据来源：**两侧都在真实例上全量跑过**（各 26 用例），原始日志留档；
> 平台事实取自 `read.env` / `read.cmd.list` / `read.viewids` 的**协议原文**与磁盘上的实际文件名。
> **不抽样**（R5′.5）：没有「只跑一侧、说另一侧应该也行」的条目。

### 5.1 兼容矩阵（六列）

| 列 | GS32_Studio v1.2.5.2 | CCS 12.8.1 |
|---|---|---|
| **平台版本** | Eclipse Platform **4.30.0** + CDT 11.5.0 | Eclipse Platform **4.23.0** |
| **JRE 模块数** | JustJ Temurin **23.0.2** minimal → **30** 模块（`java --list-modules \| wc -l`） | **11.0.13** → **55** 模块（同上实测） |
| **命令服务 bundle 版本** | `org.eclipse.ui.workbench_3.131.0.v20231201-0512` | `org.eclipse.ui.workbench_3.125.0.v20220308-0722` |
| **厂商命令数** | `com.gs` → **7**（`cmd.list` 原文 `com.gs total=666 matched=7 returned=7`） | `com.ti` → **115**（原文 `com.ti total=807 matched=115 returned=115`） |
| **必须在目标上重编的产物** | 桥 jar（class-file **61** / Java 17，`java_target=17`）；**SWT 片段 3.124.200** 与夹具 class | 桥 jar（class-file **52** / Java 8，`java_target=8`）；**SWT 片段 3.119.0** 与夹具 class |
| **厂商命令 id 清单** | 7 条：`com.gs.sdk.version`、`…sendtoLive`、`…checkproject`、`…gsprojectimport`、`…gsprojectcreate`、`com.gs.sdk.editor.activate`、`com.gs.ui.intro.openFile` | 115 条（`com.ti.*` 前缀；全量清单以 `ctl commands export` 的产物为准，本表给前缀与计数） |

补充事实（同一协议原文）：`read.viewids` 注册视图 GS32 `total=55`（厂商 5）/ CCS `total=95`（厂商 33）；
命令表总量 GS32 **666** / CCS **807**；`handlerOnly` GS32 **1**（`com.gs.chipsetting.commands.opthandler`）/ CCS **0**。
> **2026-10-02 更正**：本行此前写「两者 `handlerOnly=0`」，与桥侧原文（空前缀 `handlerOnly registry=ok total=1`）不符。
> 实测**两个数都对，只是作用域不同** —— `handlerOnly` 块**按前缀过滤**：
> **空前缀（全局）** GS32 **1** / CCS **0**；带 `org.eclipse.ui.edit` 前缀时**两侧都是 0**。
> `read.cmd.list` 早先只把带前缀那次的值打进详情，于是读起来像"打架"（**上一版本行曾把它推测成
> 「扫描落地前的旧值」，那是没有证据的假设，已按实测改掉**）；该用例现改为三个作用域都标出：
> `handlerOnly(global=…, prefix=org.eclipse.ui.edit=…, prefix=<vendor>=…)`。
> 客户端 `ctl commands export` 走空前缀，故 §A9b 引用的是**全局值**；它另修掉了 CCS 少 2 条 `redo`/`undo` 的静默丢数据。

### 5.2 两列对照表（同一用例集，逐条）

`ctl verify --all` 在两侧各跑一遍（**28 用例** = read 11 + write 4 + errors 7 + resilience 2 + input 1 + realflow 1 + **板级 2**）。
⚠️ `--all` **不按 target 过滤**（`ctl/verify/runner.py::Runner.run`：不适用 target 的用例记一条
`skipped: not applicable to target …`）⇒ **用例集一变，两侧的合计都必须重跑**。
下表读数 = **2026-10-09 重跑**（先 `ctl install --target <名>`，`ECLIPSE_CTL_AUTO_GC=false`，**无并发负载**）。

| 用例 | GS32 | CCS | 差异与归因 |
|---|---|---|---|
| `read.ping` | PASS | PASS | — |
| `read.env` | PASS | PASS | — |
| `read.shells` | PASS | PASS | — |
| `read.parts` | PASS | PASS | — |
| `read.viewids` | PASS | PASS | — |
| `read.persp` | PASS | PASS | — |
| `read.tree` | PASS | PASS | — |
| `read.cmd.list` | PASS | PASS | — |
| `read.cmd.query` | PASS | PASS | — |
| `read.wait` | PASS | PASS | — |
| `read.console` | SKIP | SKIP | 两侧同因：该实例 Console 视图没有 console 页 ⇒ 如实跳过 |
| `write.open-editor` | PASS | PASS | — |
| `write.close-view` | PASS | PASS | — |
| `write.runp-show-view` | PASS | PASS | — |
| `write.run-toggle` | PASS | PASS | — |
| **`input.fixture`** | **PASS** | **FAIL** | **见 §5.3（归因：平台版本 / SWT）** |
| `errors.unknown-method` | PASS | PASS | — |
| `errors.bad-param` | PASS | PASS | — |
| `errors.missing-id` | PASS | PASS | — |
| `errors.unhandled` | PASS | PASS | — |
| `errors.bad-runp-param` | PASS | PASS | — |
| `errors.console-absent` | PASS | PASS | — |
| `errors.plugin-id-as-view` | PASS | PASS | — |
| `resilience.modal-reset` | PASS | PASS | — |
| `resilience.timeout-applied` | PASS | PASS | — |
| **`realflow.build_artifact`** | **PASS** | **PASS** | 判据、配方形状、产物名与 `e_machine` 见 §5.4（差异只在值上：构建入口 / 配置名 / 标记的字节编码） |
| **`board.led_chase`** | **SKIP** | **PASS** | CCS12 侧硬件用例（XDS100v2 `PID_A6D0` + DSP280025 板）；GS32 侧不适用（`targets=("ccs12",)`）⇒ `skipped: not applicable to target gs32` |
| **`board.led.chase.gs32`** | **PASS** | **SKIP** | GS32 侧硬件用例（板载 FT2232H `PID_6010` + H1017A 板，2026-10-09 新增）；**不走桥**：判据 = 两个 CLI 的 rc + 各自成功标志 + ELF 回读（见 §5.4 与用例 docstring；人眼段不可省） |
| **合计** | **26 PASS + 2 SKIP / 0 FAIL**（rc=0；28 用例，**2026-10-09 实测**） | **待重跑**（见右格） | GS32 列 2026-10-09 重跑；**CCS12 列的旧快照（24 PASS + 1 SKIP / 1 FAIL）已按 §13.8 撤下**——用例集 +1（本任务新增的 GS32 专用用例在该侧记一条 `not applicable` SKIP）⇒ 该列须同批重跑：`ctl install --target ccs12` → `ECLIPSE_CTL_AUTO_GC=false python -m ctl verify --all --target ccs12`。归因 1 条（`input.fixture` 的 `key`，§5.3），未结案 **0** 条 |

原始输出片段（`input.fixture` 的差异 + 新增 `realflow` 两侧原文）：

```
[GS32] [PASS] input.fixture  7 条断言（4 条标题有变化；证伪 ⑤=1 ⑥=UNCHANGED）｜ target=gs32
[CCS ] [FAIL] input.fixture  7 条断言（3 条标题有变化；证伪 ⑤=1 ⑥=UNCHANGED）｜ target=ccs12
        | FAILED: key：期望 CHANGED，实测 UNCHANGED（after='ctl-fixture GO 2'）
        | 目标 SWT=3.119.0 —— 已知平台差异（兼容矩阵 input.fixture/key）：
        | Eclipse 4.23 不把合成 WM_KEYDOWN 派发给控件自身的 KeyListener
[GS32] [PASS] realflow.build_artifact  target=gs32 project=realflow_gs32 create=ok rc=0 editors=3->4
        new_editor='org.eclipse.cdt.ui.editor.CEditor' build_rc=0 artifact=realflow_gs32.elf
        size=551584 e_machine=243(exp 243) marker_in_image=ascii@32996
[CCS ] [PASS] realflow.build_artifact  target=ccs12 project=realflow_ccs create=ok rc=0 editors=3->4
        new_editor='org.eclipse.cdt.ui.editor.CEditor' build_rc=0 artifact=realflow_ccs.out
        size=17528 e_machine=141(exp 141) marker_in_image=u16le@604
```

### 5.3 归因：唯一一条差异 = **平台版本（SWT 派发行为）**

**判据**：夹具对 `Edit` 子窗发同一条 `WM_KEYDOWN VK_RETURN`（`SendMessage`），
标题应变成 `ctl-fixture KEY 13`。GS32 变，CCS 不变（**3/3 确定性，不是偶发**）。

**归因实验（同一套启动方式，只换一个变量）**：

| # | JVM | SWT（平台版本） | `key` 结果 |
|---|---|---|---|
| A | 11.0.13 | **3.119.0**（Eclipse 4.23） | UNCHANGED |
| B | **23.0.2** | **3.119.0** | UNCHANGED |
| C | **23.0.2** | **3.124.200**（Eclipse 4.30） | **CHANGED** |
| D | 11 / 23 | 3.119.0 + `WM_SETFOCUS` 或 `SetForegroundWindow` | 仍 UNCHANGED |

⇒ **变量是 SWT 版本**：A↔B 同 SWT 换 JVM **不翻面**；B↔C 同 JVM 换 SWT **翻面**。
⇒ **JVM 排除；焦点/前台排除**（D 两种补救都无效）。
⇒ **归因 = 平台版本**（R5′.3 的四类之一），**不是** JVM 级别，也**不是**依赖 bundle 缺失。

**边界**（措辞纪律，§4 的三档不得混用）：
- 「点按钮」`BM_CLICK` 与「写文本」`WM_SETTEXT` 在**两侧都通** ⇒ 元素寻址输入原语**不是**整体不可用。
- 「按键」`WM_KEYDOWN` 在 Eclipse 4.23 上**不可用**（本机实测，确定性）；在 4.30 上可用。
  ⇒ 结论写作「**按键原语按平台核对**」，**不**写成「合成输入无效」。

### 5.4 判据同源可证（A5′④）

两侧跑的是**同一个用例文件、同一段判据表达式**，逐字相同：

```python
# ctl/verify/cases/input_fixture.py —— 两侧共用同一份源码
want = row["expect"]                      # 来自同一张常量表 _PROBES
got  = row["verdict"]
if got != want:
    problems.append("%s：期望 %s，实测 %s（after=%r）%s" % (cid, want, got, row.get("after"), note))
```

- **没有任何 per-target 的判据分支**：判据表达式里不出现 `target`。
- 唯一按 target 取值的量是 **target 事实**（R5′.2 允许「差异落在值上」）：
  `probe_view`（两侧厂商视图名不同）与夹具工具链路径。两侧的 `want` 表**逐字相同**。
- 归因**写在失败消息里**（上引原文），不是靠人工记忆附会。

**第二个例子：`realflow.build_artifact`（2026-10-03 新增）** —— 判据完全同源，
per-target 差异只在**配方数据**与**值**上：

```python
# ctl/verify/cases/realflow_build_artifact.py —— 两侧共用同一份源码（逐字摘录）
problems.append("artifact: e_machine=%d, expected %d"
                % (elf["machine"], recipe["machine"]))
...
        new_row = added[0]
        if "CEditor" not in new_row[0]:
            problems.append("ide: the new editor is %r, not a CEditor" % (new_row[0],))
        if new_row[1] != write.get("marker_name"):
            problems.append("ide: the new editor name is %r, expected %r"
                            % (new_row[1], write.get("marker_name")))
```

| 量 | GS32 | CCS | 性质 |
|---|---|---|---|
| 判据表达式 | 同一份文件 | 同一份文件 | 同源 |
| 建工程 | 复制 CDT 模板 + 改 `.project` `<name>` | `.projectspec` + `com.ti.ccstudio.apps.projectCreate` | **构建入口差异**（已归因，§6.2 of 研究档 / §5.1 末行） |
| 构建 | CDT `headlessbuild` | `com.ti.ccstudio.apps.projectBuild` | 同上 |
| 构建配置名 / 产物 | `Flash_ILM` / `*.elf` | `Debug` / `*.out` | **值** |
| `e_machine` | 243（RISC-V） | 141（TI C2000） | **值**（器件） |
| 标记字节编码 | `ascii` | `u16le`（C2000 默认 16 位 `char`） | **值**（工具链） |
| 实测 | PASS · `realflow_gs32.elf` 551584 B | PASS · `realflow_ccs.out` 17528 B | — |

反假阳性两侧同样成立：写出的源带唯一 `CTL-REALFLOW-<8 hex>`，`main` 引用它，
构建后在产物字节里**按对应编码找回**那串标记 ⇒ 编的是**这一次写的**代码，不是陈旧产物。

> 上表「实测」列的尺寸是**某一 run** 的值：标记每次随机 ⇒ 同一份源码也会差几个字节
> （实测 GS32 551584 / 551588 B，CCS 17528 / 17532 B）。**稳定判据是 `e_machine` 与
> 「标记在产物里」，不是尺寸**。

### 5.5 未结案条目

**0 条。** 唯一差异已归因（§5.3）。
