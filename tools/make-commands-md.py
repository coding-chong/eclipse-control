#!/usr/bin/env python3
"""Regenerate `COMMANDS.md` from `commands.json` -- the human-readable twin.

`commands.json` is the machine-readable artifact (A8 / R8: one record per command,
six fields).  This script renders the *same* records as a Markdown table, so the two
can never disagree: it reads the JSON, never the bridge.

Run it right after regenerating the JSON:

    python -m ctl commands export --json --full --run-id <id> > commands.json
    python tools/make-commands-md.py

Exit codes: 0 written / 2 the JSON is missing or is not a `--full` export (a
bare id list has no `fields` and its records are strings, not objects).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(REPO_ROOT, "commands.json")
MD_PATH = os.path.join(REPO_ROOT, "COMMANDS.md")


def _cell(value: Any) -> str:
    """Markdown-safe cell: a raw `|` inside a command name would split the row."""
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def render(data: Dict[str, Any]) -> str:
    fields: List[str] = list(data.get("fields") or [])
    rows: List[Dict[str, Any]] = list(data.get("commands") or [])
    handler_only: List[str] = list(data.get("handler_only") or [])
    # 没有 `--full` 的导出：`commands` 是一串裸 id 字符串、且没有 `fields`。**必须显式失败** ——
    # 否则 `for f in fields`（空）会渲染出一张空表并 rc=0，把"不是这张表"伪装成"表是空的"
    # （`measurement-hygiene.md` §13.6：空结果与查找错误必须用退出码分开）。
    if not fields:
        raise ValueError("no 'fields' list -- this JSON is not a `--full` export")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("'commands' holds bare ids, not records -- not a `--full` export")

    out: List[str] = [
        "# Eclipse 命令表（自省产物）",
        "",
        "> **本文件由 `commands.json` 生成，不要手改。** 重新生成：",
        "> ```bash",
        "> python -m ctl commands export --json --full --run-id <id> > commands.json",
        "> python tools/make-commands-md.py",
        "> ```",
        "",
        "| target | run_id | total | returned | truncated | handler_only |",
        "|---|---|---|---|---|---|",
        "| %s | %s | %s | %s | %s | %d |" % (
            _cell(data.get("target")), _cell(data.get("run_id")), _cell(data.get("total")),
            _cell(data.get("returned")), _cell(data.get("truncated")), len(handler_only)),
        "",
        "`handler_only` —— **不在** `getDefinedCommandIds()` 里（桥按 plugin.xml 尽力扫出来的，"
        "见 `boundaries.md` 的 A8 条）：",
        "",
    ]
    out += ["- `%s`" % hid for hid in handler_only] or ["（无）"]
    out += [
        "",
        "## 全量 %d 条（%d 字段）" % (len(rows), len(fields)),
        "",
        "| " + " | ".join(fields) + " |",
        "|" + "|".join(["---"] * len(fields)) + "|",
    ]
    for row in rows:
        out.append("| " + " | ".join(_cell(row.get(f)) for f in fields) + " |")
    out.append("")
    return "\n".join(out)


def main() -> int:
    if not os.path.isfile(JSON_PATH):
        print("ERR notfound %s; run the export command in its header first" % JSON_PATH,
              file=sys.stderr)
        return 2
    with open(JSON_PATH, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or not isinstance(data.get("commands"), list):
        print("ERR badrequest %s has no 'commands' list; regenerate it with --full"
              % JSON_PATH, file=sys.stderr)
        return 2
    try:
        text = render(data)
    except ValueError as exc:
        print("ERR badrequest %s: %s; regenerate it with --full" % (JSON_PATH, exc),
              file=sys.stderr)
        return 2
    with open(MD_PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print("wrote %s (%d commands)" % (MD_PATH, len(data["commands"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
