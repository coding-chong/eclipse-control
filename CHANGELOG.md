# Changelog

本文件格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
**版本策略**：项目版本 **=** 桥 `Bundle-Version`（同号）；**协议版本** `PROTOCOL_VERSION` 独立编号，
仅在行协议变更时改动（`design-project.md` §15.2、`protocol.md` §9）。

当前 `PROTOCOL_VERSION = 1`。

## [Unreleased]

### Added

- **验收用例组 `realflow` 与新用例 `realflow.build_artifact`**：把「真实工作流」——**建工程 →
  写几行代码 → IDE 认它 → 构建出产物**——固化成一条可复跑的用例（`python -m ctl verify
  --group realflow`）。两个 target（GS32 / CCS）跑**同一段用例代码、同一组判据**，只有配方是
  per-target 数据：启动器、建工程命令（GS32 = 复制 CDT 模板 + 改 `.project` 的 `<name>`；
  CCS = 最小 `.projectspec` + `com.ti.ccstudio.apps.projectCreate`）、构建命令
  （CDT `headlessbuild` vs `com.ti.ccstudio.apps.projectBuild`）、构建配置名、产物名、`e_machine`。
  判据含**反假阳性**：写出的源文件带唯一标记 `CTL-REALFLOW-<8 hex>`，`main` 引用它，
  构建后在**产物字节里**找回该标记（GS32 = ASCII；C2000 默认 16 位 `char` ⇒ u16le），
  证明编的是**这次写的**代码而不是陈旧产物。目标缺配方 / 缺启动器 / 缺模板目录 ⇒ SKIP；
  配方齐备但跑挂 ⇒ FAIL。环境变量 `ECLIPSE_CTL_REALFLOW_<KEY>` 可覆盖配方标量以便换机器。
  实测 2026-10-03（两侧各跑多次）：GS32 `rc=0`（`realflow_gs32.elf` ≈551.6 KB · `e_machine=243`）·
  CCS `rc=0`（`realflow_ccs.out` ≈17.5 KB · `e_machine=141`）。产物大小随每次运行的随机标记
  差几个字节 ⇒ 只给量级；**稳定判据是 `e_machine` 与「标记能在产物字节里找到」**。
- **影子留档（shadow shots）—— 写动作后自动留一帧屏幕**：每次**写动作**完成后截一帧存进
  `<run_root>/<run_id>/shadow/`（`manifest.jsonl` + 帧），**默认不读**，出事时用
  `python -m ctl shadow --run-id <id> [--seq N] [--promote N] [--open N] [--prune]` 回看。
  新增 `tools/win-probe.ps1`（**一次** pwsh 调用同时产出窗口集 JSON 与像素）与 `ctl/shadow.py`
  （策略与簿记：sha256 去重 / 环形 20 帧·32 MB / promote / 清单）；挂钩在 `Client.request` 尾部，
  纯附加，**任何失败都不得影响请求结果或退出码**；开关 `--no-shadow` / `--shadow-only-changes`
  （优先级：命令行 > 环境变量 > 配置文件 > 默认）。
- **`ui.shells` 之外，窗口选题改由类名白名单定身份**：`pid` ∧ `class ∈ {SWT_Window0, #32770}` ∧
  `vis=True` ∧ 标题非辅助窗；**没有合法候选就 `rc=1` 且不写盘**（fail closed）。

### Fixed

- **`install` 用固定端口且不判占用 ⇒ 与活实例「共用」端口，`--stop` 再按端口误杀别人**（2026-10-03 实测踩到）：
  `effective_port = port or target.port` 直接取目标配置的固定端口，**没有任何占用判定**；而 `is_port_free()`
  只做 `bind()` 试探 —— Windows 上对端 Java `ServerSocket` 默认可 `SO_REUSEADDR`，**判不准**
  （`pick_port()` 那条「首个空闲端口」还是**死代码**，全仓零调用点）。
  实测代价：`install --target ccs12 --run-id rfv3-ccs` 与另一个 run 的实例（`ccs12-p42`）同占 8778，
  客户端连到**别人的桥**；收工时 `ensure_clean()` 的规则是 `victims[pid] = "listening on port %d"`
  ⇒ **按端口收、不按 run**，把不属于本次 run 的 pid 一并停掉。
  现在：未给 `--ensure-clean` 时，若目标端口有**非本 run** 的活监听 ⇒ **fail closed**（rc=2）并给出
  `--port <free port>` / `--ensure-clean` 两条可操作出路。三态实测：被占 ⇒ 拒绝并点名持有者 pid；
  空闲端口 ⇒ 照常起；`--ensure-clean` ⇒ 仍按原语义清理后起。同 run 自身的重装路径不受影响。
- **`ctl run` 的 `commands()` 静默吞掉 CCS 的 `undo` / `redo`**（真实工作流验证发现，2026-10-03）：
  该助手仍是旧启发式（`"." in token`），而 `cmd.list` 的 id 块**应按两行签名行框定、块内逐行照抄**
  —— 这条契约此前只修在 `ctl/__main__.py:_fetch_command_ids`，**同仓的第二个调用方没跟上**
  （`measurement-hygiene.md` §13.7「修一处不算修」）。后果：桥上 `returned=807`，
  库里 `len(commands())` 只有 **805**，且**无任何告警**；GS32 恰好每条 id 都带点 ⇒ **只在 CCS 一侧显形**。
  改为签名行框定后两侧实测：CCS `count=807`（`undo`/`redo` 归位）／GS32 `count=666`，
  **均与桥自报的 `returned=` 逐字相等**。
- **`ctl shadow` 的写方法判定漏掉 `cmd.runp`**（验收时发现，S4）：`sys.help` 的 `cmd.runp` 行
  **args 列自身含一个 `|`**（`<paramId|=paramName>=<value>`），朴素 `split("|")` 把列冲歪，
  `fields[2]` 不再是 write 列 ⇒ 该行被判成非写 ⇒ **`ctl cmd` 带参数时一律走 `cmd.runp`，
  等于绝大多数参数化命令写操作全都没被留档**，而且**没有任何告警**。
  改为按"第一个 `yes`/`no` 且其后紧跟合法 idempotent 值"定位写列。对拍：
  旧 `{cmd.run, ui.close, ui.open}` → 新 `{cmd.run, cmd.runp, ui.close, ui.open}`；12 个读方法零泄漏。
- **环形裁剪把 promoted 帧算进额度**：与"promoted 不计入额度"的约定矛盾 ⇒ 1 张 promoted 帧
  会静默吃掉 1 张普通帧的额度。
- **显式 `--port` 时不绑 `run_root`/`run_id`**：即使给了 `--run-id`，影子层也静默不写清单。
- **截图 tmp 文件残留**：`os.replace` 失败时只告警不删，`shadow/` 会积 `.pending-*.png`。
- **`tools/win-click-button.ps1` 的按钮路径不是 fail-closed**（`boundaries.md` §A6 / `implement.md` P6.3 遗留）：
  「命中 0」只打印 `no visible Button matching` 却 **`exit 0`**（**静默成功 —— A14 明禁**），
  「命中 >1」**静默点第一个**（与 §18.3「文本必须唯一，命中 0 或 >1 一律失败」冲突；
  直接调该工具的调用方，如 `ctl/screen.py` 的模态框处置路径，会拿不到失败信号）。
  改为：**0 命中 → `exit 1`**；**>1 命中 → `exit 1` 并列出候选**（`ERR ambiguous: N visible Buttons match …`）。
  实测三态（同机）：唯一命中 `rc=0` 且标题 `ctl-fixture`→`GO 1`；
  `-Text '&NoSuchButton'` → `rc=1`；`-Text '('`（消息框 3 个 Button 全含）→ `rc=1` + 三条候选。
  CLI 层本来就是这个契约，本次是**下层工具对齐上层**，不改 CLI 行为。

### Changed

- **影子探针固定用 `-Flags 0`**（不设为配置项）：观测通道不该扰动被测物 ——
  `resilience_modal_reset` 记着一条"`flags=2` 可能让活模态框消失"的未复现怀疑，而影子会按
  "新窗优先"恰好去拍那扇 `#32770`。拍空时工具会自己换档重试，故选 0 零代价。
  实测（2026-10-01，第三次独立测）：**两档都拍到活模态框、都没让它消失**。
- **写命令失败是异步的，回话会谎报 `OK`（用户在一张截图上发现的）**：
  `cmd.runp org.eclipse.ui.views.showView viewId=<不存在的视图>` 回话 `OK`、
  `executeCommand returned: null`，但 Eclipse 随后弹出 `Problem Occurred`（`ExecutionException`），
  且 `ui.parts` 的 `views` 纹丝不动 —— **界面没变 + 回话说成功**，只读协议回话的验证两头都看不见。
  - 新增**写方法窗口快照**：动作前后各取一次「可见且有标题的顶层 Shell 标题」快照，
    多出来的回报成 `dialog=appeared "<标题>"` + `dialog_note=…`（负载行，**不是错误码** ——
    有些命令本就该弹框，判断权留给调用方）。UI 被占住时回 `dialog=unknown (… timed out)`。
  - 实现要点：检查必须在 `onUi` **返回之后**、在连接线程上做（弹框是 UI 线程空闲后才出现的）；
    **排除空标题窗口**（全屏切换会冒无标题临时窗，会假阳性）；快照走 `asyncExec` + **有上限等待**。
  - **试过但无效、已记录别再走**：`ICommandService.addExecutionListener`
    （`org.eclipse.core.commands.IExecutionListener`）**抓不到** —— handler 正常返回，
    监听器看到的是成功。
  - 契约见 `protocol.md` §4.3（含客户端必须遵守的四条）。
- **`cmd.runp` 不接受短参数名**：文档/配方写的都是 `viewId=<id>`，而 `ICommand.getParameter()`
  只认参数**全 id**（`…showView.viewId`），实测被拒。现在先按全 id 查，再按「参数 id 去掉命令前缀
  的那一段」**唯一**匹配；命中 0 或 >1 一律失败并列出候选。
  ⚠️ 注意 `IParameter.getName()` 是**本地化显示标签**（实测 `name="View"`），不是 XML 属性名。
  短名支持让 `cmd.runp` 第一次有了成功记录（`views 8→9`，目标视图真出现）。
- **文档补"什么时候不留帧"**（交回门任务时的兼容性审计）：README 与 `skill/SKILL.md` 都补上
  ① 只读请求不留 ⇒ **`install` 之后看不到 `shadow/` 是正常的**（它全程只调
  `sys.ping`/`sys.help`/`sys.env`，一次写方法都没调）；② `sys.help` 拿不到 ⇒ 整个影子层
  对本次调用关闭（fail closed，不猜）；③ `--no-shadow`；④ 无合法候选窗 ⇒ `rc=1` 不写盘。
  实测依据：2026-10-01 真机 `install` 后确无 `shadow/`，跑一次写动作后才有。
- **`skill/SKILL.md` §4.2 补"最大不是身份"的告警**：`shot-window-pw.ps1` 的
  `picked largest` 只是启发式（控制台拉大/工作台缩小会**静默选错**），选窗的正确判据是
  R11 的四条件；该脚本**尚未**改用该规则 ⇒ **看到 `picked largest` 必须人工核对**。
  （此前 SKILL 只说"工具会自动选最大的"，与门任务坑表「不要再依赖 `picked largest`」矛盾。）
- **`TROUBLESHOOTING.md` §7 补齐：只覆盖 9 条 → 覆盖全部 59 条**（另 1 条通用兜底模板单列；2026-10-01）。
  用 `ast` 重抽 `ctl/*.py` + `ctl/verify/*.py` 里所有含 `retry: python -m ctl` 的字符串字面量
  （跨行隐式拼接由 AST 合并）：**60 条去重模板**；旧表只有 12 行、且多行左列写的是 `<detail>`/`<name>`
  这类占位符 ⇒ **真实错误串 grep 不到**，A12 判据本不可能成立。
  - 现在左列是**可 grep 的字面量**（判据落在"消息里那段稳定的文字"上；id/路径/耗时是变量，整行 grep 不现实）。
  - 表格加注**三种形态**：`ERR <code>` 行 / `doctor` 报告行 / `warning:` 行 ——
    并点明 **`PrereqNotReady` 的码是 `internal` 但退出码是 `2`**（同码不同退，判"能否继续"要看 rc）。
  - 附可复跑的核对脚本（含**证伪自测**：故意删掉一个覆盖用的字面量，脚本必须报缺口——
    否则"通过"是恒真的；见 `measurement-hygiene` §13.2 的 fail-closed 纪律）。
- **`SKILL.md` / `README.md` 补"别只看退出码"的口径**：写命令的弹框回报**只在回话的 `dialog=` 负载行里**，
  **不进退出码** —— 桥只交事实、判断留给调用方（`protocol.md` §4.3）。机器可读走 `--json` 的 `payload`。
  CI 拿 rc 串 `&&` 判成功会漏掉"界面没变 + 桥说 OK + 弹了错误框"这类动作。
  **本轮为零代码改动**：`ctl/**` 与 `bridge/**` 一行未动。

### Added

- **两份韧性用例**（新增 `resilience` 组）：`resilience.modal-reset`（模态框**六段证据**：
  请求时刻 / **发起连接自己**的 `ERR timeout` / **自抓截图并把框上的标题与按钮文字读出来** /
  子窗 `Button` 枚举 / 处置动作并复验已消失 / 恢复后探活）与 `resilience.timeout-applied`
  （**超时 ≠ 未生效**：`wm_close` 取消 ⇒ `applied=no`；声明按钮并 `BM_CLICK` ⇒ `applied=yes`
  且回读差是实的）。按按钮的地方**只有一处**（`Runner.answer_modal()`），默认只 `WM_CLOSE`
  （等同点标题栏 X，什么都不决定），仅当用例显式声明 `expects_modal={"title":…,"button":…}`
  且标题匹配才按键。
- **断线重连（D4）：客户端退避重连 + 重连后验身**（`ctl/client.py`、`--retry <SECONDS>`）。
  动机：IDE 重启（或被换掉）之后，长脚本应当能**自己续上**，但**绝不能**在不知情的情况下
  对着"另一个人"继续跑。
  · `--retry SECONDS`（默认 **0 = 立刻失败**，保持一次性命令的既有行为不变）启用后：
    连接失败按**指数退避**（0.5 s 起、封顶 5 s）重试，直到预算用尽。
  · 启用后**首次连上会先 `sys.env` 钉住 `(bundle, protocol)`**；**每次重连成功后必须再取一次
    `sys.env` 比对**，不一致 ⇒ `ERR internal … reconnected to a DIFFERENT bridge … refusing to
    continue`，**绝不带着它的状态往下跑**。
  · `Client` 同时暴露 `retry=` 与 `reconnects` 计数（供脚本/证据用）。
- **活体保留容量：满员后 `sys.ping` / `sys.env` / `sys.help` 仍然能答**（`protocol.md` §4.4）。
  动机是实测出来的：连接槽按 `accept()` 计入，**8 条只是连着、不发任何请求**的连接就能把全功能槽占满
  （每条占满 `SOCKET_READ_TIMEOUT_MS`=60 s），此后连 `sys.ping` 都只能拿到 `ERR busy` ——
  **运维观测能力被平凡地打掉**，而且从外面分不清「忙」与「死」。
  现在：`1..8` 全功能；`9..12` 只准那三个不碰 UI 也不阻塞的方法（`sys.wait` 会阻塞，不放行）；
  `>=13` 才 `ERR busy`。保留槽越权与连接槽全满的 `ERR busy` 消息文本不同，**按错误码判断**。
- **屏幕守卫接进用例执行器**（门 G10）：`ctl/screen.py` + `ctl/verify/runner.py`。
  写组用例**自动**在动作前后各枚举一次可见窗口，多出来的弹框即 **FAIL**（除非用例声明
  `expects_dialog`），每条新窗自动 PrintWindow 截图归档到 `<run_root>/<run_id>/shots/`，
  并与桥的 `dialog=` 行**交叉验证**（不一致会报出来）；收尾自动 `WM_CLOSE` 并复验、终扫不留残余。
  为什么必须有它：写命令的失败是**异步**的，「`OK` + 回读差为 0」与「幂等成功」**长得一模一样**
  （`chore` 见 §Fixed 与 `protocol.md` §4.3）。`--no-screen-guard` 只用于复现该漏洞，`preflight` 恒关。
- **写用例 4 条**（`write.open-editor` / `write.close-view` / `write.runp-show-view` / `write.run-toggle`）：
  每条给「协议回话 + 回读差 + 屏幕检查结论」三样，跑完回到 `pre` 状态。
- **反例回归 1 条**（`errors.plugin-id-as-view`）：固化的**不是缺陷而是判定** —— 它**通过**的条件是
  「被判定为 FAIL/SUSPECT」。
- **错误契约用例 4 类**（未知方法 / 坏参数 / 目标不存在 / 命令不可用），每类贴协议原文。

### Fixed

- **`doctor` 会让一个健康会话"自毁"**（两层）：
  ① 端口被占时一律记 `FAIL` 并把 retry 指向 `doctor --ensure-clean` —— 而当占用者
  **就是本 run 自己的实例**时，照提示执行会**把正在用的实例杀掉**（实测：实例健康、
  `endpoint.json` 里就是那个 pid，doctor 仍报 2 条 FAIL 并 `exit 2`）。
  ② 「无残留实例」扫的是**整个 run_root**，任何**兄弟 run_id** 的存活实例都算 FAIL ——
  而兄弟实例各有自己的 run_id / 配置区 / 端口，**根本不撞车**；该 FAIL 也无法被它给的 retry 消除
  （实测照做后同一行原样存在，而 `install` 反而成功）。
  现在：占用者若属于本 run_root ⇒ **`INFO`**（提示用 `status` 对话或换 `--port`）；
  只有**外来**占用者才 `FAIL`。兄弟实例记 `INFO` 并说明不阻塞新 run。`INFO` 不参与退出码，
  实测健康实例下 `doctor` 由 `exit 2` 变为 **`rc=0`**。
- **`win-close.ps1` 在「一个都没匹配到」时返回 `rc=0`** —— 脚本写
  `win-close; if rc==0 then 认为已关` 会把**没关掉**当成**关掉了**（同族的 `win-click-button.ps1`
  同样情形返回 `1`）。现在未匹配即 `exit 1`。
- **`win-enum.ps1` 的 pid 参数叫 `-Target`**，而同族的 `win-close` / `win-click-button` /
  `shot-window-pw` 都叫 `-ProcId`。已改名为 `-ProcId`，并保留 **`-Target` 别名**（旧笔记与配方照旧可用）。
- **`shot-window-pw.ps1` 会把一张全黑的图当成成功截图**：`PrintWindow` 即便什么都没画也返回 TRUE，
  老脚本照样写 PNG 并打印 `ok=True`。实测（GPU 合成的 Chromium 窗口 Edge，2744x1828）：
  `-Flags 0` 拍出来 **75.5% 字节为零、3000 像素样本里只剩 2 种颜色**（即基本全黑），却被报成成功
  —— 一张假图会"证明"那个窗口里什么都没有。现在：**判空 → 换另一档 flags 重试一次 → 仍空白就
  `stderr` 报错、不写盘、`rc=1`**（照 `open-computer-use-fixed` 的 `Capture-WindowPngBase64` 语义）。
  实测 `-Flags 0` 现在会自动退到 `flags=2` 并如实标注 `(blank with flags=0 -> retried flags=2)`。
  另加 `-ProcId` / `-Class`：标题不唯一（两个实例可能同名），`ui.open` 还会把文件名写进主窗标题。
  **不再「先匹配先赢」，改为选面积最大的那扇**：GS32_Studio 的**启动器控制台**是一扇可见顶层窗，
  标题 `D:\ProgramFiles\...\GS32_Studio_v1.2.5.2\GS32.exe` **含 `GS32_Studio`** 且**同 pid**
  （`-ProcId` 分不开），且在 `EnumWindows` 顺序里排在前面 —— 实测旧版因此把 **2048x1536 的工作台**
  拍成了 **800x500 的黑控制台**（29 KB vs 1.95 MB）并报 `ok=True`。现在选最大的，并打印全部候选
  （`picked largest of N matching: ConsoleWindowClass:..., SWT_Window0:...`），歧义不再静默。
  **最小化/离屏目标也拒绝**：`IsIconic` 或 rect 落在 -32000 哨兵上时 `rc=1`、不写盘
  （实测：`-TitleLike "GS32_Studio"` 会匹配到最小化的那个同名窗，产出 353x56 的无用图，
  旧脚本照样 `ok=True`；且实测 **pid 880 与 13104 两个进程都叫 `ws - GS32_Studio`**）。
  **与 `open-computer-use-fixed` 逐字节对拍**：同一窗口、同一时刻，两者 sha256 **完全相同**
  （两组各 167807 B / 167805 B），确认渲染质量等同，我们只是补上了它早就有的诚实性。
- **`gc` 是静默的破坏性命令（安全性）**：它
  ① 从 `common` 继承了 `--run-id` 却**完全忽略**（其它子命令里该参数是"作用域"，于是传它反而像"只扫我的"）；
  ② **无 dry-run**，`dry_run=False` 写死，CLI 也不暴露开关；
  ③ **不检查活实例**，`shutil.rmtree(..., ignore_errors=True)` 对手握句柄的活进程会**只删掉一部分**
  —— 目录还在、内容已残，且静默。
  实测代价：一次「把每个子命令都点一遍」的探索，把 `runs/` 从 **30 个删到 4 个**，其中包含另一个会话
  **正在运行**的实例（`endpoint.json`/`bridge.log`/`shots/` 全没，只剩删不掉的 `ws/`）。
  现在：`gc` 用自己的选项集（**不再接受 `--run-id`**，无法兑现的选项不该被接受）；**默认 dry-run**，
  必须 `--yes` 才删；**跳过 `endpoint.json` 中 pid 仍存活的 run**（除非显式 `--force-live`）；
  新增 `--keep N`；删不干净的目录**逐条上报**并 `rc=1`，不再吞掉。
- **`win-click-button.ps1` 没有 pid 过滤**：实测到**两个实例同时**都显示标题为 `Reset Perspective` 的
  `#32770`，于是无范围的 `BM_CLICK` **可能按到别的实例的按钮** —— 而按按钮是替用户做的不可逆决定。
  已加 `-ProcId`（对齐 `win-close.ps1`）。
- **`win-enum.ps1` 文档写着 `-Class "#32770"` 却没实现**：传了也**静默列出全部窗口** ——
  过滤看起来发生了，其实没有。已补 `-Class`。
- **`upgrade` 会把 run 的端口漂回默认**：`install --run-id u1 --port 8939` 之后跑不带 `--port` 的
  `upgrade --run-id u1`，新实例起在了默认 **8777**，`endpoint.json` 也被改写 ——
  而端口是 run 身份的一部分，外部工具/长脚本手里握着旧端口，下次连接就会"突然连不上"，
  且与"桥挂了"难以区分。现在：用户给了 `--port` 就听用户的，否则**沿用该 run 已记录的端口**。
- **拒绝路径会发 RST，客户端可能连 `ERR busy` 都收不到**：`rejectBusy` **不读**客户端发来的请求行
  就直接 `close()`，未读字节让 OS 发 RST —— 实测客户端 `recv` 抛 `ConnectionAbortedError [WinError 10053]`。
  改为 **flush → `shutdownOutput()`（送 FIN）→ 把未读字节排空（上限 500 ms）→ 再 close**。
- **桥把「同一扇窗改了标题」误报成新窗（假阳性）**：原先按**标题串**做差，而 `ui.open` 会把文件名
  写进**主窗标题**，于是一次干净的写也回 `dialog=appeared "ws - … - GS32_Studio"`。
  改为按**窗口身份**做差（`System.identityHashCode(shell)`；`Object` 级、不碰 SWT 控件、可跨线程带走）。
  实测：`ui.open` ×2 的 dialog 行数 **1 → 0**；坏 `viewId` 仍如实报 `"Problem Occurred"`；全屏开关 0。
- **用例对环境的依赖**：Eclipse 会把重复的同类错误合并成 `Multiple problems have occurred` 聚合框；
  它若已在屏上，守卫的 `pre` 快照就含它，新失败**不算新窗** ⇒ `expects_dialog` 用例**假失败**。
  新增 `Runner.clean_room`：连上实例后先关掉**本实例的** `#32770`。
  **绝不按标题**（`ui.open` 改过主窗标题，按名关窗会关掉工作台）；**拿不到实例 pid 就不做**
  （`None` 意为「所有进程」，会去关别的程序的对话框）—— 同一道闸也加到了 `rescue_dialogs` / `dismiss`。
- **README 与实现文档里的照抄命令参数写错**：`verify`/`cmd`/`open`/`close` 收的是 `--run-id`，
  不是 `--target`；写命令还漏了 `--yes`（**静默变成 dry-run，什么都不发生**）。

### Changed

- **纠正「模态框会让后续 UI 调用 `ERR timeout`」这条旧表述**（`protocol.md` §4.2 第 5 条）。
  实测推翻：`Reset Perspective` 在屏时，**另一条连接**的 `ui.parts` / `ui.tree` / `ui.persp` /
  `sys.ping` **全部正常返回**（0.00–0.02 s），**只有发起那次请求自己**在 ~15.4 s 后 `ERR timeout`。
  原因：SWT 模态框跑**嵌套事件循环**，`Display.asyncExec` 队列照常派发。
  ⇒ 「超时」是**每条连接自己的**事，不是全局状态；**不能**用「`ui.*` 通不通」判断界面有没有被占住。
- **`idempotent` 列三个待定值实测回填**（`protocol.md` §7）：
  `ui.open` → **`true`**（同一文件连开两次 `editors` **1→1**）；
  `cmd.run` / `cmd.runp` → **`per-command`**（新增取值）。
  **`per-command` 的含义**：一个方法名承载任意命令，方法级无从保证 ⇒ 与 `unknown` **同等保守**
  （**不允许自动重试**）。依据：`org.eclipse.ui.window.fullscreenmode` 是开关型命令，
  连点两次**回到原状** —— 幂等性取决于**被调命令**，不是方法。

### Removed

- **`token` 可选启用 / 连接后首行 `auth <token>`：凭空来的特性，已删（2026-10-03）**。
  它不是用户需求：需求条目由 AI 自写进 `prd.md`（**流程仓** `2d535e9`，2026-10-01），客户端那半
  `auth <token>` 同期由 AI 自写（**本仓** `6fd6e3e`），**桥侧从未实现**该握手 ⇒ 现在整体移除，而不是补实现。
  移除面：`Config.token` 与配置键 / 环境变量 `ECLIPSE_CTL_TOKEN`（`ctl/targets.py`）·
  `Client` / `talk` / `from_run` / `Runner` / `wait_for_bridge` / `wait_for_workbench` /
  `ShadowConfig` 的 `token` 形参 · `endpoint.json` 的 `token` 字段（`ctl/client.py`）·
  `protocol.md` §5（改为「本工具不提供鉴权」）· `SECURITY-REVIEW.md`（原条目改为 **该项不存在，已删**）·
  `README.md` 配置表里的 `token` 行。
  复核：`grep -rn 'token\|auth' ctl/ bridge/src/ protocol.md SECURITY-REVIEW.md` 不再命中原功能面；
  `python -m compileall -q ctl` rc=0；`python -m unittest discover -s tests -t .` 25 条全绿；
  `python -m ctl --help` / `python -m ctl status --help` 正常。

## [0.1.0] - 2026-10-01

首个版本。`eclipse-ctl` 立项收口：把「往 Eclipse 系 IDE 进程热注入薄桥，从外部读界面 / 发命令」
从散落的临时实证收成可复用、可验证的独立仓（`prd.md` §1）。

### Added

- **行协议契约文档**：`protocol.md` —— 帧格式（请求一行；响应 `OK|ERR` 一行 + 负载行 + `END`）、
  错误码闭集、超时语义、鉴权、端口发现、协议演进规则。
- **错误码闭集**：`badrequest` / `notfound` / `disabled` / `unhandled` / `timeout` / `noWorkbench` /
  `internal` / `busy`，共 8 个；`NotEnabledException` / `NotHandledException` 不再以裸异常串返回
  （`design.md` §3）。
- **超时语义**（`protocol.md` §4）：客户端默认 25 s；桥侧 UI 调用上限默认 15 s，可用
  `-Dctl.uiTimeoutMs` 配置；**`ERR timeout` ≠ 「未生效」**——超时后必须再取回读差。
- **写操作幂等标记**：`protocol.md` §7 方法表新增 `idempotent` 列（供 dry-run / 审批闸 / 重试策略使用）。
- **端口可配**：`-Dctl.port` > 环境变量 `CTL_PORT` > 默认 `8777`。
- **端口发现**：每次运行写 `<run_root>/<run_id>/endpoint.json`
  （`port` / `pid` / `configuration` / `started_at`）。
- **边界清单**：`boundaries.md` —— 能做 / 不能做 / 未验证三节，粒度到方法级，每条带出处；
  「未验证」条目各带验证入口。
- **故障排查表**：`TROUBLESHOOTING.md` —— 覆盖 `design-obs-ux.md` §14.5 全部症状行，
  另含 CLI 错误串 ↔ 本文件命中行（A12 判据）。
- **安全复审记录**：`SECURITY-REVIEW.md` —— 五字段（日期 / 复审人 / 改动文件 / 判定 / 复核命令）格式，
  首条实体记录覆盖「桥只绑 `127.0.0.1`」。
- **用法样例库**：`recipes/` —— `view-and-shot` / `open-sources` / `build-and-console` /
  `diag-when-hung` / `record`（`design-obs-ux.md` §14.8）。
- **AI 用法说明**：`skill/SKILL.md`（含「超时后怎么办」小节）。
- **仓库卫生**：`.gitignore` 拦运行目录副本、构建产物（`bridge/out/`、`bridge/dist/`）、
  `**/__pycache__/`、`*.pyc` 与截图产物。
- **许可证**：`LICENSE` = MIT。

### Changed

- **命名统一（方案 A）**：桥 `Bundle-SymbolicName` 由 `livebridge` 改为 **`eclipse-ctl.bridge`**，
  与项目同名同号；Java 包名改为 **`ctl.bridge`**（Java 包名不能含 `-`），
  源码路径 `bridge/src/ctl/bridge/LiveBridge.java`，`Bundle-Activator: ctl.bridge.LiveBridge`。
  类名 `LiveBridge` 属裁决后的正确名，不计入「产物里不得出现 `livebridge`」的判法
  （`design-project.md` §15.1、`prd.md` A11 判法）。

### Fixed

- `cmd.list` / `ui.viewids` 的全量导出契约：空前缀 = 全量，且必须带 `total` / `returned` / `truncated`
  三字段（旧产物写死 `if (n <= 300)`，报 `total=666` 却只列 300 条；`design.md` §6、
  `design-project.md` §16.5）。

### 未随本版宣称（仍在 `boundaries.md` 里挂「未验证」）

- `-configuration <run_root>/<run_id>/configuration` 的运行配置区隔离是否生效 → `boundaries.md` U4（P0.4b 三项判据）。
- `cmd.list` 全量导出的**代码落地**（本文件写作时源码仍见硬截断）→ `boundaries.md` U5。
- 三个 `idempotent` 值（`showView` / `ui.open` / `cmd.run`）回填 → `boundaries.md` U12（P2.1）。
- 「同时只能用一个实例」是否仍是桥的固有性质 → `boundaries.md` U1。
- `LICENSE` 暂定 **MIT**，待复核（`prd.md` A11 兜底条款）。
