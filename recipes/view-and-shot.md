# view-and-shot — 打开一个厂商视图，用回读差判定，并自动截图存档

**填占位符**：`<RUN_ID>` 任取（如 `vs1`）；`<RUN_ROOT>` 内置默认 `<user.home>/.eclipse-ctl/runs`
（若照 `design-obs-ux.md` §14.6 的示例配置，则为 `D:/tmp/eclipse-ctl`）。
以下命令一律在**仓库根目录**执行（脚本路径 `tools/` 是相对仓库根的）。

## 1. 前置：环境就绪 + 起实例

```bash
python -m ctl doctor --target gs32
python -m ctl install --target gs32 --run-id <RUN_ID>
```

```text
[PASS] source_dir exists                    <TARGET_INSTALL>
[PASS] product                              Eclipse Platform 4.30.0
...
all checks passed (8/8)
no-copy mode: isolated configuration at <RUN_ROOT>/<RUN_ID>/configuration
installed eclipse-ctl.bridge id=351 -> started
OK  bridge live on 127.0.0.1:8777  (protocol 1, version 0.1.0)
```

## 2. 前快照

```bash
python -m ctl parts --run-id <RUN_ID> --json > "<RUN_ROOT>/<RUN_ID>/pre.parts.json"
```

```text
perspective  org.eclipse.cdt.ui.CPerspective
views=7  editors=0
```

## 3. 动作（写方法 → 必须 `--yes`）

```bash
python -m ctl cmd --run-id <RUN_ID> org.eclipse.ui.views.showView viewId=com.gs.memory.view --yes
```

```text
OK  executed org.eclipse.ui.views.showView
```

## 4. 后快照 + 取差（**回读差才是判据**，不看上一步的 `OK`）

```bash
python -m ctl parts --run-id <RUN_ID> --json > "<RUN_ROOT>/<RUN_ID>/post.parts.json"
python -c "import json;a=json.load(open(r'<RUN_ROOT>/<RUN_ID>/pre.parts.json'));b=json.load(open(r'<RUN_ROOT>/<RUN_ID>/post.parts.json'));print('added =', sorted(set(b['views'])-set(a['views'])))"
```

```text
added = ['com.gs.memory.view']
```

> `--json` 的字段名以 CLI 实际输出为准；若键名不同，把 `views` 换成实际键名就行
> ——**判据是「视图集合多了该 id」，不依赖键名**。

## 5. 自动截图存档（观测：图是辅证，回读是主判据）

```bash
pwsh -NoProfile -File tools/shot-window-pw.ps1 -TitleLike "GS32_Studio" -Out "<RUN_ROOT>/<RUN_ID>/shots/view-and-shot.png"
```

```text
saved <RUN_ROOT>/<RUN_ID>/shots/view-and-shot.png  rect=...,... (PrintWindow, DPI-aware)
```

## 6. 收工（写方法的回滚：关掉刚开的视图）

```bash
python -m ctl close --run-id <RUN_ID> com.gs.memory.view --yes
python -m ctl parts --run-id <RUN_ID> --json > "<RUN_ROOT>/<RUN_ID>/rollback.parts.json"
python -m ctl uninstall --target gs32 --run-id <RUN_ID> --verify-clean
```

```text
OK  closed com.gs.memory.view (stillOpen=False)
[clean] ss: bundle absent
[clean] configuration: no residue
[clean] port released
[clean] no process
```

> 一键版：`python -m ctl recipes run view-and-shot`
> （先把 `<RUN_ID>` / `<RUN_ROOT>` 替换成实际值——**配方里还有未替换的 `<...>` 占位符时，CLI 会拒绝执行并退出码 1**）
