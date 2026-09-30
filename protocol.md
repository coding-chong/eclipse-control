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
- 唯一例外是鉴权首行 `auth <token>`（见 §5），它不出现在普通请求流里。

### 2.2 响应

成功：

```
OK <一行摘要>
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

1. **首行一定是 `OK` 或 `ERR` 开头的一行摘要**；此后是 0..N 行负载；最后一行是**单独的 `END`**。
2. `END` 是帧终止符。客户端**必须读到 `END` 才认为一帧结束**；读到 `END` 之前就断开 = 帧不完整。
3. `ERR` 的首行形如 `ERR <code> <message>`，`code` 取自 §3 的闭集，`message` 是**人类可读的一行**。
4. 负载行**不保证**是合法 JSON；它是给人看、给 grep 的文本。机读请用 CLI 的 `--json`（`design-obs-ux.md` §14.3），
   不要把负载行当机读接口。

**示例（真实形状，取自 `research/facts-baseline.md` §3）**

```
REQ  sys.env
OK   java.version=23.0.2 | os.name=Windows 11 | bundle=eclipse-ctl.bridge id=351 state=32 | thread=gs32ctl-bridge
END
```

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
**已经排进 `Display` 队列的 Runnable 仍会执行**，副作用只是延后到模态框被解除之后。

因此：

1. `ERR timeout` 只表示**本次应答**超时；**不是**「没执行」的判据。
   桥的 `ERR timeout` message 本身就把这件事写在字面上：
   `UI task did not finish within <N> ms; the action is still queued on the SWT event thread and MAY still take effect - read back before retrying`。
2. 副作用是否落地**桥无法自证**，因此**没有**服务端 `applied` 字段可供采信；
   客户端**回读后自行判定** `applied=yes|no|unknown`，并把该差值**归因到先前那次超时请求**
   （不是为了给下一次动作当基线）。
3. 回读判定为 `applied=yes` ⇒ **不要再重发**（否则会执行两次）。
4. **只有幂等方法**（§7 表 `idempotent=true`）允许自动重试。
5. 模态框挂着时，**UI 类方法（`ui.*` / `cmd.*`）一律 `ERR timeout`**，不会假成功；
   **非 UI 类方法（`sys.ping` / `sys.env`）照常响应**——这就是「僵死 vs 可运维」的分界
   （`design-project.md` §16.4，判据 G3）。

超时后的**标准自救顺序**（`design.md` §5、`design-obs-ux.md` §13.2）：
① 先截图看清框上写了什么 → ② 枚举子窗拿到按钮列表 → ③ 处置（默认 `WM_CLOSE` 关窗；
用例显式声明时才 `BM_CLICK` 按下指定按钮）→ ④ 探活 → ⑤ **对超时请求再做一次回读差**。
可照抄命令见 `recipes/diag-when-hung.md`。

---

## 5. 鉴权

- 桥**只绑 `127.0.0.1`**，局域网不可达（`design-project.md` §15.4 安全基线 1）。
- `token` **可选**：配置里 `token` 非空即启用校验。启用后，客户端在**连接后的第一行**发送：

  ```
  auth <token>
  ```

  其它任何请求之前必须先过这一行。`token` 为空（默认）则**不校验**，直接发普通请求。
- `token` 不通过 ⇒ `ERR badrequest <message>`，随后连接关闭；客户端不得在该连接上重试。

---

## 6. 端口发现（`endpoint.json`）

桥的实际端口由「从 `8777` 起取首个空闲」决定（`design.md` §10、`design-obs-ux.md` §14.3），
因此**客户端不能假设端口一定是 8777**。每次运行会把寻址信息写进：

```
<run_root>/<run_id>/endpoint.json
```

| 字段 | 类型 | 含义 |
|---|---|---|
| `port` | int | 本次运行的桥端口（连接 `127.0.0.1:<port>`） |
| `token` | string? | 启用鉴权时的 token；**可选字段**，未启用则省略 |
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
**不读它就无法知道「首个空闲」到底落在哪个端口**。

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
| `ui.open <abs path>` | 写 | 是 | `unknown` | `editors` 计数 +1，且 class = `org.eclipse.cdt.internal.ui.editor.CEditor` |
| `cmd.run <id>` | 写 | 是 | `unknown` | **依命令而定**（多数需专门判据） |
| `cmd.runp <id> <paramId>=<value>` | 写 | 是 | `unknown` | 依具体命令：`showView` → views 集合新增该 id；`showPerspective` → perspective id 变化 |

> **`unknown` 的语义**：**不允许自动重试**（保守默认，`design.md` §7）。
> `ui.open` / `cmd.run` / `cmd.runp` 的 3 个 `unknown` 是 **P2.1 待实测回填**的占位，
> 回填前不得假设其幂等性，也不得照抄惯例（D5）。
> `cmd.runp` 是**一个**方法名承载多条命令，故其幂等性按命令而定（设计 §7 表里 `showPerspective` 标
> `true`、`showView` 标「待回填」）——回填后以 `sys.help` 报出的值为准。
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
  只有**可变部分**用 `<token>` 占位（`<name>` `<run_id>` `<target>` `<detail>` `<path>`），
  使用者把占位符替换成实际值后即可执行。
- 该串**必须**能在 `TROUBLESHOOTING.md` 里 grep 命中**同一行**。
- 出错时的诊断**只走 stderr**；stdout 在 `--json` 下必须仍是纯机读
  （`design-project.md` §17.2/§17.3、`prd.md` A11b）。
- 桥侧码（`timeout` / `disabled` / `unhandled` / `noWorkbench` / `busy` 等）保留桥自己的 `message`，
  只在其后追加 `; retry: <处置动作对应的命令>`。

逐条清单（CLI 侧原样字符串 + 桥侧码的 retry 命令）见 `TROUBLESHOOTING.md` §7。
