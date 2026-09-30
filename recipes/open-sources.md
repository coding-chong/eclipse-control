# open-sources — 把一批源文件开进 CDT 编辑器，用 editors 计数回读差判定

**填占位符**：`<RUN_ID>` 任取（如 `os1`）；`<RUN_ROOT>` 内置默认 `<user.home>/.eclipse-ctl/runs`；
`<ABS_C_SOURCE_1>` / `<ABS_C_SOURCE_2>` = **磁盘上真实存在的** `.c` / `.h` **绝对路径**。
本机可用的示例（照抄其中两个即可）：

```text
D:/gitclone/antigravity-proxy/src/buffer.c
D:/gitclone/antigravity-proxy/src/hde/hde64.c
```

以下命令在**仓库根目录**执行；`open` 接的是**绝对路径**，工作区外的文件也能开
（桥走 `EFS.getLocalFileSystem().fromLocalFile` → `FileStoreEditorInput`）。

## 1. 前置

```bash
python -m ctl doctor --target gs32
python -m ctl install --target gs32 --run-id <RUN_ID>
```

```text
all checks passed (8/8)
installed eclipse-ctl.bridge id=351 -> started
OK  bridge live on 127.0.0.1:8777  (protocol 1, version 0.1.0)
```

## 2. 前快照（记下 editors 计数）

```bash
python -m ctl parts --run-id <RUN_ID> --json > "<RUN_ROOT>/<RUN_ID>/pre.parts.json"
python -c "import json;print('editors =', json.load(open(r'<RUN_ROOT>/<RUN_ID>/pre.parts.json'))['editors'])"
```

```text
editors = 0
```

## 3. 开文件（写方法 → 必须 `--yes`）

```bash
python -m ctl open --run-id <RUN_ID> "<ABS_C_SOURCE_1>" --yes
python -m ctl open --run-id <RUN_ID> "<ABS_C_SOURCE_2>" --yes
```

```text
OK  opened <ABS_C_SOURCE_1>
OK  opened <ABS_C_SOURCE_2>
```

## 4. 后快照 + 取差（**判据在这里**，不在上一步的 OK）

```bash
python -m ctl parts --run-id <RUN_ID> --json > "<RUN_ROOT>/<RUN_ID>/post.parts.json"
python -c "import json;a=json.load(open(r'<RUN_ROOT>/<RUN_ID>/pre.parts.json'));b=json.load(open(r'<RUN_ROOT>/<RUN_ID>/post.parts.json'));print('editors', a['editors'], '->', b['editors'])"
```

```text
editors 0 -> 2
```

> 再看一眼编辑器明细（确认开的是 C 编辑器而不是纯文本编辑器）：
> `python -c "import json;print(json.load(open(r'<RUN_ROOT>/<RUN_ID>/post.parts.json')))"` →
> 每个编辑器条目的 `class` 应为 `org.eclipse.cdt.internal.ui.editor.CEditor`。
> **`--json` 的字段名以 CLI 实际输出为准**；本配方的判据是「编辑器**计数**变大」，不依赖键名
> （上面用的 `editors` 键名若不同，换成实际的即可）。

> 若 `editors` 计数没变：文件路径不存在（应当得到 `ERR notfound`）或实例不对（比对 `sys.env` 的 `bundle id`）。

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

> 一键版：`python -m ctl recipes run open-sources`（先把上面的占位符替换掉，否则 CLI 会**拒绝执行**并退出码 1）
