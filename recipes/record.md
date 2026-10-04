# record — 探索一次，落成脚本（录的是 ctl 命令会话，不是 GUI 手点）

**用途**：把「手敲一段探索性命令」自动落成可复跑的脚本，下次不再手敲。

**填占位符**：`<RUN_ID>` 任取（如 `r1`）；`<RUN_ROOT>` 内置默认 `<user.home>/.eclipse-ctl/runs`。
以下命令在**仓库根目录**执行。

> ⚠️ **它不是 GUI 录制器**：`--record` 记录的是 **`ctl` 命令会话**，
> **不能**捕捉用户在界面上手工点击（那是 SWTBot recorder / RCPTT 的能力，本轮不投入）。
> 出处：`design.md` §11 取舍表「GUI 事件录制 | 不做」。

## 1. 前置：起实例

```bash
python -m ctl doctor --target gs32
python -m ctl install --target gs32 --run-id <RUN_ID>
```

```text
all checks passed (8/8)
OK  bridge live on 127.0.0.1:8777  (protocol 1, version 0.1.0)
```

## 2. 开一个**带录制**的交互会话

```bash
python -m ctl shell --target gs32 --run-id <RUN_ID> --record "<RUN_ROOT>/<RUN_ID>/record.sh"
```

提示符出现后，逐行敲下面这些（`shell` 里每行就是一个**桥方法调用**，首 token 必须含 `.`）：

```text
sys.env
ui.parts
ui.viewids com.gs
cmd.runp org.eclipse.ui.views.showView viewId=com.gs.memory.view
ui.parts
ui.close com.gs.memory.view
quit
```

```text
OK  java.version=23.0.2 | os.name=Windows 11 | bundle=eclipse-ctl.bridge id=351 state=32 | thread=gs32ctl-bridge
OK  perspective id=org.eclipse.cdt.ui.CPerspective views=7 editors=0
OK  registeredViews total=55 matched(prefix=com.gs)=5 returned=5 truncated=false
OK  executed org.eclipse.ui.views.showView
OK  perspective id=org.eclipse.cdt.ui.CPerspective views=8 editors=0
OK  closed com.gs.memory.view stillOpen=False
recorded 6 line(s) -> <RUN_ROOT>/<RUN_ID>/record.sh
```

> 注意第 4、5 行：`viewids` 是**读**、`showView` 是**写**——写方法的判据是第 5 行的回读差（views 7→8），
> 不是第 4 行的 `OK`。
> `shell` 是原始通道：不挂 `--yes`（`--yes` 只挂在 `cmd` / `open` / `close` 三个写子命令上；
> 元素寻址的三个库原语用 `yes=True`，不走 `--yes`），
> 但危险 Gogo 命令仍需 `--allow-dangerous`（默认拒绝）。

## 3. 检查录制产物

```bash
cat "<RUN_ROOT>/<RUN_ID>/record.sh"
python -m ctl recipes list
```

```text
# eclipse-ctl recorded session  <RUN_ID>
sys.env
ui.parts
ui.viewids com.gs
cmd.runp org.eclipse.ui.views.showView viewId=com.gs.memory.view
ui.parts
ui.close com.gs.memory.view

NAME             STATUS
view-and-shot    ok
open-sources     ok
build-and-console ok
diag-when-hung   ok
record           ok
```

## 4. 把录下来的脚本变成正式配方（可选）

把 `record.sh` 的内容按 `recipes/<name>.md` 的样式落一份（首行 `# <name> — 一句话`，
正文放 ```` ```bash ```` 块），之后就能：

```bash
python -m ctl recipes run <name>
```

## 5. 收工

```bash
python -m ctl uninstall --target gs32 --run-id <RUN_ID> --verify-clean
```

```text
[clean] ss: bundle absent
[clean] configuration: no residue
[clean] port released
[clean] no process
```

> 一键版：`python -m ctl recipes run record`
> （先把 `<RUN_ID>` / `<RUN_ROOT>` 替换成实际值——仍有未替换的 `<...>` 占位符时 CLI **拒绝执行**、退出码 1；
> 但 `record` 配方是**交互式**的，`recipes run` 更适合当“起点说明书”，真正的录制请按第 2 步手敲）
