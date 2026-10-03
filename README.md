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

## 五分钟上手

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

## 配置文件

`~/.eclipse-ctl/config.json`（可用 `--config` 换）。**优先级：flag > 环境变量 > 文件 > 内置默认。**

| 键 | 作用 |
|---|---|
| `targets` | 每台 IDE 的事实：安装根 / JRE 级别 / 源级 / 启动器 / 厂商标识 / 探针视图（**准确字段名与别名见 [`DEVELOPING.md`](DEVELOPING.md) §九**） |
| `run_root` | 运行目录根（默认 `~/.eclipse-ctl/runs`） |
| `keep_runs` | 保留最近几次 run（超出可**回收**） |
| `token` | 可选；启用后握手带 token |

> `java_target` 决定 `-source/-target`：它必须**≤ 目标 JRE 的级别**，否则编出来的 class 在那台 JRE 上装载不了。

## 目录

| 路径 | 内容 |
|---|---|
| [`ctl/`](ctl/) | Python 库与 CLI（**只用标准库**）：`client` / `console` / `lifecycle` / `run` / `targets` / `shadow` / `screen` |
| [`bridge/`](bridge/) | 桥 bundle 源码与构建产物 |
| [`tools/`](tools/) | PowerShell 观测/输入装置（枚举窗、截图、关窗、点按钮） |
| [`skill/`](skill/) | 约束层（给 AI 会话） |
| [`protocol.md`](protocol.md) | 行协议（请求/响应形状、错误码闭集、超时语义） |
| [`boundaries.md`](boundaries.md) | 能做 / 不能做 / 未验证，**方法级** |
| [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) | 症状 → 处置 |
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
