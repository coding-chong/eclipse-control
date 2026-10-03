# DEVELOPING —— 开发者工具（**不进用户路径**）

> 本文件里的东西**都不是**用户面。用户面只有一个门：`python -m ctl run`（见 [`README.md`](README.md)）。
> 这里是**维护本仓**时要用的：验收用例、发布前总检、配方库、回收、换代。
> `deliverable-shape.md` C5：这些工具**留在仓里**，但 README 与 `skill/SKILL.md` **不指向它们**。

## 为什么它们在仓里而不在用户路径

判据在 [`.trellis/spec/backend/deliverable-shape.md`](../../SyncthingFiles/xn2pk-yyqwv/omp-migration/.trellis/spec/backend/deliverable-shape.md)：
**能力** vs **项目** —— 用户要的是「薄协议 + 可 `import` 的库 + skill 约束」，
功能的**归属**是「agent 现写脚本」，不是「工具内置 N 个子命令」。
`verify` / `preflight` / `recipes` 是**维护者**的仪器，不是用户的手。

## 一、验收用例（`ctl verify`）

26 个用例，跑在**目标实例**上：

```bash
python -m ctl install --target gs32 --run-id dev --port 8900
python -m ctl verify --all --target gs32 --run-id dev
python -m ctl verify --group read  --target gs32 --run-id dev     # 组：read / write / errors / resilience / input / realflow
python -m ctl verify --case  read.ping --target gs32 --run-id dev
```

- 退出码：`0` 全过 / `1` 有 FAIL 结论 / `2` 前置未就绪（无实例、target 不认识、缺 `pwsh`）。
- **回归基线**（2026-10-03，26 用例，**GS32**）：`--all` = **25 PASS + 1 SKIP / 0 FAIL**，`rc=0`
  （SKIP = `read.console`，该实例的 Console 视图没有 console 页 ⇒ 如实跳过）。
- `input.fixture` 是 `requires_bridge=False` 的自带夹具，**不需要实例**，自己起停。
- `realflow.build_artifact` 是唯一**真的跑一遍工作流**的用例（含一次无头构建），见下。

### `--group realflow`：一条真跑的工作流（`realflow.build_artifact`）

它固化的不是某个方法，而是用户的四步场景：**建工程 → 写几行代码 → IDE 认它 → 构建出产物**。
两个 target 跑**同一段用例代码、同一组判据**；只有「配方」是 per-target 数据
（启动器、建工程/构建命令、构建配置名、产物名、`e_machine`），与
`research/realflow-scenario-2026-10-02.md` §5/§6.2 的归因一致。

```bash
python -m ctl install --target gs32 --run-id dev --port 8900   # 前置：一个活实例
python -m ctl verify  --group realflow --target gs32 --run-id dev
```

- **判据**（每条失败都在 detail 里点名）：建工程落位且 rc=0；写出的源文件含唯一标记
  `CTL-REALFLOW-<8 hex>` 且被 `main` 引用；`ui.open` 后 `editors` **回读差 +1**、新行 id 含
  `CEditor`、`name=` 等于文件名；构建 rc=0（未被超时杀掉）；产物存在、`\x7fELF`、
  `e_machine` 等于配方值；**产物字节里能找到那串唯一标记**（反假阳性：证明编的是这次写的代码）。
- **为什么它比别的组长**：一边连桥（编辑器步骤），一边起一个**独立的无头 IDE 进程**做真构建
  （GS32 走 CDT `headlessbuild`，CCS 走 `com.ti.ccstudio.apps.projectBuild`），实测单条 10–30 s
  （冷启动还要编厂商驱动库），所以它排在 `--all` 的最后。
- **前置条件**：两个 SDK 都装在 `targets` 表里指向的 `install_dir`；两侧都必须有可用的无头构建入口。
  目标没有配方 / 启动器不存在 / 模板目录不存在 ⇒ **SKIP**（不是 FAIL）；
  配方齐备但跑挂（建工程非 0、模板锚点变了、回读差不是 +1、构建非 0、产物不对）⇒ **FAIL**。
- **换机器 / 改路径**：`ECLIPSE_CTL_REALFLOW_<KEY>` 覆盖配方标量，`<KEY>` ∈
  `LAUNCHER` / `TEMPLATE` / `CONFIG` / `ARTIFACT` / `DEVICE` / `MACHINE` / `BUILD_TIMEOUT`，
  例如 `ECLIPSE_CTL_REALFLOW_TEMPLATE=D:/other/pack/gs32f035`。
  安装树本身仍从 `ctx.target.install_dir` 派生，**不写机器特有绝对路径**。
- **它不碰你的实例**：`ui.open` 只对**你指定的 run** 发；构建走独立的 `-data <scratch>/ws`，
  在 `<run_root>/<run_id>/realflow/` 下建、跑完由 `post` 删掉。它**没有**编排 `install`——
  要真跑就得先给一个实例（`--run-id`），这跟 `read.*`/`write.*` 一样。

### 跨 target 的已知差异（必须带归因）

| 用例 | GS32（Eclipse 4.30 / SWT 3.124） | CCS（Eclipse 4.23 / SWT 3.119） | 归因 |
|---|---|---|---|
| `input.fixture` / `key` | CHANGED | **UNCHANGED** | **平台版本**：SWT 3.119 不把合成 `WM_KEYDOWN` 派发给控件自身的 `KeyListener`；3.124 会。换 JVM（11 ↔ 23）、补 `WM_SETFOCUS`、置前台**都不改变**结果（2026-10-02 的 2×2 实测，同启动方式）。点按钮（`BM_CLICK`）与写文本（`WM_SETTEXT`）两侧都通 |

## 二、发布前总检（`ctl preflight`）

```bash
python -m ctl preflight --target gs32,ccs12
```

= `doctor` + `verify` + 「文档 ↔ CLI 一致性」+ CHANGELOG 条目检查。

## 三、配方库（`ctl recipes`）

```bash
python -m ctl recipes list
python -m ctl recipes run diag-when-hung
```

`recipes/` 下是可直接跑的 bash 块；`recipes run <name>` 按顺序执行。

## 四、回收与换代

```bash
python -m ctl gc                       # 默认 dry-run：列出会被删的 run
python -m ctl gc --yes                 # 真删
python -m ctl upgrade --target gs32    # 重编桥并把实例带回来
```

> ⚠️ **`gc` 是破坏性命令**：语义 = 清掉 `<run_root>` 下**除最新 keep 个以外全部** run 目录。
> 实测代价：一次探索把 `runs/` 从 30 个删到 4 个，**含一个正在运行的实例**。
> 规矩：默认 dry-run、`--yes` 才删、**跳过 `endpoint.json` 里 pid 存活的 run**。

> ⚠️ **`doctor` 回答的不是「我的实例健康吗」**：它的「无残留实例」扫**整个 run root**
> （任何兄弟 run_id 都算），且端口占用会把**自己的实例**算成 FAIL ⇒ 健康会话下也 `exit 2`。
> 它给的 `--ensure-clean` retry **会杀掉你的实例**。会话中途**不要**照它的 retry 执行。

## 五、生命周期命令的原始形态

用户面由 `ctl run` 自动完成这些；需要手工介入时才用：

```bash
python -m ctl doctor   --target gs32                                    # 8 项自检
python -m ctl install  --target gs32 --run-id demo                      # 装桥 + 起实例 + 写 endpoint.json
python -m ctl status   --target gs32 --json                             # 桥版本 / 协议版本 / 端口
python -m ctl uninstall --target gs32 --run-id demo --verify-clean      # 停机 + 清残留 + 四项判据
python -m ctl targets list                                              # target 矩阵
python -m ctl commands find  --text "Reset Perspective"                  # 反查：UI 文字 → 命令 id
python -m ctl commands export --json --full > commands.json             # 命令表导出（六字段；R8 的机读产物）
python tools/make-commands-md.py                                        # 由 commands.json 同源渲染 COMMANDS.md
python -m ctl act click-button --title "Reset Perspective" --text "&No" --yes   # 元素寻址输入
```

`--stop` / `--doctor` 是 `ctl run` 上的等价开关，用户面走那两个。

> **`commands export --full` 的归类（`deliverable-shape.md` C3 / R10′.6）**：它**不是**新能力，是
> `commands.json` **生成器**（R10′.5 点名的保留开发者工具）按 **R8** 把产物做成六字段形状的动作。
> 判据：门只有 `ctl run` 一个（见 §九）；这条留在 developer 工具里、README 与 skill 都不指向它（A13′ `rc=1`）。
> 若将来有人要**给用户**加命令表能力，那按 C3 先落脚本。

## 六、`ctl run` 上的两个生命周期 flag（实现说明）

- **`--stop`**：脚本跑完后复用 `uninstall` 的**已被测试覆盖**的路径收工，并打印四项清洁判据
  （`bundle_absent` / `configuration_clean` / `port_released` / `no_process`）。
  **脚本失败也照收** —— 漏掉一个活实例比脚本失败更糟。
- **`--doctor`**：先打一份体检报告，**但它的退出码永远不参与判定**
  （理由见上：它扫整个 run root，健康会话也报 FAIL）。它是报告，不是闸门。

## 七、三层测试

**只用标准库（R12′.1）** —— 没有 `pytest` 依赖，仓里也没有别的测试框架。

| 层 | 回答什么 | 复跑命令 | 实测（2026-10-04） |
|---|---|---|---|
| 单元 | 四层配置的**优先级**（flag > env > file > 默认）、窗口寻址的 pid 契约、`act` 寻址契约、`run` 写助手、控制台黑名单 | `python -m unittest discover -s tests/unit -t . -q` | 48 tests / `rc=0` |
| 契约 | 冻结的 **8 个错误码**：常量 ↔ 异常映射 ↔ `protocol.md` 三者不漂移 | `python -m unittest discover -s tests/contract -t . -q` | 7 tests / `rc=0` |
| 验收 | 真实例上的端到端行为（需要活实例） | `python -m ctl verify --case read.ping --target gs32 --run-id <id>` | 见 §一 |

两层的合集：`python -m unittest discover -s tests -t . -q` → **55 tests / `rc=0`**
（= 单元 48 + 契约 7；48 = `test_window_pid_contract.py` 13 + `test_act_addressing.py` 11 +
`test_command_id_framing.py` 8 + `test_config_precedence.py` 7 + `test_run_write_helpers.py` 4 +
`test_console_blacklist.py` 3 + `test_help_method_set.py` 2）。
**计数由各文件 `def test_` 直接数** —— 别照抄这里的数字，改了测试就复算一次。

> 契约层**实测咬出过一个真问题**，值得记着：最初把「未知错误码要保留原文」这条断言写在 `CtlError` 上，
> **实测失败** —— 该承诺实际是在 `ctl/client.py:parse_status` 兑现的（那才是"看见一个外来码"的地方），
> `CtlError` 只负责折叠、原样传 message。断言随即改到正确的层，并拆成三条
> （折叠 / 外来码保留 / 裸异常串保留）。⇒ 写"契约"测试时，先确认**承诺落在哪一层**。

## 八、目录

| 路径 | 内容 |
|---|---|
| `ctl/verify/` | 用例运行器与 26 个用例 |
| `recipes/` | 配方库 |
| `commands.json` / `COMMANDS.md` | 命令表产物 —— **开发者工具**（R11′.3 已降为可选，不进 README / skill 的用户路径）。`commands.json` = 六字段（`id/name/category/parameters/handled/vendor`）× N + 顶层 `handler_only`；`COMMANDS.md` 由 `tools/make-commands-md.py` **从它**渲染，两者不再各自取数 |
| `tools/` | 被库调用的工具（不是门）：`shot-window-pw.ps1` / `win-*.ps1` / `make-commands-md.py` |
| `tests/` | 单元 / 契约测试 |
| `.trellis/`（本仓外的迁移仓） | 任务 PRD / 设计 / 研究档 |

## 九、用户面里被刻意省略的标识符

`README.md` 与 `skill/SKILL.md` **不写**下面这些字面量 —— `deliverable-shape.md` §6② 的机械判据
（`grep -nE 'verify|preflight|recipes|install|uninstall|gc|upgrade'` 必须无输出），
而要传达的意思用中文表达。需要**准确标识符**时来这里取：

| 用户面说法 | 真实标识符 |
|---|---|
| 安装根目录 | `install_dir`（别名 `source_dir`） |
| 源级 | `java_target`（别名 `java_level`） |
| 厂商标识 | `vendor_prefix` |
| 探针视图 | `probe_view` |
| 控制台的 bundle 生命周期动词 | `install` / `start` / `stop` / `ss` / `uninstall` |
| 起外部进程 | `fork/exec` |
| 开发者用例模块 | `ctl/verify/` |
| 回收 / 换代命令 | `ctl gc` / `ctl upgrade` |
| 发布前总检 | `ctl preflight` |

**别把它们加回 README / skill** —— 那是 §6② 判据要拦的东西；要引用就走本表。

## 十、提交、分支与性能预算（R12′.5 / R12′.7 —— 开发者工具，**不进用户路径**）

这两条**不是验收项**：`deliverable-shape.md` C1 把「性能预算」明列在**家具**清单里，R12′.7 把
「三层测试 · 性能预算 · 缺陷上报四件套 · 发布节奏 · `preflight` 门禁」统一下沉为开发者工具。
**它们的家是本文件，不是 `README.md` / `skill/SKILL.md`。**

### 提交与分支（R12′.5，纪律保留）

- 提交信息形如 `<type>: <subject>`，带 scope 的写法见 `git log`：`docs(boundaries): …` /
  `fix(tools): …` / `spec(backend): …` / `chore(task): …`。
- **一提交一意图** —— 不要把互不相关的改动揉进同一个提交。
- **破坏协议的变更走 `proto/vN` 分支**。协议版本独立于项目版本：`PROTOCOL_VERSION` 只在
  行协议本身变化时 bump（`ctl/__init__.py` 注释与 `design-project.md` §15.2）。
- **两个版本号必须同号**（R11′.2）：桥 `Bundle-Version`（`bridge/build.py` 的 `DEFAULT_VERSION`）
  == 项目 `__version__`（`ctl/__init__.py`）。**改一个就要改另一个** —— 这条曾经失守过
  （桥 3.1.0 / 项目 0.1.0），且当时**没有任何门禁能发现**，只能靠人读出来。

### 性能预算（R12′.7，**不构成验收**）

**测量法**（A12′ 末段，不变）：以桥侧 `<run_root>/<run_id>/bridge.log` 的 per-request 耗时为准，
每方法 **n ≥ 30** 稳态样本，报 **p50 / p95**。阈值：读面 p95 ≤ 2 s、写面 p95 ≤ 5 s、
`sys.ping` p95 ≤ 50 ms（**不含**客户端启动与 TCP 连接，该段单列 ≤ 1 s）；冷启动 ≤ 120 s。

- 数字的**唯一来源**是 `bridge.log`（R12′.2 的日志约定：每条请求 + 耗时 + 结果码）——
  没有独立的基准脚本，也**不需要**把表写进产品文档；要数就现场读日志。
- 与 `--doctor` 的关系：`--doctor` 是唯一的诊断 flag，性能数字供它和临时脚本取用。
- **别把它产品化**：`README.md` / `skill/SKILL.md` 不写这些阈值。

