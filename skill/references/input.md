# Input 域：三个原语与它们能/不能做的事

元素寻址的输入原语是**库函数**（`ctl run` 的脚本命名空间），不是 CLI 子命令。
三条都**默认 dry-run**：不带 `yes=True` 只回一行 `DRY-RUN …`，桥侧与窗口**零动作**。

| 原语 | 寻址 | 动作 | 适用面 |
|---|---|---|---|
| `act_click_button(text, case=None, title=None, yes=False)` | 窗标题 + **按钮标签**（必须**唯一**） | `BM_CLICK` | 对话框上的 `Button` |
| `act_send_keys(key, title=None, class_="Edit", index=None, yes=False)` | 窗标题 + **控件类**（唯一或 `index=`） | `WM_KEYDOWN/UP` | 对话框上的 `Edit`（见 §C 的按键口径） |
| `act_set_text(text, title=None, class_="Edit", index=None, yes=False)` | 同上 | `WM_SETTEXT` | 对话框上的 `Edit`（**打字走这条**） |

**适用面是对话框，不是主窗**：实测真 IDE **主窗**的 `Button` 与 `Edit` **各为 0**；
真实目标是对话框（`#32770`），那里才有 `&Reset Perspective` / `&No` 这类真按钮。

**fail closed**：标签/类名寻址必须**唯一**，命中 **0 或 >1** 都在**发送任何输入之前**失败
（先 `-ListOnly` 枚举，再决定发不发）；不给 `index=` 时不做「挑第一个」。序位**只在同一会话内稳定**，跨运行会漂移。

---

## A. 真 IDE 端到端四元组（2026-10-04，GS32_Studio 4.30）

载体：`org.eclipse.ui.window.resetPerspective` 的确认框，与 GS32 自带 Preferences 的过滤框。
**走产品库**（不是裸 `SendMessage`）。原始输出见任务侧
`.trellis/tasks/archive/2026-10/09-30-eclipse-ctl-project/research/p67-realide-input-2026-10-04.md`。

| 原语 | 寻址 | 动作原文 | 可观测回读差 | 结论 |
|---|---|---|---|---|
| 点按钮 | 标题 `Reset Perspective` + 标签 `&No`（真 `#32770`） | `BM_CLICK sent to hwnd=0x715DA text="&No"` | 框消失（`ui.shells` 3→2、独立枚举 `-Class "#32770"` 空）+ `parts` **不变** + `sys.ping OK` | **可行** |
| 写文本 | 标题 `Preferences` + 类 `Edit` + `index=0` | `sent WM_SETTEXT "proxy" -> hwnd=0x1E12F4` | 框内出现 `proxy` **且**左树按它重过滤成 `General > Network Connections` | **可行**（行为级） |
| 按键 | 同上 | `sent WM_KEYDOWN/WM_KEYUP vk=0x2E`（`DELETE`） | `proxy` → **`roxy`**、左树**清空** | **可行**（插入点相关） |
| 负例：不给序位 | 同上 | `act_set_text(…, index 缺省)` | `ERR badrequest ambiguous: 3 visible children of class 'Edit'`，**写之前**就拒 | fail closed 成立 |

**判据必须叠加**，缺一条就会读错：点按钮那次「框没了」**不能单独**算过 —— 还要 `parts` **不变**
（证明选的是 `No` 而不是 `Reset Perspective`）**且** `ping` 仍 `OK`。

---

## B. 真 IDE 上 `Edit` 是 3 路歧义

Preferences 对话窗里**可见的 `Edit` 有 3 个**（过滤框 + `Initial maximum number of elements` +
`Workbench save interval`）。夹具里的歧义是造出来的，这里是**产品自带的**：

```
  hwnd=0x1E12F4 class=Edit vis=True text="" rect=788,485,332,42     ← 过滤框
  hwnd=0x181406 class=Edit vis=True text="" rect=1866,693,170,42
  hwnd=0x811EE  class=Edit vis=True text="" rect=1666,791,370,42
```

⇒ 不给 `index=` 一律 `ERR badrequest ambiguous: …`；要打哪一个就**显式**给 `index=`
（**0 基**，且只在同一会话内稳定）。

---

## C. 按键口径：非字符键可行 / 可打印字符无效果 / 插入点决定结果

同一条路径上打了四个键，**两个无回读差**（截图都读了，是像素级的结论）：

| 动作 | 原文 | 像素回读 | 归因 |
|---|---|---|---|
| `BACK`（`vk=0x8`） | `sent WM_KEYDOWN/WM_KEYUP vk=0x8` | 仍 `proxy`（无差） | **插入点在 0** ⇒ 光标前无可删（**位置**问题） |
| `X`（可打印字符，`vk=0x58`） | `vk=0x58` | 仍 `proxy`（无差） | 本层 `SendMessage` 直达子窗 HWND、消息**不进目标线程队列** ⇒ `TranslateMessage` 从不运行 ⇒ 不生成 `WM_CHAR`（**[INFERENCE]：机制未单独验证**） |
| `DELETE`（`vk=0x2E`） | `vk=0x2E` | **`proxy` → `roxy`**，过滤树清空 | **原语本身生效** |
| `BACK`（第二次） | `vk=0x8` | `roxy` 不变 | 插入点仍在 0 |

**范围限定（写用例必读）**：**非字符键（`BACK` / `DELETE` / 方向键 / `RETURN`）可行；
可打印字符经本原语无效果** —— 要「打字」走 `act_set_text`，**不要**用 `act_send_keys` 逐字敲。

> **`BACK` 与 `X` 的表观结果一模一样（都「没反应」），但归因不同**：前者是**原语生效、只是无可删**，
> 后者才是**原语不适用**。**没有 `DELETE` 这个对照**，就会把「插入点在 0」误读成「按键原语在真 IDE 上不生效」。
> 见 §D。

**prior art 的边界要读对**：上游调研那条「真按键合成要求前台，否则拒绝」说的是 `Display.post`，
与本层的跨进程 `WM_KEYDOWN` **不是同一条路** —— 后者**不需要前台**
（实测该窗 `hwndFocus=0x1E12F4`，而 `GetForegroundWindow()` 是别人的窗）。两者不得互相引用当结论。

---

## D. 一条「无回读差」在排除目标自身状态之前不构成结论

`BACK` / `X` / 第二次 `BACK` 三条都是「无差」，但只有一条是「原语不适用」。
⇒ 一条「无回读差」**只**在**排除掉所有可由目标自身状态解释的原因**之后，才能当结论；
待排除项按目标类型列举（编辑器控件：**插入点位置 / 选区 / 只读态 / 掩码 / IME**）。
排除靠**对照实验**（这里：`DELETE` 证明插入点在 0、且证明原语生效），不是靠「我觉得应该是这样」。
没做对照前只能写「**未观察到变化 + 待排除项：<清单>**」，**不得**写成「原语不生效 / 通道坏了」。
最便宜的自检：**换一个不依赖该状态变量的输入**再打一次。

---

## E. 一条必须记下的假阴性通道：跨进程 `GetWindowText`

同一次枚举里 `Button` 的文字读得到（`Apply and Close` / `Cancel`），而**刚被写过的 `Edit` 仍读回 `text=""`**：

```
  hwnd=0x1E12F4 class=Edit vis=True text=""     ← 图上是 "proxy"
```

⇒ 这个通道对 `Edit` **恒返回空**，「写进去了」与「没写进去」在它眼里**完全一样**。
纪律：`-ListOnly` 只许用于**寻址**（类名 / 可见性 / 矩形 / 序位），**不得**当**控件值**的判据；
文本值与行为都看**像素**（`see()`）或行为级回读（如过滤树是否收窄）。
反面例：把 `text=""` 当作「输入没生效」的证据 —— 它会给出**与像素相反**的结论，
并诱人去「修」一个**不存在的缺陷**（例如加一个重试写入的循环）。
