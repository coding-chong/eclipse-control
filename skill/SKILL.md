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
**关窗必须给 `-TitleLike`**（它是必填参数），再配 `-Class "#32770"` 或 `-ProcId <pid>` 精确锁定。
**只给 `-Class` 会被工具直接拒绝**（实测 rc=1）。为什么要精确：`ui.open` 会把文件名写进**主窗标题**，
按模糊标题关窗可能把工作台关掉。
⚠️ 而 `win-close.ps1` 在**一个都没匹配到**时返回 **rc=0**（同族的 `win-click-button.ps1` 返回 1）
—— **不能只看退出码**，必须回读确认框真的没了。

**`views 8→8` 这种「没变」是歧义的**——它既可能是**幂等成功**，也可能是**失败**。分辨手段只有两个：
回话里的 `dialog=` 行，以及「这条命令本来就该改什么」的先验。**别把「没变」直接读成成功。**

反例（练习时记住）：`cmd.runp showView viewId=com.gs.liveview` 返回 `OK executed`，
但**回读 views `8→8`** 且 **回话里有 `dialog=appeared "Problem Occurred"`**
—— `com.gs.liveview` 是**插件 id**，不是视图 id，Eclipse 异步抛了异常。

**幂等（决定能不能自动重试）**：看 `sys.help` 的 `idempotent` 列，三档：
`true` = 可重试；`false` = 不可；**`per-command`** = 一个方法名承载任意命令、**方法级无从保证**
（`cmd.run` / `cmd.runp` 就是这档，实测开关型命令连点两次会**回到原状**）⇒ 与 `unknown` **同等保守，一律不重试**。

### 3bis. 影子留档：每次写动作**系统已经替你留了一帧**

**你不需要做任何事，也不需要去看它。** 每次写动作完成后，`ctl` 会自动在
`<run_root>/<run_id>/shadow/` 留一帧屏幕 + 一行清单（`manifest.jsonl`）。

**它是留档，不是判据。** 判断一个写动作成不成，仍然只靠这两条：**回读差** 与 **回话里的 `dialog=` 行**。
理由：`PrintWindow` 有「返回 TRUE 却画全黑」的真实失败模式 —— **一个会撒谎的通道不能当断言**。
⇒ **不要**因为"有图"就去读图、更不要拿图去论证成功/失败。

什么时候才去看它：

```bash
python -m ctl shadow --run-id <RUN_ID>            # 清单摘要（seq / 时间 / 方法 / 结果 / 是否 promote）
python -m ctl shadow --run-id <RUN_ID> --seq 7    # 第 7 个动作之后那一眼（--open 7 直接打开）
```

- 失败 / `ERR timeout` / 弹框触发的帧会被 **promote**（永不被环形裁剪清掉），优先看这些。
- 清单每行带 `target.class/hwnd/title/bounds` —— **先看 `target.class`**：它应该是
  `SWT_Window0`（工作台）或 `#32770`（原生对话框）。出现别的类名本身就是一条缺陷记录。
- 环形上限默认 20 帧 / 32 MB，`ctl shadow --prune` 手动裁。

留档会拖慢每个写动作约 0.3–0.4 s（拍一张 ~0.9 s，其中大部分是 pwsh 启动）。
不需要时用 `--no-shadow` 关掉；只在变化/异常时留用 `--shadow-only-changes`。

## 4. 超时后怎么办（必读）
1. **不要**认定「没执行」。桥用 `asyncExec`，超时只结束**等待**，排队的动作仍可能生效。
2. **先枚举，拿到那个框的真标题**（不要先猜、不要问用户）。**顺序不能反** —— 弹框标题不含
   `GS32_Studio`，而 `PrintWindow` 只渲染目标窗**自身**的位图、不会带上非子窗的模态框，
   所以拿主窗名去截会拍到一张**没有框的图**，正好把你推向"一切正常"：

   ```bash
   pwsh -NoProfile -File tools/win-enum.ps1 -Class "#32770"      # ← 先拿标题（#32770 = 对话框类）
   ```

3. **再按那个标题截图**（`-ProcId` 用来在多实例时认准自己的实例）：

   ```bash
   pwsh -NoProfile -File tools/shot-window-pw.ps1 -TitleLike "Problem Occurred" -ProcId <你的 pid> -Out "<RUN_ROOT>/<RUN_ID>/shots/hung.png"
   pwsh -NoProfile -File tools/win-click-button.ps1 -TitleLike "Problem Occurred" -ProcId <你的 pid> -ListOnly
   ```

   > ⚠️ 标题里可能有**看不见的字符**（实测 Edge 的标题含一个 `\u200b` 零宽空格，`"Microsoft Edge"`
   > 匹配不上）。匹配不上时改用更短的片段。
   > **拍 GS32_Studio 主窗时会撞到"标题撞车"**：启动器控制台也是一扇可见顶层窗，标题是
   > `D:\ProgramFiles\...\GS32_Studio_v1.2.5.2\GS32.exe`（**含 `GS32_Studio`**），且**同 pid**
   > —— `-ProcId` 分不开它。实测旧版会静默拍到那扇 800×500 的黑控制台并报 `ok=True`。
   > 现在工具**自动选面积最大的那扇**，并在输出里列出全部候选
   > （`picked largest of N matching: ConsoleWindowClass:…, SWT_Window0:…`）。
   > **看到这行就要核对**：工作台是 `SWT_Window0` 且 ~2048×1536（约 2 MB），控制台只有 ~30 KB。
   > 多个 `SWT_Window0` = 多个实例，用 `-ProcId <你的 pid>`（从 `endpoint.json` 取）指定。
   > 该脚本**判空**：`PrintWindow` 返回 TRUE 但画出来是全黑时，它会换一个 flags 重试一次，
   > 仍空白就**不写盘并 rc=1** —— 所以"没有图"是有意义的结论，别当成工具坏了。
4. **处置**：默认只关窗（等同点右上角 X）。标题**用第 2 步枚举出来的真标题**，
   不是下面这个示例串（`Reset Perspective` 只是另一处的例子；你屏上很可能是 `Problem Occurred`）：

   ```bash
   pwsh -NoProfile -File tools/win-close.ps1 -TitleLike "<第2步枚举到的标题>" -ProcId <你的 pid>
   ```
   只有用例**显式声明**了按钮时才按下它（点按钮 = 替用户做不可逆决定）：

   ```bash
   pwsh -NoProfile -File tools/win-click-button.ps1 -TitleLike "<第2步枚举到的标题>" -ProcId <你的 pid> -Text "&No"
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

除 `ctl shell` 外的子命令，错误串都带 `; retry: <一条可复跑命令>`（`shell` 走直接回显桥回话的路径，不带）。
**但别把它当准绳**：① retry 是**按错误码套模板**生成的，不一定与该错误真正相关
（实测：文件不存在也会建议 `python -m ctl commands --json`）；② 它**不保证**能在
`TROUBLESHOOTING.md` 里 grep 到同一行 —— §7 只列了 12 种形态，而 CLI 实际会喷 45+ 种。
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
