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
| 跑门禁用例 | `python -m ctl verify --case read.ping --target gs32` |
| 跑全部门禁 | `python -m ctl verify --all --target gs32` |
| 卸桥并自检干净 | `python -m ctl uninstall --target gs32 --verify-clean` |
| 编译打包桥 | `python -m ctl build --target gs32` |
| 发布前总检 | `python -m ctl preflight --target gs32,ccs12` |

**退出码三态**：`0` 成功　`1` 失败（有明确 FAIL 结论，含用法错误）　`2` **前置未就绪**（环境没准备好，压根没开跑）。
**写操作要加 `--yes`**（缺省只打印将要发送的请求，不建连接）。

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

> **本文档描述目标形态。** 逐阶段进度以 [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) 之外的
> 任务记录为准；本仓当前处于 **P0（立骨架与实例纪律）**：
>
> - 桥：`LiveBridge.java` 已能从目标树 ECJ 编译打包（BSN `eclipse-ctl.bridge`）
> - 客户端：骨架已落，命令面在补
> - 尚未经真机验证的项在 `boundaries.md` 里**逐条标了「未验证」并给了验证入口** —— 请以那里为准，
>   不要拿本文的速查表当「已通过」的证据。
