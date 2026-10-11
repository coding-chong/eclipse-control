# eclipse-ctl

**从外部读取或控制 Eclipse 系 IDE 的薄通道。** 往目标 IDE 进程里热接一个桥 bundle，
用「一行一条」的行协议读界面 / 发命令 / 合成输入。Python 侧是一个**可 `import` 的库**，
外面套**一个门**：`python -m ctl run`。

实测过两代产品：**GS32_Studio v1.2.5.2**（Eclipse 4.30.0 + CDT 11.5.0 + JRE 23.0.2）
与 **CCS 12.8.1**（Eclipse 4.23.0 + JRE 11.0.13）。GS32 与 CCS 都是 **target**，不是绑定对象。

## 形状：能力，不是项目

| 件 | 是什么 |
|---|---|
| **一个门** | `python -m ctl run` —— 脚本进 stdin；**连不上就自己起实例**；`--stop` 收干净 |
| **库** | `import ctl` → `Client` / `talk` / `resp` / `snap` / `discover_endpoint` |
| **约束** | [`skill/SKILL.md`](skill/SKILL.md) —— 何时用 / 怎么写脚本 / 超时后怎么办 / 不许做什么 |
| **协议** | [`protocol.md`](protocol.md) —— 16 方法（12 读 + 4 写），一行一条；`sys.help` 可自省 |

功能由 **agent 现写脚本**，不内置成一堆子命令。新能力先落脚本；确有复用价值才提升为**库函数**。

## 速查表

| 想做的事 | 怎么做 |
|---|---|
| 起实例并读一眼 | `echo 'print(parts().perspective)' \| python -m ctl run --target gs32` |
| 连不上时重试 | 加 `--retry 30`（指数退避） |
| 先看一份就绪体检 | 加 `--doctor`（**仅供参考**，见下） |
| 载入任务专属辅助 | `--helpers mylib.py`（先 `exec` 它，再跑 stdin 脚本） |
| 只用已经活着的实例 | `--no-start`（没有就 `exit 2`，不替你起） |
| 收工 | 加 `--stop`（逐项报清洁判据） |
| 关掉影子留档 | `--no-shadow`（留档默认开） |

> ⚠️ **写操作 `OK` ≠ 到位**：一律「前回读 → 动作 → 后回读 → 取差」。
> **`OK` 还会撒谎**：写方法的回话里若出现 `dialog=appeared "…"` 负载行，说明动作前后冒出了**新的可见窗**
> —— 那条命令**可能失败**。**冒没冒弹框只在回话的 `dialog=` 行里**；而回读差 `views 8→8` 与「幂等成功」
> 长得**一模一样**，光看回读差必然把失败读成成功。
>
> ⚠️ **`--doctor` 不是闸门**：它扫**整个运行根**，所以健康会话里也会报 FAIL 并 `exit 2`；
> 它建议的清理 retry 会**杀掉你正在用的实例**。它是体检报告，**它的退出码永远不参与判定**。

### 三条非直觉的事实（都实测过）

1. **`ERR timeout` ≠ 未生效** —— 桥用 `asyncExec`，超时只结束**等待**，排队的动作**仍可能生效**。
2. **模态框挂着时，别的连接照样通** —— 别拿「`ui.*` 通不通」判断界面卡没卡；要看就**自己截图**。
3. **真 IDE 主窗里没有输入目标** —— 实测主窗 `Button` = 0、`Edit` = 0；
   元素寻址的真实适用面是**对话框**。

## 三层边界（摘要）

| 层 | 通道 | 能做什么 | 不能做什么 |
|---|---|---|---|
| ① 控制台 | IDE stdin/stdout（Gogo） | bundle 的**装载 / 启停 / 查询**、`services`、`log`、起外部进程 | **不能反射调用任意 Java 方法** |
| ② 桥 bundle | 热注入的进程内 bundle | 读 SWT 对象树 / 部件 / 命令表；执行命令；开文件 | 只对**已创建的 UI** 工作；弹模态框会阻塞 |
| ③ 工具链 | 外部进程 | 编译、烧写、调试（各家自带 CLI） | 与 IDE 进程无关 |

**截图不单独成层** —— 它是贯穿三层的**观测装置**（`PrintWindow` 主通道 + 备用通道）。

## 前置条件

| 项 | 要求 | 为什么 |
|---|---|---|
| 平台 | **Windows**（本机实测 win32 10.0.26200 / x64） | 桥跑在目标 IDE 的 **SWT** 上；界面观测与输入走 `tools/*.ps1`（`PrintWindow`、`Get-PnpDevice`、窗口标题） |
| Python | **≥ 3.8**（本机实测 3.13.15） | 只用标准库（**硬约束**，CI 会拦非标准库 import）；闸门读 `ast.Constant`，该节点自 **3.8** 起才由解析器产出 |
| JDK | **不用单独装** | 桥用**目标树自带的** ECJ 与 JRE 编（`python -m ctl build`）；JDK 版本由 target 的 `java_target` 属性决定 |
| 目标 IDE | 一棵 Eclipse 家族安装树（GS32_Studio / CCS…） | 内置两个 target 的安装根是**参考机标定**，换机三步见 §换一台机器 |
| 板子 | **可选** | 板级用例无硬件即 `SKIP`；其余用例不需要板子 |

## 五分钟上手

> **先编桥**：`python -m ctl build --target gs32`。`bridge/dist/` 不入库，空克隆没编就撞
> `no bridge jar built yet`；换机 / 换 target 的完整三步见 §换一台机器。

```bash
# 1) 起实例 + 读一眼（连不上就自己起，隔离运行配置区，源安装树零触碰）
echo 'p = parts(); print(p.perspective, len(p.views))' | python -m ctl run --target gs32

# 2) 只读面**默认真发**，不需要任何开关
echo 'print(sys.ping)' | python -m ctl run --target gs32     # 实际用 run("sys.ping")
```

写操作**默认 dry-run**，要真发必须在**库函数参数**上显式给 `yes=True`：

```python
# job.py
pre = set(parts().views)
print(cmd("org.eclipse.ui.views.showView", yes=True,
          viewId="com.gs.memory.view"))          # 真发
post = set(parts().views)
print("added:", post - pre)                      # ← 判据在这：回读差

# ⚠️ 同时必须扫一眼回话里有没有 `dialog=` 行（写了才可能撒谎）
```

```bash
python -m ctl run --target gs32 < job.py
```

**为什么非要回读差**：同一个方法换一个不存在的视图 id，回话照样是 `OK executed`，
屏幕上却是 `Problem Occurred` —— 而回读 `views 8→8` 与「幂等成功」长得一样。
**这说明判定必须叠三层**：协议错误码 + 弹框回报 + 回读差。出处 `protocol.md` §4.3。

收工：

```bash
echo 'print("done")' | python -m ctl run --target gs32 --run-id <id> --stop
```

## 换一台机器：clone 即用

项目按**仓根直接跑**的形态分发，不装包。`import ctl` 依赖仓内布局——`tools/*.ps1` 与
`bridge/dist/*.jar` 都在仓根下、不在 `ctl` 包里——所以入口就是仓根：

```bash
git clone <仓库地址> eclipse-ctl
cd eclipse-ctl

python -m ctl --help                                    # -m 把当前目录放进 sys.path，门就在这
echo 'p = parts(); print(p.perspective)' | python -m ctl run --target gs32
```

用库时同理：在仓根跑，或把仓根挂上 `PYTHONPATH`：

```bash
cd eclipse-ctl && python my_job.py                      # 在仓根跑
PYTHONPATH=D:/path/to/eclipse-ctl python my_job.py       # 从别的目录跑
```

### 第一步：把内置 target 的安装根换成你的路径

内置矩阵里 `gs32` / `ccs12` 各带一个 `install_dir`，值是**参考机**的路径。换机器后第一次
起实例会停在这一条上，并给出可复跑的设置命令：

```
ERR notfound target 'gs32' install_dir does not exist: D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2; it is the reference machine's value -- set yours with: python -m ctl targets add gs32 --source-dir <the directory that contains GS32.exe>
```

把 `--source-dir` 换成你机器上的安装根，两个 target 各设一次：

```bash
python -m ctl targets add gs32  --source-dir <你的 GS32_Studio 安装根>
python -m ctl targets add ccs12 --source-dir <你的 ccs/eclipse 目录>
python -m ctl targets list      # INSTALL_DIR 列应是你的路径
```

覆盖写进 `~/.eclipse-ctl/config.json`（`--config` 可换文件）。JRE 级别 / 端口 / 启动器沿用内置值；
产品版本换了再一起给：

```bash
python -m ctl targets add gs32 --source-dir <安装根> --java-level 17 --launcher GS32.exe
```

### 第二步：编一次桥

新克隆里没有桥 jar（`bridge/dist/` 不入库）。在仓根编一次，两个 target 各一份：

```bash
python -m ctl build --target gs32
python -m ctl build --target ccs12
```

产物落在 `bridge/dist/eclipse-ctl.bridge_<版本>_<target>.jar`；`run` 按 target 自动选对应那份。

### 起不来时看什么

- `python -m ctl doctor --target gs32` —— 逐项体检：安装根在不在、桥 jar 的字节码级别对不对、端口通不通。
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) —— **维护者页**（症状 → 处置：恢复要动维修仪器，故不算用户面）；含 `no bridge jar built yet`、`launcher not found` 两条。

## 配置文件

`~/.eclipse-ctl/config.json`（可用 `--config` 换）。**优先级：flag > 环境变量 > 文件 > 内置默认。**

| 键 | 作用 |
|---|---|
| `targets` | 每台 IDE 的事实：安装根 / JRE 级别 / 源级 / 启动器 / 厂商标识 / 探针视图（**准确字段名与别名见 [`DEVELOPING.md`](DEVELOPING.md) §九**） |
| `run_root` | 运行目录根（默认 `~/.eclipse-ctl/runs`） |
| `keep_runs` | 保留最近几次 run（超出可**回收**） |

> `java_target` 决定 `-source/-target`：它必须**≤ 目标 JRE 的级别**，否则编出来的 class 在那台 JRE 上装载不了；
> 同时必须**≤ 该目标能拿到的编译器**的上限 —— ccs12 的编译器来自它自带的 XDCtools 组件（ECJ 3.14，
> 上限 Java 9），所以它的 `java_target` 是 **8**。它是 target 的**属性**，不由"发现了哪个编译器"推导。

## target 清单（内置两个）

内置矩阵是 `ctl/targets.py` 的 `_BUILTIN`（`ctl/targets.py:234-277`）。两个 target 的
**平台版本 / JRE / 厂商标识 / 端口 / 安装根**逐项如下（**同一份脚本、同一套方法面**，差异只在值上）：

| target | 平台版本 | JRE（`java_target`） | 厂商标识 | 端口 | 启动器 | 产品 id |
|---|---|---|---|---|---|---|
| `gs32` | Eclipse 4.30.0 | 23.0.2（17） | `com.gs` | **8777** | `GS32.exe` | `com.gs.ui.Studio` |
| `ccs12` | Eclipse 4.23.0 | 11.0.13（8） | `com.ti` | **8778** | `ccstudio.exe` | `org.eclipse.platform.ide` |

| target | 安装根（**参考机取值**，可覆盖） |
|---|---|
| `gs32` | `D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2` |
| `ccs12` | `D:/ti/ccs1281/ccs/eclipse` |

> ⚠️ **这两个值不是产品常量，是「参考机」的实测值** —— 内置矩阵那一层（第 4 层）的默认。
> 解析顺序固定为 **CLI 旗标 > 环境 `ECLIPSE_CTL_*` > `~/.eclipse-ctl/config.json` > 内置默认**；
> **换一台机器不要改源码**，跑一条命令即可（`python -m ctl doctor` 会打印同样的提示）：
>
> ```bash
> python -m ctl targets add ccs12 --source-dir <你的 .../ccs/eclipse>
> ```
>
> 内置值在本机不存在时，`launch` **直接给出上面这条命令**：`lifecycle.py` 的 `_install_dir_missing`
> 把「你没设过」与「你设错了」分开报（`reference_install_dir()` 就是为此存在的）。

实测对拍（`python -m ctl targets list`，rc=0；**下述 `INSTALL_DIR` 列是参考机上的原样输出**，换机后该列即不同）：

```
NAME     ECLIPSE    JRE    JAVA   PRODUCT                  PORT   INSTALL_DIR
ccs12    4.23.0     11.0.13 8      org.eclipse.platform.ide 8778   D:/ti/ccs1281/ccs/eclipse
gs32     4.30.0     23.0.2 17     com.gs.ui.Studio         8777   D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2
```

三条非直觉的差异（都有出处，逐条可 `grep`）：

- **端口是每个 target 的固定值，不是「从 8777 起取首个空闲」**：`gs32` = 8777、`ccs12` = 8778
  （`ctl/targets.py:241` / `ctl/targets.py:263`）。端口被占**即拒**，不会自动漂到别处（`protocol.md` §6）。
- **探针视图按 vendor 命名，后缀拼接不通用**：`gs32` = `com.gs.memory.view`（`ctl/targets.py:246`），
  `ccs12` = `com.ti.ccstudio.project.ui.views.MemoryAllocationView`（`ctl/targets.py:275`）——
  `com.ti` 下**没有** `.memory.view`。
- **`ccs12` 那棵树里没有 JDT 批编译器**，它的编译器由 `_find_ecj` 在**同产品**的 XDCtools 组件里找到
  （`ctl/targets.py:174-181` 的两条搜索面：树内 `plugins/`，再向上两层
  `xdctools_*/packages/xdc/shelf/java/ecj.jar`）——**不再从 gs32 树外借**；
  `--doctor` 会把「两处都没有」这一条报成 FAIL，并在编译器不认 `java_target` 时给出改写。

加自定义 target 用 `python -m ctl targets add`；字段名与别名见 [`DEVELOPING.md`](DEVELOPING.md) §九。

## 目录

| 路径 | 内容 |
|---|---|
| [`ctl/`](ctl/) | Python 库与 CLI（**只用标准库**）：`client` / `console` / `lifecycle` / `run` / `targets` / `shadow` / `screen` |
| [`bridge/`](bridge/) | 桥 bundle 源码与构建产物 |
| [`tools/`](tools/) | PowerShell 观测/输入装置（枚举窗、截图、关窗、点按钮） |
| [`skill/`](skill/) | 约束层（给 AI 会话） |
| [`protocol.md`](protocol.md) | 行协议（请求/响应形状、错误码闭集、超时语义） |
| [`boundaries.md`](boundaries.md) | 能做 / 不能做 / 未验证，**方法级** |
| [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) | **维护者页**：症状 → 处置 |
| [`DEVELOPING.md`](DEVELOPING.md) | **开发者工具**（不进用户路径）：验收用例、发布前总检、配方库、回收、换代 |

## 卸载与回滚

`--stop` 会停机、清掉该 run 在运行配置区里的残留，并逐项报告清洁判据
（`bundle_absent` / `configuration_clean` / `port_released` / `no_process`）。
回滚到上一个桥版本、以及「源安装树零触碰」的取证方式，见 [`DEVELOPING.md`](DEVELOPING.md)。

## 边界与状态

- **能做 / 不能做 / 未验证**逐条在 [`boundaries.md`](boundaries.md)。三条措辞纪律：
  `未证实` / `已否决` / `决定不投入` **不得混用**。
- 已知平台差异（实测 2026-10-02，同一夹具、同一条消息）：`BM_CLICK`（点按钮）与 `WM_SETTEXT`（写文本）
  在 Eclipse 4.30 与 4.23 上**都通**；但 `WM_KEYDOWN`（按键）在 **4.30 / SWT 3.124 通**、
  在 **4.23 / SWT 3.119 不通**（换 JVM、补 `WM_SETFOCUS`、置前台都不改变）。
  ⇒ 按键原语**按平台核对**。
- 平台版本、JRE 模块数、命令服务 bundle 版本、厂商命令数等，见 `boundaries.md` 的兼容矩阵。
