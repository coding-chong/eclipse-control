# eclipse-ctl

给 Eclipse 系 IDE（GS32_Studio / CCS / 任意 Equinox 产品）装一条**外部控制通道**：
一个热注入的桥 bundle + 一套脚本化客户端。AI、CI、人都用它把「手点界面」变成**可 diff、可进 CI 的脚本**。

**定位**：`ctl` 之于 Eclipse，约等于 **CDP 之于 Chromium** —— 有读面（部件/控件/命令表/Console）、
有写面（执行命令/开文件/切透视图）、有输入面（按控件 `BM_CLICK`）。**没有**坐标注入（未证实，已决定不投入）。

---

## 速查表

| 我想… | 命令 |
|---|---|
| 看环境到底行不行 | `python -m ctl doctor --target gs32` |
| 装桥并起一个实例 | `python -m ctl install --target gs32` |
| 单次调用（读） | `python -m ctl parts --run-id <id> --json` |
| 敲任意桥方法 | `python -m ctl shell --run-id <id> -c "ui.parts"` |
| 导出命令表（机读） | `python -m ctl commands --json > commands.json` |
| 按 UI 文字反查命令 id | `python -m ctl commands find --text "Reset Perspective"` |
| 跑门禁用例 | `python -m ctl verify --group write --run-id <id>`（组：`read` / `write` / `errors`） |
| 跑全部门禁 | `python -m ctl verify --all --run-id <id>` |
| 回看某次动作之后的屏幕 | `python -m ctl shadow --run-id <id>`（`--seq N` 取那一帧，`--open N` 打开） |
| 关掉影子留档 | 任意子命令加 `--no-shadow`；只在变化/异常时留用 `--shadow-only-changes` |
| 长脚本扛 IDE 重启 | 加 `--retry 120`（退避重连；重连后验身，版本不符则报错退出） |
| 卸桥并自检干净 | `python -m ctl uninstall --target gs32 --verify-clean` |
| 编译打包桥 | `python -m ctl build --target gs32` |
| 发布前总检 | `python -m ctl preflight --target gs32,ccs12` |

**退出码三态**：`0` 成功　`1` 失败（有明确 FAIL 结论，含用法错误）　`2` **前置未就绪**（环境没准备好，压根没开跑）。
> ⚠️ **`rc=0` 不代表"没有弹框"**：写命令的弹框回报只在回话的 `dialog=` 负载行里，**不进退出码**
> —— 桥只交事实、判断留给调用方（`protocol.md` §4.3 有专节写为什么不做成错误码）。
> **CI/脚本不要只看 rc**：检查那一行（机器可读走 `--json` 的 `payload`），或直接用 `ctl verify`（写用例自带屏幕检查）。
**写操作要加 `--yes`**（缺省只打印将要发送的请求，不建连接）。
**写用例自带屏幕检查**：动作前后各枚举一次可见窗口，多出来的弹框即判 **FAIL**
（除非用例声明 `expects_dialog`），并自动截图归档到 `<run_root>/<run_id>/shots/`。
理由见 `protocol.md` §4.3：写命令的失败是**异步**的，回话里的 `OK` 会撒谎 ——
`cmd.runp showView viewId=<不存在的视图>` 回 `OK`、回读差为 0，屏幕上却弹着 `Problem Occurred`。
`--no-screen-guard` 只用于复现这个漏洞，`preflight` 里恒为关。

**影子留档（`ctl shadow`）**：每次**写动作**完成后自动留一帧屏幕到
`<run_root>/<run_id>/shadow/`（`manifest.jsonl` + 帧），**默认不读**，出事时回看。
与 `shots/` 分工不同：`shots/` 是"我被要求证明什么"（验收证据），`shadow/` 是"当时屏幕长什么样"（常备留档）。

- **留哪扇窗**：四条同时满足 —— `pid` = 目标实例 ∧ `class ∈ {SWT_Window0, #32770}` ∧ `vis=True`
  ∧ 标题不是已知辅助窗（`PartRenderingEngine's limbo` / `SWT_Window_GS32_Studio`）。
  **没有合法候选就 `rc=1` 且不写盘**（fail closed）—— 一张来历不明的窗口被记成"当时界面就是这样"，
  比没有这张图更糟。
- **`SWT_Window0` 不是工作台专属**：实测同一 pid 下有 3 扇顶层 `SWT_Window0`；
  启动器控制台与工作台**同 pid、标题同含 `GS32_Studio`、都可见**，面积差只有 18%
  ⇒ 面积只能当白名单**内**的次级判据，身份靠类名 + 可见性 + 标题。
- **帧不是判据**：它**不参与任何 PASS/FAIL**。`PrintWindow` 存在"返回 TRUE 却画全黑"的失败模式，
  会撒谎的通道不能当断言。清理用 `--no-shadow`；`ctl shadow --prune` 按环形上限（默认 20 帧 / 32 MB）裁剪，
  失败/超时/弹框触发的帧会被 **promote** 且永不裁。
- **什么时候不留帧（看到空目录别以为坏了）**：
  ① **只读请求不留**。判据是桥 `sys.help` 的**写列**（`cmd.run` / `cmd.runp` / `ui.open` / `ui.close`），
     不另立名单。⇒ **`install` 装完看不到 `shadow/` 是正常的**：它只做打包/拷贝/探活，
     一次**桥写方法都没调**（全程 `sys.ping` / `sys.help` / `sys.env`）。
  ② **`sys.help` 拿不到**（桥不可达 / IDE 卡死）⇒ 判定依据没了，**整个影子层对本次调用保持关闭**，
     只在 stderr 打一条 `sys.help unavailable …; the whole layer stays off`。这是 fail closed：**不猜**。
     代价要知道：**桥完全不可达时影子也无能为力**（只有 `ERR timeout` 那一类"桥还活着、UI 卡住"它才拍得到）。
  ③ `--no-shadow`（或配置关掉）。　④ 没有合法候选窗 ⇒ `rc=1` 且**不写盘**（见上一条 fail closed）。

---

## 三层边界（摘要）

| 层 | 进 IDE 进程？ | 能做什么 | 不能做什么 |
|---|---|---|---|
| ① Gogo 控制台 | 否（stdin/stdout） | 装卸/启停 bundle、列服务、查扩展点、`fork/exec` | **不能反射调用任意 Java 方法**（Felix 的 `inspect` 不是 Equinox 的） |
| ② 桥 bundle | **是** | 读部件/控件树/命令表/Console；执行命令；开文件 | 只在**已创建的 UI** 上工作；**弹模态框会阻塞**（桥侧有超时保底） |
| ③ 工具链 CLI | 否 | 编译、烧写、调试（另任务） | 与 IDE 进程无关 |

完整方法级契约见 [`boundaries.md`](boundaries.md) —— 每条「能做/不能做/未验证」都带证据字段。

---

## 快速开始

```bash
# 1. 编译桥（本机无 javac，借目标安装树里的 ECJ + JRE）
python -m ctl build --target gs32

# 2. 自检：目标安装树、JRE、控制台、（可选）驱动
python -m ctl doctor --target gs32

# 3. 起实例 + 热装桥 + 探活
python -m ctl install --target gs32 --run-id demo

# 4. 读一眼
python -m ctl parts   --run-id demo
python -m ctl viewids --run-id demo com.gs

# 5. 收工
python -m ctl uninstall --target gs32 --run-id demo --verify-clean
```

每个运行实例一个目录 `<run_root>/<run_id>/`，内含 `configuration/`（Equinox 配置区）、
`ws/`（工作区）、`bridge.log`、`endpoint.json`（端口发现）。**不同 `run_id` 互不干扰**，可并行。

---

## 配置文件

**载体**：`~/.eclipse-ctl/config.json`（与运行目录同级）。**没有这个文件就等于全用内置默认** —— 不必须存在。

**完整示例（照抄这个改）**：

```json
{
  "default_target": "gs32",
  "run_root": "D:/tmp/eclipse-ctl",
  "keep_runs": 3,
  "copy": false,
  "token": "",
  "allow_dangerous": false,
  "targets": {
    "gs32":  { "source_dir": "D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2", "java_level": "17", "port": 8777 },
    "ccs12": { "source_dir": "D:/ti/ccs1281/ccs/eclipse",                                  "java_level": "11", "port": 8778 }
  }
}
```

| 字段 | 作用 |
|---|---|
| `default_target` | 不给 `--target` 时用谁（内置默认 `gs32`） |
| `run_root` | 运行实例的根目录；每个 `run_id` 一个子目录。内置默认 `~/.eclipse-ctl/runs` |
| `keep_runs` | `ctl gc` 保留最近几次 run（内置默认 3） |
| `copy` | `false`（默认）= **一份源安装树跑多实例**，只写运行配置区；`true` = 每实例复制整份安装树（`-configuration` 隔离实测不生效时的回退） |
| `token` | 桥的鉴权串；非空时客户端每次请求都要带 |
| `allow_dangerous` | 放行 `gc` 这类破坏性命令的默认 dry-run（等价于 `--allow-dangerous`） |
| `targets.<名>` | 目标矩阵：`source_dir` 安装树 / `java_level` 编译级别 / `port` 默认端口 |

> `source_dir` / `java_level` 是**别名**，内部字段名是 `install_dir` / `java_target`；两种写法都吃。

**三层覆盖（优先级从低到高）**：

```bash
ECLIPSE_CTL_PORT=8899 python -m ctl status --target gs32   # ① 环境变量（Eclipse_CTL_ 前缀）
python -m ctl status --target gs32 --port 8890             # ② 命令行 flag（最高）
python -m ctl status --target gs32 --config ./my.json      # ③ 换整份配置
```

**新增一个目标**（比如同事的另一个 Eclipse 系 IDE）：

```bash
python -m ctl targets list
python -m ctl targets add myide --source-dir "D:/path/to/ide" --java-level 17
python -m ctl targets remove myide
```

---

## 五分钟上手（每步给期望输出）

> 下列输出是 **2026-10-01 在 GS32_Studio v1.2.5.2 绿色版上的原样实测记录**，不是排版的样例；
> 其中 `doctor` 一段为 **2026-10-02 重测**（桥 jar 命名与 Java 级别校验收紧后）。
> ⚠️ **写操作必须带 `--yes`** —— 不带只打印 `DRY-RUN` 不发送（dry-run 落在**客户端**，桥没有 dry-run 概念）。
> 不带 `--yes` 的代价：下面 **3b** 那条「回话撒谎」的教训你**永远看不到**。

```bash
# 0) 自检 —— 不写任何东西，先看机器行不行
$ python -m ctl doctor --target gs32
target gs32
  [PASS] source_dir exists        D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2
  [PASS] platform / JRE           Eclipse 4.30.0 (expected 4.30.0); JRE 23.0.2 (expected 23.0.2, 30 modules)
  [PASS] ECJ compiler             org.eclipse.jdt.core.compiler.batch_3.36.0.v20231114-0937.jar
  [PASS] bridge buildable         bridge\dist\eclipse-ctl.bridge_3.1.0_gs32.jar (Bundle-Version 3.1.0); class-file 61 (Java 17) matches java_target 17
  [PASS] port 8777                free
  [PASS] no leftover instance     0 process under C:\Users\Alice\.eclipse-ctl\runs
  [PASS] run_root writable        C:\Users\Alice\.eclipse-ctl\runs (163.3 GiB free)
  [SKIP] installed version        no run installed for target gs32
all checks passed

# 若最后一行是 [FAIL] installed version … cannot reach bridge on 127.0.0.1:8777，
# 而 "no leftover instance" 仍是 [PASS] —— 那是**残留的安装记录**（登记在、桥没起），
# 不是环境问题：清掉那一次的 run（`ctl uninstall --target gs32 --run-id <那次> --verify-clean`）
# 或让它被 `ctl gc` 回收即可。退出码此时是 2（前置未就绪），不是 1。

# 1) 装 —— 一条命令（no-copy：只借 IDE 的 plugins，配置区隔离在 run 目录下）
$ python -m ctl install --target gs32 --run-id w --port 8905
run_id      w
configuration C:\Users\Alice\.eclipse-ctl\runs\w\configuration
workspace   C:\Users\Alice\.eclipse-ctl\runs\w\ws
endpoint    C:\Users\Alice\.eclipse-ctl\runs\w\endpoint.json
OK bridge live on 127.0.0.1:8905 (protocol 1, version 3.1.0)

# 2) 看 —— 只读方法**默认真发**，不需要任何开关
$ python -m ctl parts --run-id w
OK
workbenchWindows=1 activeWindow=org.eclipse.ui.internal.WorkbenchWindow@1ff463bb
perspective id=org.eclipse.cdt.ui.CPerspective label="C/C++"
views=8
  view id=org.eclipse.ui.navigator.ProjectExplorer title="Project Explorer"
  view id=org.eclipse.ui.views.ProblemView title="Problems (0 items)"
  view id=org.eclipse.ui.views.TaskList title="-"
  view id=org.eclipse.ui.console.ConsoleView title="-"
  …
# 完整命令表也是只读：`python -m ctl commands --run-id w` → total=666 returned=666 truncated=False

# 3) 写 —— 不带 --yes 只打印
$ python -m ctl cmd org.eclipse.ui.views.showView viewId=com.gs.memory.view --run-id w
DRY-RUN cmd.runp org.eclipse.ui.views.showView viewId=com.gs.memory.view

$ 同上 + --yes          # 真发
OK
ICommandService via IWorkbench.getService -> true
IHandlerService -> true
parameter resolved by name: viewId -> org.eclipse.ui.views.showView.viewId
parameter org.eclipse.ui.views.showView.viewId=com.gs.memory.view
parameterizedCommand id=org.eclipse.ui.views.showView
executeCommand returned: null
OK executed org.eclipse.ui.views.showView

# 3b) ⚠️ 最要紧的一步：**回话撒谎**。同一个方法，换一个不存在的 viewId：
$ python -m ctl shell --run-id w -c "cmd.runp org.eclipse.ui.views.showView viewId=com.gs.liveview"
OK                                   ← 回话说成功了
…（上面那些 OK 行照旧）
parameter org.eclipse.ui.views.showView.viewId=com.gs.liveview
executeCommand returned: null        ← 框架也说成功了
OK executed org.eclipse.ui.views.showView
dialog=appeared "Problem Occurred"   ← ★ 桥自己抬头看到了这个框
dialog_note=the command may have FAILED, or the dialog may be the expected behaviour;
            close it and read back (ui.parts) before treating this call as done
END

# 回读一次就知道真相：views **8 → 8**（没变）。而「没变」既可能是幂等，也可能是失败 ——
# 光看回读差**分不出来**，必须叠加 dialog= 这层。这就是 protocol.md §4.3 的由来。

# 4) 卸 —— 一条命令 + 卸干净验收
$ python -m ctl uninstall --target gs32 --run-id w --verify-clean
stopped: pid 13772
residue removed: 1
  [clean] bundle_absent
  [clean] configuration_clean
  [clean] port_released
  [clean] no_process
```

**关键约定**：`0` = 成功；`1` = 失败（有明确结论）；**`2` = 前置未就绪（压根没跑）** —— CI 靠这个区分「机器没准备好」和「东西坏了」。

**三样一起看，缺一层就有洞**（`protocol.md` §4.3）：

| 层 | 看得见什么 | 看不见什么 |
|---|---|---|
| 协议错误码 | 参数写错、方法不存在、命令无 handler | 命令**执行中**抛的异常（异步，回话已经 OK 了） |
| `dialog=` / 窗口快照 | 异步弹框（含标题，可截图取证） | **不弹框**的失败（只写日志） |
| 回读差 | 静默失败 | **分不清「幂等」与「失败」**（`views 8→8` 两种都长这样） |

---

## 目录

```
bridge/src/ctl/bridge/LiveBridge.java   ← 桥源码（BSN: eclipse-ctl.bridge）
bridge/build.py                          ECJ 编译 + 打包
ctl/                                     客户端（CLI / 行协议 / 控制台驱动 / 实例纪律 / 用例）
tools/                                   窗口工具（枚举 / 关闭 / 按键 / 截图）
recipes/                                 可直接跑的配方
skill/SKILL.md                           给 agent 的用法说明
```

---

## 卸载与回滚

- **卸桥**：`python -m ctl uninstall --target <t> --verify-clean`（会连配置区里的常驻残留一起清）
- **回滚到上一个桥版本**：`python -m ctl upgrade --target <t> --from <旧 jar>`，或控制台里
  `uninstall <id>` → `install file:<旧 jar>` → `start <id>`
- **彻底清场**：删掉 `<run_root>/<run_id>/` 整个目录即可（源安装树零触碰，见 [`boundaries.md`](boundaries.md)）

---

## 文档

| 文件 | 内容 |
|---|---|
| [`protocol.md`](protocol.md) | 行协议、8 个错误码、超时语义、鉴权、端口发现、协议演进规则 |
| [`boundaries.md`](boundaries.md) | 方法级「能做 / 不能做 / 未验证」 |
| [`COMMANDS.md`](COMMANDS.md) / `commands.json` | 命令表自省产物（人读 / 机读，由 `ctl commands` 生成） |
| [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) | 症状 → 处置 |
| [`CHANGELOG.md`](CHANGELOG.md) | 版本变更 |
| [`SECURITY-REVIEW.md`](SECURITY-REVIEW.md) | 安全相关改动的人工复审记录 |
| [`recipes/`](recipes/) | 配方库 |

---

## 实现状态

> 逐阶段进度与验收证据在**项目任务仓**（Trellis 工作区）的 `research/` 下，**不在本仓**：
> `p0-gate.md` … `p3-gate.md`（各道门的闭环记录）、`hardening-r1-*.md`（硬化轮）、
> `popup-observation-matrix-*.md`（两条观测路径对小弹窗的实测矩阵）、`s4-acceptance-*.md`（影子截图验收）。
> **截至 2026-10-02，G0（立骨架与实例纪律）/ G1（只读面）/ G2（写面与错误契约）/
> G3（韧性）/ G3R1（硬化轮）/ G4（跨产品）均已通过**：
>
> - 桥：`LiveBridge.java` 由目标树 ECJ 编译打包成 OSGi bundle（BSN `eclipse-ctl.bridge`，v3.1.0），
>   16 个方法（12 只读 + 4 写），8 个错误码闭集
> - 客户端：**22 个子命令全部可用，全部支持 `--json`**，纯标准库；`ctl verify` 有
>   **24 条用例，两个 target 各自跑通**：**gs32 = 23 PASS + 1 SKIP / 0 FAIL**、
>   **ccs12 = 19 PASS + 5 SKIP / 0 FAIL**（6 条 SKIP 全为「声明式 skip」或「判据不适用」，
>   差异逐条见 [`boundaries.md`](boundaries.md) §A5）
> - **影子留档**（`ctl shadow` / `tools/win-probe.ps1`）：写动作后自动留帧；**帧不参与判据**。
>   实测（2026-10-01 真机）：`verify --all` 在影子开着时仍 **23 PASS + 1 SKIP / 0 FAIL**（两次覆盖
>   共 54 个样本，**控制台零命中**）；S4 桌面项 **13/13 PASS**
> - 未验证的项仍在 `boundaries.md` 里**逐条标注并给了验证入口**，请以那里为准。
>   **本文速查表描述的是已实测可用的一面，不是全部能力** —— 边界看 `boundaries.md`。
>
> 已知未修项（见任务仓的 `hardening-r1-*.md` §6）：`dialog=` 出现时进程退出码仍为 0；`TROUBLESHOOTING.md` §7
> 只覆盖约 7/45 条真实错误串；`ctl shell` 的错误不带 `; retry:`。
