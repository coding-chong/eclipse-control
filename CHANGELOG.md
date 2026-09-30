# Changelog

本文件格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
**版本策略**：项目版本 **=** 桥 `Bundle-Version`（同号）；**协议版本** `PROTOCOL_VERSION` 独立编号，
仅在行协议变更时改动（`design-project.md` §15.2、`protocol.md` §9）。

当前 `PROTOCOL_VERSION = 1`。

## [Unreleased]

暂无条目。本版（0.1.0）之后的所有变更在落地时记入本节。

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
  （`port` / `token?` / `pid` / `configuration` / `started_at`）。
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
