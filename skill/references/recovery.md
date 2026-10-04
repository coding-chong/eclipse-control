# 恢复：target 没配 / 桥超时 / 界面卡死

主路径是**库函数**（`ctl run` 的脚本命名空间）；shell 版装置在 §C，**只在库函数这条路走不通时**用。

---

## A. 换一台机器：内置 target 的安装根不是你的

内置矩阵里 `gs32` / `ccs12` 各带一个 `install_dir`，值是**参考机**的路径。换机器后，
第一次起实例会停在这一条上（2026-10-04 取自 `ctl/lifecycle.py::_install_dir_missing` 的原文形态）：

```
ERR notfound target 'gs32' install_dir does not exist: D:/ProgramFiles/GS32_Studio_v1.2.5.2/GS32_Studio_v1.2.5.2; it is the reference machine's value -- set yours with: python -m ctl targets add gs32 --source-dir <the directory that contains GS32.exe>
```

这条串**两处**会变，别把它当固定文本去 grep：

| 槽位 | 内置矩阵（新 clone 的默认） | 你在配置文件里给过的路径 |
|---|---|---|
| `install_dir does not exist:` 后面的路径 | 参考机那份 | 你的那份 |
| `;` 与 `-- set yours with:` 之间 | `it is the reference machine's value` | `it is not on this machine` |

**不变量**（可 grep 的部分，逐字）：

```
target '<name>' install_dir does not exist:
-- set yours with: python -m ctl targets add <name> --source-dir <the directory that contains <launcher>>
```

**修法**（把 `--source-dir` 换成你机器上的安装根，两个 target 各设一次）：

```bash
python -m ctl targets add gs32  --source-dir <你的 GS32_Studio 安装根>
python -m ctl targets add ccs12 --source-dir <你的 ccs/ccs/eclipse 目录>
python -m ctl targets list      # INSTALL_DIR 列应是你的路径
```

覆盖写进 `~/.eclipse-ctl/config.json`（`--config` 可换文件）。JRE 级别 / 端口 / 启动器沿用内置值；
产品版本换了再一起给：`python -m ctl targets add gs32 --source-dir <安装根> --java-level 17 --launcher GS32.exe`。

> **本机偏测的限度**：本机没有 `~/.eclipse-ctl/config.json`，但两个内置安装根本机**都在** ⇒ 走不出
> 「install_dir does not exist」。要复现这条串，得给一份 `--config` 把某个 target 指到不存在的目录
> （此时 origin 是 `it is not on this machine`）。**「新机器上第一次连接就会报这条」跨机器未验。**

---

## B. 超时后怎么办（主路径）

**不许**认定「没执行」—— 桥用 `asyncExec`，超时只结束**等待**，排队的动作**仍可能生效**。

1. **先看**（只读，无副作用）：拿这个 run 的可见顶层窗，再从里面认那个框的真标题。

   ```python
   for hwnd, (pid, cls, title) in sorted(windows().items()):
       print(hwnd, cls, title)
   ```

   `#32770` 是原生对话框的窗口类。**顺序不能反** —— 弹框标题通常不含产品名，
   按主窗名去截会拍到**一张没有框的图**，正好把你推向「一切正常」。

2. **再拍**：一帧证据图落到 `<run 目录>/shots/`，回「真路径 + 窗口行」。

   ```python
   print(see(name="hung"))                    # 不给 title 时优先拍对话框
   print(see(name="hung", title="Preferences"))  # 已知标题时钉死它
   ```

   `see()` 走 `tools/shot-window-pw.ps1`（`PrintWindow`，免疫遮挡/DPI）；**空图会被工具自己拒掉**
   （不落盘、`exit 1`）—— 所以它返回的路径一定是**非空白** PNG。没有可见窗时它**不写盘**直接抛
   `ScreenError`（fail closed：宁可不产出，也不拍一扇别的窗）。

3. **处置**：默认**只关窗**（等同点右上角 X）。

   ```python
   print(close_window("Preferences", yes=True))      # 默认 dry-run，yes=True 才真关
   ```

   只有用例**显式声明**了按钮时才按它（点按钮 = 替用户做不可逆决定）：

   ```python
   print(act_click_button("Preferences", text="&No", yes=True))
   ```

   同名按钮不止一个时**不要挑第一个**：命中 0 或 >1 都失败并列出候选；确实要选第 n 个就显式给 `index=`
   （0 基；序位**只在同一会话内**稳定，跨运行会漂移）。

4. **探活 —— 但「ping 得通」证明不了「界面没卡」**：模态框在屏上时，**另一条连接**的
   `ui.parts` / `ui.tree` / `sys.ping` **全都正常返回**（SWT 模态框跑的是嵌套事件循环）；
   只有**发起那次请求自己**会 `ERR timeout`。
   ⇒ 别拿「`ui.*` 通不通」判断界面卡没卡，直接**枚举/截图看那个框在不在**。
   ⇒ 反过来也要记住：**你发的那次请求超时了，不代表别的连接也干不了活**。

5. **再取一次回读差**，把差值归因到先前那次超时请求 —— **这一步不能省**，
   否则会把迟到的副作用算到下一次动作头上。

---

## C. Fallback：shell 版装置

库函数走不通（例如 pwsh 不在、或你已经在 shell 里排障）时，同一套动作的 shell 版：

```bash
# 1) 枚举（-Class "#32770" = 只要原生对话框）
pwsh -NoProfile -File tools/win-enum.ps1 -Class "#32770"

# 2) 按标题截图（多实例时用 -ProcId 认准自己那扇）
pwsh -NoProfile -File tools/shot-window-pw.ps1 -TitleLike "<上一步枚举到的标题>" -ProcId <pid> -Out "<运行目录>/hung.png"

# 3) 关窗（默认处置）
pwsh -NoProfile -File tools/win-close.ps1 -TitleLike "<真标题>" -ProcId <pid>

# 4) 点按钮（仅当用例显式声明了按钮）
pwsh -NoProfile -File tools/win-click-button.ps1 -TitleLike "<真标题>" -ProcId <pid> -Text "&No"
```

- 同名按钮不止一个时**不要挑第一个**：`-Text` 命中 **0 或 >1 都 `exit 1`**（后者列出候选）。
  确实要选第 n 个，就**显式**给 `-Index <n>`（0 基；序位只在同一会话内稳定）。
- `tools/*.ps1` 的错误回话是**英文**，而库函数那一层已经把它们翻成了带 `retry:` 的 `ERR` 行；
  行为差异也以库函数那份契约为准。

---

## D. 归因纪律（几条，都实测过）

- **命中 0 / >1 是两个独立的失败**：都必须在**发送任何输入之前**就拒（先枚举后动手）。
  只修「命中 0」会留下更隐蔽的那个 —— 多命中时静默挑第一个，看起来一切正常。
- **`err` 与「无回读差」要分开归因**：一条「没反应」在**排除目标自身状态**（插入点 / 选区 / 只读 / IME）
  之前不构成结论。最便宜的自检：换一个不依赖该状态的输入再打一次。
- **枚举器不是取值器**：`win-enum.ps1` 与 `win-send-input.ps1 -ListOnly` 的输出**只**用来定
  类名 / 可见性 / 矩形 / 序位。跨进程 `GetWindowText` 对**这个产品的 `Edit`** 恒回空 —— 值与行为都看像素。
- **`shots/` 不是 `shadow/`**：`shots/` 是**证据**（`shot-window-pw.ps1`，`see()` 写的）；
  `shadow/` 是**留档**（`win-probe.ps1`，声明不是判据）。两者不得互相顶替，见
  [`observation.md`](observation.md)。
