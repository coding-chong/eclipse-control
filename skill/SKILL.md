---
name: eclipse-ctl
description: 从外部读取或控制 Eclipse 系 IDE（GS32_Studio / CCS 等）的桥通道。当需要看 IDE 界面/部件/命令、执行 IDE 命令、开文件、截图取证、或排查桥超时与模态框卡死时使用。关键词：eclipse-ctl、ctl、GS32_Studio、CCS、工作台、模态框、sys.ping、ui.parts。
---

# eclipse-ctl 用法（给 AI 会话）

**一句话**：向 Eclipse 进程热装一个薄桥，从外部**读界面 / 发命令**；写操作靠**回读差 + 弹框回报**判定，卡住时**自己截图看**。

## 0. 四条铁律

1. **`OK` ≠ 到位**。写方法一律「前快照 → 动作 → 后快照 → 取差」。
2. **`OK` 还会撒谎**：写方法的回话里若出现 `dialog=appeared "…"` 负载行，说明动作前后冒出了**新的可见窗口**
   —— 那条命令**可能失败了，也可能它本来就该弹框**。看到这一行就**别当成功**：先截图、关掉、再回读一次。
   （实测：`viewId` 写错时回话是 `OK executed`，屏幕上却是 `Problem Occurred`，而回读差 `views 8→8` 与
   「幂等成功」**长得一模一样** —— 只看回读差必然把失败读成成功。）
3. **`ERR timeout` ≠ 未生效**。超时后**必须再取一次回读差**（见 §3）。
4. **看不懂就自己截图**，不许把观察外包给用户。

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

## 3. 写操作：动作 + 回读差 + **看有没有 `dialog=`**

```bash
# 1) 前快照
python -m ctl parts --run-id <RUN_ID> --json > pre.json
# 2) 动作（写方法必须带 --yes；不带则只是 dry-run）
python -m ctl cmd --run-id <RUN_ID> org.eclipse.ui.views.showView viewId=com.gs.memory.view --yes
# 3) 后快照 + 取差：views 集合必须新增该 id
python -m ctl parts --run-id <RUN_ID> --json > post.json
```

**回话里必须扫一眼有没有 `dialog=` 行**（见 §0 第 2 条）。有就说明**多出了一个可见窗口**：

```
OK executed org.eclipse.ui.views.showView
dialog=appeared "Problem Occurred"          <- 先别当成功
dialog_note=… close it and read back (ui.parts) before treating this call as done
```

处置：截图 → `win-close.ps1` 关掉 → 再 `parts` 回读一次 → 才下结论。
**关窗要用 `-Class "#32770"` 或 `-TitleLike` 精确匹配**：`ui.open` 会把文件名写进**主窗标题**，
按模糊标题关窗可能把工作台关掉。

**`views 8→8` 这种「没变」是歧义的**——它既可能是**幂等成功**，也可能是**失败**。分辨手段只有两个：
回话里的 `dialog=` 行，以及「这条命令本来就该改什么」的先验。**别把「没变」直接读成成功。**

反例（练习时记住）：`cmd.runp showView viewId=com.gs.liveview` 返回 `OK executed`，
但**回读 views `8→8`** 且 **回话里有 `dialog=appeared "Problem Occurred"`**
—— `com.gs.liveview` 是**插件 id**，不是视图 id，Eclipse 异步抛了异常。

**幂等（决定能不能自动重试）**：看 `sys.help` 的 `idempotent` 列，三档：
`true` = 可重试；`false` = 不可；**`per-command`** = 一个方法名承载任意命令、**方法级无从保证**
（`cmd.run` / `cmd.runp` 就是这档，实测开关型命令连点两次会**回到原状**）⇒ 与 `unknown` **同等保守，一律不重试**。

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
5. **探活 —— 但「ping 得通」证明不了「界面没卡」**：

   ```bash
   python -m ctl shell --run-id <RUN_ID> -c "sys.ping"
   pwsh -NoProfile -File tools/win-enum.ps1 -Class "#32770"   # ← 这才是判断依据
   ```

   实测（2026-10-01）：模态框在屏上时，**另一条连接**的 `ui.parts` / `ui.tree` / `sys.ping`
   **全都正常返回** —— 因为 SWT 模态框跑的是**嵌套事件循环**，`asyncExec` 队列照常派发。
   只有**发起那次请求自己**会 `ERR timeout`。
   ⇒ **别拿「`ui.*` 通不通」判断界面卡没卡**，直接**枚举/截图看那个框在不在**（第 2 步）。
   ⇒ 反过来也要记住：**你发的那次请求超时了，不代表别的连接也干不了活**。
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

- **不要一次开一堆连接压桥**：全功能槽只有 **8** 个，而且**连着的空闲连接也算占槽**（每条要占满 60 s）。
  满员后只有 `sys.ping` / `sys.env` / `sys.help` 还能答，别的回 `ERR busy`（**可重试**，别当成故障）。
  **用完就关**，别把连接挂在那儿。
- **不要拿「`ui.*` 通不通」判断界面卡没卡**：模态框在屏时**别的连接照样通**（见 §4.5），
  要判断就**枚举/截图看那个框在不在**。
- 不要用坐标点击（该路线**未证实**，且**决定不投入**）；要动手柄一律**元素寻址**（按控件路径/文本）。
- 不要在 `--json` 场景里把 stderr 混进 stdout（诊断只走 stderr；stdout 只放结果）。
- 不要反复重试同一个 `ERR disabled` / `ERR unhandled` 的命令（那是 enablement / handler 问题，重试无用）。
  —— 但 `ERR busy` 不同：**它就该重试**（可能配合退避）。
- 不要用 `taskkill //F`（会被 shell 吃掉参数）；用 `pwsh -Command "Stop-Process -Id <pid> -Force"`。
  而且要**认准自己的 pid** —— 按映像名杀会连带杀掉别人的实例。

## 7. 收工

```bash
python -m ctl uninstall --target gs32 --run-id <RUN_ID> --verify-clean
```

`--verify-clean` 四项全过才算干净：`ss` 无该 bundle / 运行配置区无残留 / 端口已释放 / 无同源进程。
