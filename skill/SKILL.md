---
name: eclipse-ctl
description: 从外部读取或控制 Eclipse 系 IDE（GS32_Studio / CCS 等）的桥通道。当需要看 IDE 界面/部件/命令、执行 IDE 命令、开文件、截图取证、或排查桥超时与模态框卡死时使用。关键词：eclipse-ctl、ctl、GS32_Studio、CCS、工作台、模态框、sys.ping、ui.parts。
---

# eclipse-ctl 用法（给 AI 会话）

**一句话**：向 Eclipse 进程热装一个薄桥，从外部**读界面 / 发命令**；写操作靠**回读差**判定，卡住时**自己截图看**。

## 0. 三条铁律

1. **`OK` ≠ 到位**。写方法一律「前快照 → 动作 → 后快照 → 取差」。
2. **`ERR timeout` ≠ 未生效**。超时后**必须再取一次回读差**（见 §3）。
3. **看不懂就自己截图**，不许把观察外包给用户。

## 1. 先发现端口、再说话

端口是「从 `8777` 起取首个空闲」，**不要假设 8777**。真实端口写在
`<run_root>/<run_id>/endpoint.json`（字段：`port` / `token?` / `pid` / `configuration` / `started_at`）。

```bash
python -m ctl doctor --target gs32                 # 前置就绪？（0 全绿 / 2 未就绪）
python -m ctl status --target gs32 --json          # 桥版本 / 协议版本 / 端口 / 工作台状态
python -m ctl shell --run-id <RUN_ID> -c "sys.env" # bundle / protocol / port / thread
```

`sys.env` 必须报 `protocol=1`，且 `bundle=` 的值是 `eclipse-ctl.bridge`；不符就**先别发写方法**。

## 2. 读一个部件 / 一条命令

```bash
python -m ctl parts  --run-id <RUN_ID> --json                  # 透视图 + views + editors
python -m ctl tree   --run-id <RUN_ID> 7                       # SWT 控件树，深度是位置参数（缺省 3）
python -m ctl viewids --run-id <RUN_ID> com.gs                 # 注册视图，前缀是位置参数（空前缀=全部）
python -m ctl cmd    --run-id <RUN_ID> org.eclipse.ui.views.showView viewId=com.gs.memory.view --yes
python -m ctl commands --json                                  # 全部命令（含 handlerOnly 块）
python -m ctl commands find --text "Reset Perspective" --json   # 按 UI 文字反查命令 id
python -m ctl shell  --run-id <RUN_ID> -c "ui.console --tail 50"  # 活动 Console 尾部（无独立子命令）
```

> `ctl cmd` 有参数时走桥的 `cmd.runp`、无参数时走 `cmd.run`——你不用记这个，CLI 会选。

- **参数别硬编码**：先 `cmd.query <id>` 取 `parameters[]`，再拼 `cmd.runp`。
- `ui.tree` 里 `ToolItem` / `MenuItem` / `CTabItem` **不是 `Control`**，走 `getItems()`；按钮语义在 `getToolTipText()`。
- `ui.console` **只读活动 Console**；要读另一个先激活它。

## 3. 写操作：动作 + 回读差

```bash
# 1) 前快照
python -m ctl parts --run-id <RUN_ID> --json > pre.json
# 2) 动作（写方法必须带 --yes；不带则只是 dry-run）
python -m ctl cmd --run-id <RUN_ID> org.eclipse.ui.views.showView viewId=com.gs.memory.view --yes
# 3) 后快照 + 取差：views 集合必须新增该 id
python -m ctl parts --run-id <RUN_ID> --json > post.json
```

反例（练习时记住）：`cmd.runp showView viewId=com.gs.liveview` 返回 `OK executed`，但回读 views `8→8` ——
`com.gs.liveview` 是**插件 id**，不是视图 id。

**幂等**：只有 `sys.help` 里标 `idempotent=true` 的方法才允许自动重试；标 `unknown` 的一律**不重试**
（自动重试可能把「已生效」再执行一次）。

## 4. 超时后怎么办（必读）

1. **不要**认定「没执行」。桥用 `asyncExec`，超时只结束**等待**，排队的动作仍可能生效。
2. **先截图看清那个框**（不要先猜、不要问用户）：

   ```bash
   pwsh -NoProfile -File tools/shot-window-pw.ps1 -TitleLike "GS32_Studio" -Out "<RUN_ROOT>/<RUN_ID>/shots/hung.png"
   ```
3. **从图上读出标题与按钮文字**，再枚举子窗拿按钮列表：

   ```bash
   pwsh -NoProfile -File tools/win-enum.ps1 -TitleLike ""
   pwsh -NoProfile -File tools/win-click-button.ps1 -TitleLike "Reset Perspective" -ListOnly
   ```
4. **处置**：默认只关窗（等同点右上角 X）：

   ```bash
   pwsh -NoProfile -File tools/win-close.ps1 -TitleLike "Reset Perspective"
   ```
   只有用例**显式声明**了按钮时才按下它（点按钮 = 替用户做不可逆决定）：

   ```bash
   pwsh -NoProfile -File tools/win-click-button.ps1 -TitleLike "Reset Perspective" -Text "&No"
   ```
5. **探活**（卡死期间 `sys.ping` 不通、能通即「可运维」）：

   ```bash
   python -m ctl shell --run-id <RUN_ID> -c "sys.ping"
   ```
6. **再取一次回读差**，把差值归因到先前那次超时请求（这一步不能省）。

**完整自救配方**：`python -m ctl recipes run diag-when-hung`。

## 5. 出错时怎么自己看

```bash
python -m ctl doctor --target gs32       # 环境指纹（缺陷四件套的第 1 件）
python -m ctl status --target gs32 --json
python -m ctl recipes run diag-when-hung
```

CLI 的每条错误串都带 `; retry: <一条可复跑命令>`，把它贴进 `TROUBLESHOOTING.md` 能 grep 到同一行。
报缺陷要四件套：**环境指纹 + 原始回话片段 + 截图 + 复跑命令**。

## 6. 别做的事

- 不要用坐标点击（该路线**未证实**，且**决定不投入**）；要动手柄一律**元素寻址**（按控件路径/文本）。
- 不要在 `--json` 场景里把 stderr 混进 stdout（诊断只走 stderr；stdout 只放结果）。
- 不要反复重试同一个 `ERR disabled` / `ERR unhandled` 的命令（那是 enablement / handler 问题，重试无用）。
- 不要用 `taskkill //F`（会被 shell 吃掉参数）；用 `pwsh -Command "Stop-Process -Id <pid> -Force"`。

## 7. 收工

```bash
python -m ctl uninstall --target gs32 --run-id <RUN_ID> --verify-clean
```

`--verify-clean` 四项全过才算干净：`ss` 无该 bundle / 运行配置区无残留 / 端口已释放 / 无同源进程。
