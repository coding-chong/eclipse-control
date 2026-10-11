# 参与本仓（eclipse-ctl）

本仓是**一个能力库 + 一道门**：`ctl/` 是库（`import ctl` 可用），`python -m ctl run` 是那道门。
动手前先读两样：`DEVELOPING.md`（开发者仪器）与 `boundaries.md`（三层边界、什么**不进**用户路径）。

## 跑起来（不需要 IDE，也不需要板子）

```bash
python -m unittest discover -s tests -t .      # 全量单测（标准库 + 真文件，不碰 IDE）
python -m ctl preflight --target gs32          # 发布前总检（这一条**需要**目标 IDE 安装树）
```

`preflight` 里的**纯文本闸门**不需要 IDE，可以单独跑（CI 跑的就是这些 + 全量单测）：

```bash
python -c "from ctl.__main__ import _stdlib_only_check as f; print(f())"
```

其余同形的门：`_machine_path_check`（机器本地路径）、`_doc_command_consistency`（文档里的子命令名）、
`_dev_door_leak_check`（开发者工具不进用户面）、`_skill_namespace_consistency`（skill ↔ `ctl run` 命名空间）。

## 改动纪律（判据在流程仓，不在本仓）

`deliverable-shape.md` / `measurement-hygiene.md` 是**流程仓**的 `.trellis/spec/backend/` 下的两份判据
（本仓与流程仓是**两个独立的仓**，见 `DEVELOPING.md` 开头）。本仓的改动请自带：

- **判据**：写清「**什么条件下会红**」，并把那条反例**真跑一遍** —— 不写没跑过的读数；
- **变异账本**：一条变异只弄红它自己那条谓词（弄红了别条，说明变异打错了地方）；
- **闸门**：新能力要能进 `preflight`，否则它会静静地烂掉（**够不着它守的东西的守卫 = 不存在的守卫**）；
- **机器本地路径**：不得进 shipped 代码 —— `_machine_path_check` 会抓；内置 target 矩阵那两条
  「参考机标定」是**按值豁免**的，改它们要连同 `tests/unit/test_machine_path_gate.py` 的自有字面量一起改。

## 提交

- 一个改动一个主题；新行为在 `CHANGELOG.md` 的 `[Unreleased]` 下加一条，写清**判据**与**复跑命令**。
- 不提交生成物：`bridge/dist/`、`__pycache__/`（`.gitignore` 已覆盖）。
- 文档与代码同批改：README / `COMMANDS.md` / `TROUBLESHOOTING.md` 里提到的东西必须还存在
  （`_doc_command_consistency` 只查子命令名，**别指望它兜住别的**）。
