# 行协议（对外契约）

**读者**：集成者 / 脚本作者 / CI　　**项目版本与本文件无关**，协议版本单独编号。
**契约出处**：`design.md` §3（协议契约）、§4（并发与线程模型）、§6/§7（读/写路径）、
`design-project.md` §15.2/§16.3（版本策略与握手）、§17.6（协议演进规则）、
`design-obs-ux.md` §14.3（端口发现）、§14.5（错误→处置）。

---

## 1. 传输层

| 项 | 值 | 出处 |
|---|---|---|
| 传输 | TCP，**只绑 `127.0.0.1`**（不监听其它地址） | `design-project.md` §15.4 安全基线 1 |
| 端口 | `-Dctl.port` **>** 环境变量 `CTL_PORT` **>** 默认 `8777` | `implement.md` P0.4a |
| 编码 | UTF-8 | — |
| 帧界 | 每行以 `\n` 结束；请求**恰好一行** | `design.md` §3 |

> 端口解析优先级（桥侧）：`-Dctl.port` > `CTL_PORT` > `8777`。客户端一侧的端口发现见 §6。

---

## 2. 帧格式

### 2.1 请求（一行）

```
<method> [arg]
```

- `method` 与 `arg` 以**单个空格**分隔；`arg` 内部可含空格（整行剩余部分即 `arg`）。
- 约定：`sys.ping` / `sys.env` 无参数；`ui.tree` 取一个深度整数；`cmd.runp` 的 `arg` 形如
  `<commandId> <paramId>=<value> [<paramId>=<value> ...]`。

### 2.2 响应

成功：

```
OK
<负载行 0..N>
END
```

失败：

```
ERR <code> <message>
<负载行 0..N>
END
```

规则：

1. **首行一定是 `OK`（成功，不带摘要）或 `ERR <code> <message>`（失败）**；此后是 0..N 行负载；最后一行是**单独的 `END`**。
   `OK` 行**没有**摘要文本 —— 桥只写 `status`（`bridge/src/ctl/bridge/LiveBridge.java:443`），
   而 `status` 在成功路径上就是字符串 `"OK"`（`:427`），没有别的尾巴。
2. `END` 是帧终止符。客户端**必须读到 `END` 才认为一帧结束**；读到 `END` 之前就断开 = 帧不完整。
3. `ERR` 的首行形如 `ERR <code> <message>`，`code` 取自 §3 的闭集，`message` 是**人类可读的一行**。
4. 负载行**不保证**是合法 JSON；它是给人看、给 grep 的文本。机读请用 CLI 的 `--json`（`design-obs-ux.md` §14.3），
   不要把负载行当机读接口。

**示例（真实帧）**：帧形状对照 `bridge/src/ctl/bridge/LiveBridge.java` —— 请求是 `handle()` 里的
`in.readLine()` 读到的**一行**（`:435`），响应由同一个 `handle()` 写出首行 `status`、0..N 行负载、末行 `END`（`:443-445`）；
下文 `sys.env` 的负载行逐字取自 `research/realflow-scenario-2026-10-02.md` 的 `=== [1] identity: sys.env ===`。

请求（**恰好一行**，无任何前缀）：

```
sys.env
```

响应：

```
OK
java.version=23.0.2
os.name=Windows 11
…（其余每条 `key=value` 一行）
thread=gs32ctl-conn-4
END
```

> 桥自己的日志行 `REQ "<请求>" -> <status> …`（`LiveBridge.java:453`）**不是**线上帧的一部分；
> 它只是桥侧日志，别把 `REQ` 前缀当成请求帧的组成部分。

---

## 3. 错误码闭集（**恰好 8 个**）

`code` 是**闭集**——客户端可以只为下面 8 个码写分支；出现闭集之外的码，按 `internal` 处理并上报缺陷
（`design.md` §3；闭集补 `busy` 的过程见 `research/facts-baseline.md` §11.2）。

实现常量见 `bridge/src/ctl/bridge/LiveBridge.java` 的 `CODES`（8 个，顺序与此表一致），
`sys.help` 的 `codes=` 行回报同一串；`sys.env` 亦有 `protocol=` 行。

| code | 触发条件 | 客户端应如何反应 |
|---|---|---|
| `badrequest` | 请求行不合语法 / 参数非法 / 未知方法 / 字节上限内无法表达 | **不可重试**（原样重发必然再失败）；改成合法请求再发 |
| `notfound` | 目标不存在：视图 id、命令 id、参数 id、文件绝对路径、用例名 | **不可原样重试**；可分支（换 id / 换路径）后再发 |
| `disabled` | 命令存在但 enablement 不满足（`NotEnabledException` 的映射；如无 selection、无脏编辑器） | **不可原样重试**；先建前置态（开编辑器 / 设 selection），或把该用例标 skip |
| `unhandled` | 命令有声明但当前上下文无 handler（`NotHandledException` 的映射；典型：part-scoped 未路由） | **不可原样重试**；见 `boundaries.md` 的 part-scoped 条目 |
| `timeout` | UI 调用等待超过上限（桥侧默认 15 s，客户端默认 25 s）；通常是模态框占住 UI 线程 | **禁止当作「未生效」**（语义见 §4）；写方法**必须回读差**再判定；**只有幂等方法才允许自动重试** |
| `noWorkbench` | 桥活着但工作台未创建（工作区被占用 / 未起来） | **不可在此实例上重试**；清场或换工作区后重装（`design-obs-ux.md` §14.5） |
| `internal` | 未映射的异常；`message` 必须带原始异常类名 | 可重试**一次**（且**仅当**该方法是幂等方法）；仍失败则上报四件套 |
| `busy` | 连接数达上限（N=8），或服务端暂时无容量 | **可重试**：按指数退避稍后重发；不得用紧循环轰炸 |

**重试纪律（`design.md` §3 决定 5、§7 铁律）**：**只对 `idempotent=true` 的方法允许自动重试与回滚**。
`idempotent=unknown` 视为**不允许自动重试**。幂等标记见 §7 的方法表。

### 3.1 与 `oversized` 的关系（**已裁决：不是第 9 个码**）

`design.md` §3 第 4 条曾写「超出字节上限即 `ERR oversized`」。**2026-10-01 裁决：不新增该码**，
闭集**保持 8 个**。响应超限的唯一表现方式是**显式截断**：

```
total=<总数>
returned=<本条实际返回数>
truncated=true|false
```

**客户端契约**：见 `truncated=true` **必须**当作「数据不完整」，缩小范围重查
（加前缀 / 降深度 / 分页），**不得**把响应落盘当完整快照。

**为什么不做成错误码**：闭集刚收敛成 8 个，第 9 个码要连带改桥的 `CODES` 常量、CLI 映射、
本文件、`boundaries.md` 与验收项，收益不抵成本；而 `truncated` 是**带内显式标记**，不是静默截断，
「不采信看起来成功的响应」这条纪律照样成立。**代价**：客户端多判一个字段，漏判就会拿到半截数据。

> ⚠️ **别混**：`design-obs-ux.md` / `TROUBLESHOOTING.md` 里出现的 `oversized` 一律指
> **OCU 截图通道**（1 MiB 图像载荷上限），**与桥的行协议无关**。


## 4. 超时语义（⚠️ 本节被审计点名，必须读）

### 4.1 两个独立的超时

| 侧 | 取数 | 默认 | 配置 |
|---|---|---|---|
| 客户端 | 一次请求从写出到收到 `END` | **25 s** | CLI flag / 配置字段（`design-obs-ux.md` §14.2） |
| 桥侧 UI 调用 | 一次 UI 线程调用从投递到取回结果 | **15 s** | `-Dctl.uiTimeoutMs` |

桥侧上限**优先**：常见局面是客户端还在等，桥已经回 `ERR timeout`。

### 4.2 ⚠️ `ERR timeout` ≠ 「未生效」

> **写方法超时后，必须再取一次回读差才能判定是否生效。**（`design.md` §3 超时语义；审计修法见
> `research/audit-round3-2026-10-01.md` A6/A10）

机制：桥把 UI 调用投成 **`asyncExec`**（`design.md` §4 目标表）。超时只终止**等待**——
**已经排进 `Display` 队列的 Runnable 仍会被派发并执行**（模态框的嵌套事件循环照常运转），
超时取消的只是**这次等待**，不是那个动作。

因此：

1. `ERR timeout` 只表示**本次应答**超时；**不是**「没执行」的判据。
   桥的 `ERR timeout` message 本身就把这件事写在字面上：
   `UI task did not finish within <N> ms; the action is still queued on the SWT event thread and MAY still take effect - read back before retrying`。
2. 副作用是否落地**桥无法自证**，因此**没有**服务端 `applied` 字段可供采信；
   客户端**回读后自行判定** `applied=yes|no|unknown`，并把该差值**归因到先前那次超时请求**
   （不是为了给下一次动作当基线）。
3. 回读判定为 `applied=yes` ⇒ **不要再重发**（否则会执行两次）。
4. **只有幂等方法**（§7 表 `idempotent=true`）允许自动重试。
5. **超时只属于发起它的那条连接，不会传染**（2026-10-01 实测，推翻本节旧表述）：
   模态框（`Reset Perspective`）在屏时，**另一条连接**的 `ui.parts` / `ui.tree` / `ui.persp` / `sys.ping`
   **全部正常返回**（实测 0.00–0.02 s）—— 因为 SWT 模态框跑的是**嵌套事件循环**，
   `Display.asyncExec` 的队列**照常派发**；只有**发起那次请求自己**会在 ~15 s 后回 `ERR timeout`
   （它的 handler 正在等对话框的回答）。
   ⇒ **「`ui.*` 是否 `ERR timeout`」不能用来判断界面有没有被模态框占住**。
   判断依据是：屏上有没有那个框（窗口枚举 / 截图）+ **你发的那次请求**是否超时。
   「非 UI 类方法照常响应」这条仍然成立（`sys.ping` / `sys.env` 不碰 UI 线程）；
   但它是**能力**而非**分界** —— 真正的分界是 §4.4 的**连接槽**：满员时连 `sys.ping` 都会 `ERR busy`。

超时后的**标准自救顺序**（`design.md` §5、`design-obs-ux.md` §13.2）：
① 先截图看清框上写了什么 → ② 枚举子窗拿到按钮列表 → ③ 处置（默认 `WM_CLOSE` 关窗；
用例显式声明时才 `BM_CLICK` 按下指定按钮）→ ④ 探活 → ⑤ **对超时请求再做一次回读差**。
可照抄命令见 `recipes/diag-when-hung.md`。

---

## 4.3 ⚠️ `OK` 会撒谎：写命令的失败是**异步**的（必读）

**实测（2026-10-01）**：`cmd.runp org.eclipse.ui.views.showView viewId=<不存在的视图>`

```
OK                                    <- 协议说成功
…
executeCommand returned: null          <- 平台也说成功
OK executed org.eclipse.ui.views.showView
dialog=appeared "Problem Occurred"     <- 但 Eclipse 弹了错误框
dialog_note=the command may have FAILED, or the dialog may be the expected behaviour;
            close it and read back (ui.parts) before treating this call as done
END
```

`ui.parts` 的 `views` **纹丝不动** —— 也就是「**界面没变 + 回话说成功**」。

### 为什么不能用监听器解决
`org.eclipse.core.commands.IExecutionListener`（经 `ICommandService.addExecutionListener` 注册）
**抓不到**：handler 是**正常返回**的，错误在 UI 线程空闲**之后**才异步弹框。
监听器看到的是成功。**别再走这条路。**

### 因此契约加一条负载行（不是错误码）
**所有写方法**（`ui.open` / `ui.close` / `cmd.run` / `cmd.runp` / 元素寻址的三个库原语）在动作前后
各取一次「**可见且有标题的**顶层窗口标题」快照；多出来的窗口回报：

| 负载行 | 含义 |
|---|---|
| `dialog=appeared "<标题1>", "<标题2>"` | 动作期间新出现了这些可见窗口 |
| `dialog_note=…` | 提示：**可能是失败，也可能是本该弹框**；先关掉并回读再当作完成 |
| `dialog=unknown (shell snapshot timed out; the UI thread may be blocked)` | UI 线程被占住，这次**没看见** —— 不要当作「没有弹框」 |

**为什么不做成错误码**：有些命令本来就该弹框（打开首选项之类）。
桥不是成功的判官，它只把**它能看见的事实**交出来；判断留给调用方。

### 客户端契约（**必须遵守**）
1. 写操作后**必须回读**（`ui.parts` 一类）取前后差 —— 这是唯一的语义判据。
2. 见 `dialog=appeared` ⇒ **不得**把该次调用当成功；先看清框上写了什么再决定。
3. 见 `dialog=unknown` ⇒ 当作「**没检查过**」，有模态框处置手段时用上。
4. **回读差「没变化」时，必须区分两种原因**：幂等（成功）vs 失败。**只看 diff 分不出来。**

> 桥外的交叉验证：`tools/win-enum.ps1` 也可做同样前后比对（**已实测能抓到**同一弹框），
> 作为**独立于桥**的观测手段保留。

### 4.4 连接槽与「活体保留容量」（⚠️ 2026-10-01 实测新增）

**容量是按 `accept()` 计的，不是按「有多少请求在跑」计的**：

| 连接序号 | 服务 |
|---|---|
| `1..8` | **全功能**（任何方法） |
| `9..12` | **只准** `sys.ping` / `sys.env` / `sys.help`；别的回 `ERR busy` |
| `>=13` | 直接拒：`ERR busy bridge is at capacity (8 + 4 connections in flight); retry` |

**为什么要有那 4 个保留槽**（实测动机）：8 条**只是连着、不发任何请求**的连接就能把全功能槽占满
（每条要占满 `SOCKET_READ_TIMEOUT_MS` = 60 s），此后连 `sys.ping` 都拿不到 ——
**运维观测能力被平凡地打掉**，而且从外面**分不清「忙」与「死」**。
8 条各自卡在弹框命令里的连接（各 ~15 s）会造成同样结果。
保留槽只放行**不碰 UI 线程、也不阻塞**的方法（`sys.wait` 虽然不碰 UI 但会阻塞，**不放行**），
所以越过上限也不会把线程数推高。

实测（2026-10-01，13/13 全通）：

```
#9  (保留区) sys.ping   -> OK
#9  (保留区) sys.env    -> OK
#10 (保留区) ui.parts   -> ERR busy  …while saturated only [sys.ping, sys.env, sys.help] are answered…
#11 (保留区) sys.wait   -> ERR busy  （同上：会阻塞，故不放行）
#13 (超 8+4) sys.ping   -> ERR busy  …(8 + 4 connections in flight); retry
#1  (未饱和) ui.parts   -> OK       （全功能）
```

**客户端该怎么做**

- 遇到 `ERR busy` ⇒ **可重试**（`busy` 就在错误码闭集里，语义即「稍后重试」）。
- 要判断「桥还活着吗」⇒ 用 `sys.ping`：满员时它**仍然通**（直到第 13 条）。
- 两种拒绝的 `ERR busy` 消息**不同**，别按字面匹配：
  · 保留槽里的越权请求 → `while saturated only [...] are answered`；
  · 连接槽全满 → `(8 + 4 connections in flight)`。
  两者**都可重试**，判断方式看错误码而不是看消息文本。

---

## 5. 鉴权

**本工具不提供鉴权。** 桥**只绑 `127.0.0.1`**（`design-project.md` §15.4 安全基线 1），局域网不可达；
本机上的任何进程/用户都能连 —— 这是**残余风险**，其条件写在 `SECURITY-REVIEW.md`
SR-2026-10-01-01 的「条件」字段里（多用户共享机器不得使用本工具）。

> **原 `token` 可选启用 / 首行 `auth <token>` 握手：该项不存在，已删（2026-10-03）。**
> 配置键 `token`、环境变量 `ECLIPSE_CTL_TOKEN`、握手首行、`endpoint.json` 的 `token` 字段
> 一并移除；桥侧**从未实现**该握手，需求条目本身也不是用户口径（AI 自造，见 `prd.md` R10′.9）。
> 客户端不发送任何鉴权行，连接后**直接发普通请求**。

---

## 6. 端口发现（`endpoint.json`）

桥的端口**按 target 固定**，**不是**从 `8777` 起自动取首个空闲：内置矩阵里
`gs32` 条目有 `"port": 8777`、`ccs12` 条目有 `"port": 8778`（`ctl/targets.py:204` / `ctl/targets.py:217`）。
唯一的覆盖途径是调用方**显式**给一个 `port`（配置字段 / `--port` flag）——`ctl/lifecycle.py:626` 的
`effective_port = int(port) if port is not None else target.port` 就是全部逻辑：给了就用给的，没给就用 target 的固定值。
**端口被占即拒（fail closed）**：`install()` 先用 `list_port_listeners()` 问 OS「到底谁在听」
（`ctl/lifecycle.py:642`：`holders = list_port_listeners(effective_port)`），只要查到的监听进程
**不属于本次运行**（`if foreign:` 成立），就抛 `PrereqNotReady`（`ctl/lifecycle.py:657`，消息含
`port %d is already held by another run …`），提示改用 `--port <其它端口>` 或 `--ensure-clean` ——
**不会**自动换一个空闲端口。
因此**客户端不能假设端口一定是 8777**，也不能假设它会随占用漂移。每次运行会把寻址信息写进：

```
<run_root>/<run_id>/endpoint.json
```

| 字段 | 类型 | 含义 |
|---|---|---|
| `port` | int | 本次运行的桥端口（连接 `127.0.0.1:<port>`） |
| `pid` | int | IDE 进程 pid（用于清场与截图寻窗） |
| `configuration` | string | 本次运行使用的 Equinox 运行配置区绝对路径（桥的常驻落点） |
| `started_at` | string | 启动时刻（ISO-8601） |

`<run_root>` 的**内置默认**是 `<user.home>/.eclipse-ctl/runs`；`design-obs-ux.md` §14.6 的配置示例把它
覆盖成 `D:/tmp/eclipse-ctl`（那是**配置示例值**，不是内置默认）。`<run_id>` 缺省
`<target>-<yyyymmdd-HHMM>`（`design-obs-ux.md` §14.3）。

取实际值用：

```bash
python -m ctl status --target gs32 --json
```

**用法**：`shell` / `status` / `parts` / `act` 等子命令按 `--run-id` 去读这个文件解析端口；
**不读它就无法知道本次运行实际绑在哪一个端口**（target 固定值，或被 flag/config 覆盖后的值）。

---

## 7. 方法面与幂等标记

写操作的**铁律**（F9，`design.md` §7）：**写 = 动作 + 前后回读差，不采信方法自身返回值**。
`OK` 只表示「调用成功返回」，**不表示界面变了**（反例：`cmd.runp showView viewId=com.gs.liveview`
返回 `OK executed`，但回读 views `8→8` 零变化）。

| 方法 | 类型 | 写? | `idempotent` | 回读差判据（写方法） |
|---|---|---|---|---|
| `sys.ping` | 读 | 否 | `true` | — |
| `sys.env` | 读 | 否 | `true` | — |
| `sys.help` | 读 | 否 | `true` | — |
| `sys.wait [<ms>\|jobs-idle]` | 读（等待） | 否 | `true` | — |
| `ui.shells` | 读 | 否 | `true` | — |
| `ui.parts` | 读 | 否 | `true` | — |
| `ui.viewids [prefix] [--limit <n>]` | 读 | 否 | `true` | — |
| `ui.persp` | 读 | 否 | `true` | — |
| `ui.tree <depth>` | 读 | 否 | `true` | — |
| `ui.console [--tail <n>]` | 读 | 否 | `true` | — |
| `cmd.list [prefix] [--limit <n>]` | 读 | 否 | `true` | — |
| `cmd.query <id>` | 读 | 否 | `true` | — |
| `ui.close <viewId>` | 写 | 是 | `true` | `ui.parts` 的 views 集合移除该 id，且 `stillOpen=False` |
| `ui.open <abs path>` | 写 | 是 | **`true`** | `editors` 计数 +1，且 class = `org.eclipse.cdt.internal.ui.editor.CEditor` |
# `true` 的依据：同一文件连开两次，`editors` **1→1**（Eclipse 复用已开的编辑器，不会开第二个） |
| `cmd.run <id>` | 写 | 是 | **`per-command`** | **依命令而定**（多数需专门判据） |
| `cmd.runp <id> <paramId>=<value>` | 写 | 是 | **`per-command`** | 依具体命令：`showView` → views 集合新增该 id；`showPerspective` → perspective id 变化 |

> **`idempotent` 取值与语义**（**3 个待定值已于 2026-10-01 实测回填**，D5）：
> - **`true`** = 方法级幂等，**允许自动重试 / rollback**（重发不改变末态）。
> - **`false`** = 方法级不幂等，**不允许**自动重试。
> - **`per-command`** = **一个方法名承载任意命令，方法级无从保证** ⇒ 与 `unknown` **同等保守**（不允许自动重试）。
>   `cmd.run` / `cmd.runp` 属此类。依据（实测）：`org.eclipse.ui.window.fullscreenmode` 是**开关型**命令，
>   连点两次**回到原状** —— 幂等性取决于**被调命令**，不是方法。
> - **`unknown`** = 尚未确定，**不允许自动重试**（保守默认）。
>
> **实测回填依据**（同一实例内，见 `research/facts-baseline.md` §7.3）：
> `ui.open` 同一文件 ×2 → `editors` **1→1** ⇒ `true`；
> `cmd.runp showView` 同一视图 ×2 → `views` **9→9**（不会开第二个）⇒ 但 `cmd.runp` 仍标 `per-command`，
> 因为它同样能跑开关型命令，不能从 `showView` 一个用例推广到整个方法。
> `sys.wait` 的 `jobs-idle` 读的是桥侧 `JobManager`，**不是** UI 事件等待（`design.md` §6）。

`sys.help` 返回**桥自身**的方法表（name / 参数 / 一句话 / 是否写操作 / 是否幂等），
是客户端做 dry-run 白名单与审批闸的载体（`design.md` §3 第 2 条）。

**响应字段分工**：全量导出类响应（命令表 / 视图表 / Console 文本）必须带
`total` / `returned` / `truncated` 三字段（桥另额外给出 `matched`），客户端据此判断落盘是否完整
（`design.md` §3 第 4 条）。

---

## 8. 响应上限与截断语义

- **单条响应的字节上限**超出时按 §3.1 处理（`oversized` 归属待裁决；实现侧当前**不产出**该码）。
- **全量导出**必须带 `total` / `returned` / `truncated`：
  `total` = 实例里存在多少条，`returned` = 本次实际列出多少条，`truncated` = 是否被截断。
- **默认不做截断**：`ui.viewids` 与 `cmd.list` 只在显式给 `--limit <n>` 时才截断；
  `ui.console` 受 `--tail <n>`（默认 50）与一个字符上限约束，并如实报 `truncated`。
- **客户端落盘前必须校验** `returned == total && truncated == false`；否则报缺陷，**不得**把半份导出当全量用。

> ⚠️ **历史陷阱与修正（`research/facts-baseline.md` §3、§11.2）**：旧产物 `cmd.list` **空前缀也只吐前 300 条**
> （源码硬截断 `if (n <= 300)`），摘要行却报 `total=666`。⇒ **「空前缀 = 全量导出」在旧产物上是错的**。
> 现契约与实现：**空前缀 = 全量**，三字段齐全，`--limit <n>` 才截断
> （`design.md` §6、`design-project.md` §16.5）。
> 另：`getDefinedCommandIds()` 只含有 `<command>` 声明者；「有 handler 无声明」的 id 由桥从
> `org.eclipse.ui.handlers` 扩展点单独恢复，并在 `handlerOnly` 块中报出（`cmd.list`）。
> 该恢复路径的**运行期**效果（是否真能补上厂商 OptionBytes）见 `boundaries.md` U11。

---

## 9. 协议演进规则（向后兼容）

| 变更 | 允许性 | 版本动作 |
|---|---|---|
| **新增**方法 / 新增响应字段 | ✅ 向后兼容 | 升**次**版本 |
| 改既有方法**语义**（同名字段含义变、`OK`/`ERR` 判定规则变） | ⚠️ 不兼容 | **bump `PROTOCOL_VERSION`**；客户端拒绝不匹配 |
| **删除**方法 / 改响应格式（帧结构变） | ❌ 不兼容 | 仅**主**版本允许；破坏性变更走 `proto/vN` 分支 |

出处：`design-project.md` §17.6、`prd.md` R12.6。

**三条各一例**

1. **新增 = 次版本**：新增 `ui.console [--tail <n>]`（D3）。老客户端不认识它，但老的 13 个方法行为不变 ⇒
   只升次版本，`PROTOCOL_VERSION` 不动。
2. **改语义 = bump `PROTOCOL_VERSION`**：把 `cmd.runp showView` 的成功判定从「方法自身返回值」改为
   「`ui.parts` 回读差」——同一个请求、同一个响应形状，**含义变了** ⇒ bump `PROTOCOL_VERSION`，
   客户端启动时比对不符即报错，不进入怪行为。
3. **删除 = 主版本**：删除 `cmd.list`，把它的职责整体并入新方法 ⇒ 老的调用方会收到 `badrequest`，
   属破坏性 ⇒ 只在主版本（`proto/vN` 分支）里做。

**握手**：桥在 `sys.env` 里回报 `protocol=<N>`；客户端启动时比对
`PROTOCOL_VERSION` 不符即**报错退出**，不得继续（`design-project.md` §16.3）。
`PROTOCOL_VERSION` **独立于**项目版本与桥 `Bundle-Version` 编号（§15.2）。

**当前 `PROTOCOL_VERSION = 1`**（实现常量：`bridge/src/ctl/bridge/LiveBridge.java` 的
`static final int PROTOCOL_VERSION = 1;`；`sys.env` 报 `protocol=<N>`）。
期望输出形态见 `design-obs-ux.md` §14.7：
`OK  bridge live on 127.0.0.1:8777  (protocol 1, version 0.1.0)`。

---

## 10. 重连契约（D4）

1. 保活：客户端定期发 `sys.ping`（预算 ≤ 50 ms，`design-project.md` §17.5）。
2. 断线后按**指数退避**重连；端口走 §6 的 `endpoint.json`（或固定端口 + `--port`）。
3. **重连成功后必须先发 `sys.env`**，校验 `protocol` 与 `bundle` 版本；
   不符即报错，**不得**在版本不明的情况下继续发写方法。
4. 重连**不**自动重放未确认的写请求——是否重放由 §4.2 的回读差判定与 §7 的幂等标记共同决定。

---

## 11. CLI 侧错误串格式（A12 判据）

桥的 `ERR` 行是**协议内**回话；CLI 把它转成**可操作**的一行 **stderr**：

```
ERR <code> <message>; retry: <一条可复跑的完整命令>
```

- `retry:` 之后的命令**必须**是能直接复制执行的完整命令（含 `python -m ctl` 与全部参数）。
  只有**可变部分**用 `<value>` 占位（`<name>` `<run_id>` `<target>` `<detail>` `<path>`），
  使用者把占位符替换成实际值后即可执行。
- 该串**必须**能在 `TROUBLESHOOTING.md` 里 grep 命中**同一行**。
- 出错时的诊断**只走 stderr**；stdout 在 `--json` 下必须仍是纯机读
  （`design-project.md` §17.2/§17.3、`prd.md` A11b）。
- 桥侧码（`timeout` / `disabled` / `unhandled` / `noWorkbench` / `busy` 等）保留桥自己的 `message`，
  只在其后追加 `; retry: <处置动作对应的命令>`。

逐条清单（CLI 侧原样字符串 + 桥侧码的 retry 命令）见 `TROUBLESHOOTING.md` §7。
