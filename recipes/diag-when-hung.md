# diag-when-hung — 超时自救：截图 → 读按钮 → 关窗/按按钮 → 探活 → 回读差复查

**用途**：桥「起了但不回话」（`recv 超时`）时的标准处置流程。**不许先猜、不许问用户**——先把画面抓下来自己看。

**填占位符**：`<RUN_ID>` 任取（如 `d1`）；`<RUN_ROOT>` 内置默认 `<user.home>/.eclipse-ctl/runs`。
以下命令在**仓库根目录**执行（`tools/` 是相对路径）。

## 1. 前置：起实例

```bash
python -m ctl doctor --target gs32
python -m ctl install --target gs32 --run-id <RUN_ID>
```

```text
all checks passed (8/8)
OK  bridge live on 127.0.0.1:8777  (protocol 1, version 0.1.0)
```

## 2. 制造（或遇到）一次超时

`org.eclipse.ui.window.resetPerspective` 会弹一个模态确认框，正好用来复现：

```bash
python -m ctl cmd --run-id <RUN_ID> org.eclipse.ui.window.resetPerspective --yes
```

```text
ERR timeout no response within 25000 ms; retry: python -m ctl shell --run-id <RUN_ID> -c "sys.ping"
exit 1
```

**此刻不要下结论**：`ERR timeout` 只表示**应答**超时，不代表动作没生效（见第 6 步）。

## 3. 先截图（**这一步不能省**）

```bash
pwsh -NoProfile -File tools/shot-window-pw.ps1 -TitleLike "GS32_Studio" -Out "<RUN_ROOT>/<RUN_ID>/shots/hung.png"
```

```text
saved <RUN_ROOT>/<RUN_ID>/shots/hung.png  rect=...,... (PrintWindow, DPI-aware)
```

打开这张图，**从图上读出**：框的标题、正文、按钮文字。典型会读到
`Reset Perspective` / `Reset the C/C++ perspective to its defaults?` / `[Reset Perspective] [ No ]`。

## 4. 枚举子窗，拿到按钮列表

```bash
pwsh -NoProfile -File tools/win-enum.ps1 -TitleLike ""
pwsh -NoProfile -File tools/win-click-button.ps1 -TitleLike "Reset Perspective" -ListOnly
```

```text
pid=8600 hwnd=0x160782 class=#32770 title=Reset Perspective
hwnd=0x2206AC class=Button text="&Reset Perspective"
hwnd=0x1F070E class=Button text="&No"
```

## 5. 处置

**默认：只关窗**（等同点右上角 X，不替用户做不可逆决定）：

```bash
pwsh -NoProfile -File tools/win-close.ps1 -TitleLike "Reset Perspective"
```

**只有用例显式声明了按钮时才按下它**（点按钮 = 替用户做决定）：

```bash
pwsh -NoProfile -File tools/win-click-button.ps1 -TitleLike "Reset Perspective" -Text "&No"
```

> `ctl act click-button --title "Reset Perspective" --text "&No" --yes` 是同一动作的 CLI 形式
> （当前只支持 `--text` 文本寻址，`--index` / `--path` 未支持，见 `boundaries.md` N11）。
> 两条路都**不用鼠标、不需前台**。

## 6. 探活 + **回读差复查**（最后一步，也是判据所在）

```bash
python -m ctl shell --run-id <RUN_ID> -c "sys.ping"
python -m ctl shell --run-id <RUN_ID> -c "ui.parts"
```

```text
OK  pong from eclipse-ctl.bridge   (0.0 s)
OK  perspective id=org.eclipse.cdt.ui.CPerspective  views=8 ...   ← 注意 views/perspective 相比超时前有没有变
```

- `sys.ping` 通 ⇒ 桥**可运维**（卡死期间只有 UI 方法不通，非 UI 方法照常）。
- **把第 6 步读到的 `ui.parts` 与超时前的快照取差**，差值归因到第 2 步那次超时请求：
  有变化 ⇒ `applied=yes`（**不要再重发**）；无变化 ⇒ `applied=no`，此时才允许重发。
- 判断规则出自 `protocol.md` §4.2：**`ERR timeout` 不是「未执行」的判据**。

## 7. 收工

```bash
python -m ctl uninstall --target gs32 --run-id <RUN_ID> --verify-clean
```

```text
[clean] ss: bundle absent
[clean] configuration: no residue
[clean] port released
[clean] no process
```

> 一键版：`python -m ctl recipes run diag-when-hung`
> （先把 `<RUN_ID>` / `<RUN_ROOT>` 替换成实际值——仍有未替换的 `<...>` 占位符时 CLI **拒绝执行**、退出码 1）
