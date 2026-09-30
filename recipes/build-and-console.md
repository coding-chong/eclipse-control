# build-and-console — 触发构建，用 `sys.wait jobs-idle` 判完工，再读 Console

**填占位符**：`<RUN_ID>` 任取（如 `b1`）；`<RUN_ROOT>` 内置默认 `<user.home>/.eclipse-ctl/runs`；
`<BUILD_COMMAND_ID>` = 由第 3 步**反查得到**的构建命令 id（**不要硬编码**——`cmd.run` 只是「发出命令」，
发完就返回，构建在后台 Job 里跑）。

以下命令在**仓库根目录**执行。

## 1. 前置

```bash
python -m ctl doctor --target gs32
python -m ctl install --target gs32 --run-id <RUN_ID>
```

```text
all checks passed (8/8)
OK  bridge live on 127.0.0.1:8777  (protocol 1, version 0.1.0)
```

## 2. 前快照（确认有一个工程/配置可构建）

```bash
python -m ctl shell --run-id <RUN_ID> -c "ui.parts"
```

```text
perspective id=org.eclipse.cdt.ui.CPerspective
views=8 editors=1
```

## 3. 反查构建命令 id（**参数自发现**，别猜）

```bash
python -m ctl commands find --text "Build" --json
```

```text
{"matches": [{"id": "<BUILD_COMMAND_ID>", "name": "Build ...", "handled": true}, ...]}
```

把输出里**带 handler 的那条** id 填进 `<BUILD_COMMAND_ID>`。

## 4. 触发构建（写方法 → 必须 `--yes`）

```bash
python -m ctl cmd --run-id <RUN_ID> <BUILD_COMMAND_ID> --yes
```

```text
OK  executed <BUILD_COMMAND_ID>
```

> 这条 `OK` **只说明命令发出去了**，**不说明构建完了**（F9：`OK` ≠ 到位）。

## 5. 完工判据（**两条，任一即可**；A13 要求的正是这条）

```bash
python -m ctl shell --run-id <RUN_ID> -c "sys.wait jobs-idle"
```

```text
OK  waited_ms=8420 idle=true jobs=0
```

- `idle=true` ⇒ 桥侧 `JobManager` 已空闲，构建 Job 结束。
- 若等了很久仍 `idle=false`（例如仍弹出模态框），会如实返回未完成，**不要**直接判成功。

或者读 Console 尾（读方法，不用 `--yes`）：

```bash
python -m ctl shell --run-id <RUN_ID> -c "ui.console --tail 40"
```

```text
console=Build (name from the active console)
text lines=240 returned=40 truncated=true tailRequested=40
  <Tail of the build output, ending with the builder's own "build finished" line>
```

- 完工串以**构建器自己的输出**为准（CDT 收尾会打印一行完工行）。
  **本配方不写死该串**——以你第 6 步实际读到的为准；若读不到收尾行，说明构建还没结束（回到上一步）。
- 只读**活动** Console；若活动 Console 不是构建那个，先激活它（`ui.console` 的已知边界）。

## 6. 收工

```bash
python -m ctl uninstall --target gs32 --run-id <RUN_ID> --verify-clean
```

```text
[clean] ss: bundle absent
[clean] configuration: no residue
[clean] port released
[clean] no process
```

> 一键版：`python -m ctl recipes run build-and-console`（先把 `<RUN_ID>` / `<BUILD_COMMAND_ID>` 替换掉——
> 仍有未替换的 `<...>` 占位符时 CLI **拒绝执行**、退出码 1；`sys.wait` 的 `jobs-idle` 是**唯一**不会假成功的完工判据）
