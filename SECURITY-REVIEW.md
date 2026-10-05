# 安全相关改动 · 人工复审记录

**读者**：评审者 / 发布把关人。
**契约出处**：`design-project.md` §17.8（安全相关改动：网络绑定 / 写操作 / 危险命令白名单 → **人工复审**一次）、
`design-project.md` §15.4（安全基线四条）、`prd.md` A12（每条含 **日期 / 复审人 / 改动文件 / 判定 / 复核命令**
五字段，且 ≥1 条实体记录）。

**五字段格式（每条记录必须齐备）**

```
- **日期**：
- **复审人**：        ← 人类；AI 会话不得署名
- **改动文件**：
- **判定**：          ← 通过 / 有条件通过（须写条件） / 拒绝 + 理由
- **复核命令**：      ← 一条可直接复制执行、能独立复现判定的命令
```

**「复审人」纪律**：本文件署名的**必须是人类**。本文档集由 AI 起草，AI **不是**复审人；
若某条记录只有 AI 复核过，判定的可信度按「未复审」处理。

---

## 实体记录

### SR-2026-10-01-01 —— 桥只绑回环地址

- **日期**：2026-10-01
- **复审人**：alice（人类）
- **改动文件**：`bridge/src/ctl/bridge/LiveBridge.java`（监听套接字构造）
- **判定**：**有条件通过**。理由：`new ServerSocket(PORT, 50, InetAddress.getByName("127.0.0.1"))`
  把绑定地址**硬编码为回环**，不接受来自其它主机的连接；端口可配（`-Dctl.port` / `CTL_PORT` / 默认 8777）
  **不改变**绑定地址，故改端口不扩大暴露面。
  **条件（残余风险，必须随发布说明携带）**：桥**没有任何鉴权面** —— 本机上任何进程/用户都能连。
  单用户开发机可接受；**多用户共享机器不得使用本工具**。
  （原条目曾写「默认 `token` 为空 ⇒ …必须启用 `token`」：`token` / `auth <token>` 握手
  **该项不存在，已删**（2026-10-03，见下方待复审队列与 `protocol.md` §5）——桥侧从未实现它。）
- **复核命令**：
  ```bash
  grep -n 'InetAddress.getByName("127.0.0.1")' bridge/src/ctl/bridge/LiveBridge.java
  ```
  期望输出（唯一命中，绑定地址为回环字面量）：
  ```
  273:        server = new ServerSocket(PORT, 50, InetAddress.getByName("127.0.0.1"));
  ```

### SR-2026-10-01-02 —— 端口可配不改变监听地址

- **日期**：2026-10-01
- **复审人**：alice（人类）
- **改动文件**：`bridge/src/ctl/bridge/LiveBridge.java`（端口解析 `resolvePort()`）
- **判定**：**通过**。理由：端口解析顺序固定为
  `-Dctl.port` > 环境变量 `CTL_PORT` > `8777`（`DEFAULT_PORT`），且解析结果只作为**端口实参**使用；
  绑定地址仍是同一行的回环字面量。⇒ 新增的可配置面**不引入新的网络暴露**，
  也不接受外部主机注入监听地址（无「绑定地址可配」这一项）。
- **复核命令**：
  ```bash
  grep -n 'getProperty("ctl.port")\|getenv("CTL_PORT")\|InetAddress.getByName("127.0.0.1")' bridge/src/ctl/bridge/LiveBridge.java
  ```
  期望输出（两条解析 + 一条回环绑定同时可见）：
  ```
  142:        String v = System.getProperty("ctl.port");
  143:        if (v == null || v.trim().isEmpty()) v = System.getenv("CTL_PORT");
  273:        server = new ServerSocket(PORT, 50, InetAddress.getByName("127.0.0.1"));
  ```

### SR-2026-10-01-03 —— 本地资源耗尽防护（连接上限 + 错误码闭集）

- **日期**：2026-10-01
- **复审人**：alice（人类）
- **改动文件**：`bridge/src/ctl/bridge/LiveBridge.java`（并发上限与错误码常量）
- **判定**：**有条件通过**。理由：并发上限 `MAX_CONNECTIONS = 8`，超出即回 `ERR busy` 并关闭连接，
  单条连接的长请求不再阻塞整桥（accept 改每连接一线程 ⇒ 本地资源被单请求占满的风险下降）；
  错误码收敛为**闭集 8 个**（`CODES`），未映射异常归 `internal` 并**带原始异常类名**。
  **条件（残余风险）**：`internal` 的 message 会带异常类名与一行消息 ⇒ 对**本机**读端可见；
  这在同机同用户边界内可接受，但不得把桥日志（`bridge.log`）对外发布。
- **复核命令**：
  ```bash
  grep -n 'static final int MAX_CONNECTIONS\|static final int PROTOCOL_VERSION\|private static final int DEFAULT_PORT\|String CODES' bridge/src/ctl/bridge/LiveBridge.java
  ```
  期望输出：
  ```
  100:    static final int PROTOCOL_VERSION = 1;
  102:    private static final int DEFAULT_PORT = 8777;
  104:    private static final int MAX_CONNECTIONS = 8;
  125:    private static final String CODES =
  ```

### SR-2026-10-05-01 —— 影子留档是**未脱敏整窗帧**（**待人工复审**）

- **日期**：2026-10-05
- **复审人**：        ← **留空**：本文件明文「AI 不是复审人，本文档集由 AI 起草」；本条待人工署名后按「已复审」计
- **改动文件**：`ctl/shadow.py`（2026-10-01 引入影子留档）、`ctl/lifecycle.py`（2026-10-05 新增跨 run 回收 `auto_gc()`）、`.gitignore`
- **判定**：**待人工复审**。下面 6 条实情均已实测（逐条可复跑，见「复核命令」）：

  1. **未脱敏且是整窗** —— `PrintWindow` 拍的是**整个窗口**，含代码内容与工作区**绝对路径**。
     连**文件名**都带路径与用户名：实测 `<run_root>/gs32-handoff/shadow/0003-143303-ws_C_Users_Alice_eclipse_ctl_runs_gs32_h.png`
     （`ws_C_Users_Alice_eclipse_ctl_runs_gs32_h` = 窗口标题 `ws - C:\Users\Alice\eclipse-ctl\runs\gs32\h` 的转写）。
     ⇒ **本机同用户边界内可接受；不得把 `shadow/` 目录的内容对外发布**（与 `SR-2026-10-01-03` 对 `bridge.log` 的条件同源）。
  2. **落盘位置**：`<run_root>/<run_id>/shadow/`；内置默认 `<user.home>/.eclipse-ctl/runs/…`（**仓外**）。
     把 `run_root` 配到仓内时，由 2026-10-05 新增的 `**/shadow/` 规则兜住（见第 6 条）。
  3. **保留期**：**单 run 内 20 帧 / 32 MB**，超限删**最旧的非 promoted**；**`promoted` 永不裁**
     （`ctl/shadow.py:62-63`、`:718-719`）。
     ⚠️ **`promoted` 的"永不裁"是每 run 内的保证** —— run 目录本身被回收后，promoted 帧**一并消失**。
     **跨 run**：2026-10-05 起，收工路径（`uninstall` / `run --stop`）按 **target** 各留 **3** 个 run；
     可用配置键 `auto_gc=false`（文件 / `ECLIPSE_CTL_AUTO_GC`）关闭；手动 `ctl gc --yes` 保持"全局 + 照删"。
  4. **读取面**：`python -m ctl shadow [--seq N]` —— **纯读盘**（`ctl/shadow.py:666 → :644`），**不连桥**。
     ⇒ **桥后来死掉，死前拍下的帧仍然列得出来**（这是留档存在的主要理由）。
     **不承诺**：桥**从头**不可达 ⇒ 该 run **一张帧都没有**。
  5. **不进判据**：观测通道会撒谎（`PrintWindow` 有"返回 TRUE 却整张全黑"的失败模式），
     故用**构造性保证**钉住 —— `grep -rn shadow ctl/verify ctl/screen.py` **零输出**。
  6. **不进版本库**：`**/shadow/`（2026-10-05 新增；`manifest.jsonl` 含窗口标题、路径、动作参数摘要，
     不被 `*.png` 覆盖）。
- **复核命令**：
  ```bash
  # ① 未脱敏的证据：文件名里带绝对路径与用户名
  python -c "import os;print('\n'.join(sorted(os.listdir(r'C:\Users\Alice\.eclipse-ctl\runs\gs32-handoff\shadow'))))"
  # ② 不进判据（构造性保证；期望零输出且 rc=1）
  grep -rn shadow ctl/verify ctl/screen.py
  # ③ 不进版本库：必须用**自定义 run_root**，否则会被 /runs/ 掩盖
  git check-ignore -v myroot/x/shadow/manifest.jsonl
  ```
  期望输出（2026-10-05 实跑，`shadow/` 共 17 个文件）：
  ```
  0001-143200-ws_GS32_Studio.png
  0003-143303-ws_C_Users_Alice_eclipse_ctl_runs_gs32_h.png      ← 绝对路径 + 用户名
  0021-143423-Reset_Perspective.png
  ...（共 16 帧 + manifest.jsonl）
  （② 无输出，rc=1）
  .gitignore:33:**/shadow/	myroot/x/shadow/manifest.jsonl
  ```

---

## 待复审队列（**尚未**取得人工复审，不得计入实体记录）

| 标的 | 安全基线条款 | 状态 |
|---|---|---|
| 写操作**默认 dry-run**、需显式 `--yes` | `design-project.md` §15.4 第 2 条 / §16.2 | 待 `ctl/` 落地后复审（CLI 侧，不改桥） |
| 控制台**危险命令黑名单默认拒绝**（`init` / `close` / `shutdown` / `exit` / `threads -t` / `gc`） | `design-project.md` §15.4 第 3 条 | 待 `ctl/` 落地后复审 |
| ~~`token` 启用路径（启用后首行 `auth <token>`）~~ | ~~`design-project.md` §15.4 第 4 条 / `protocol.md` §5~~ | **该项不存在，已删**（2026-10-03）：桥侧从未实现该握手，需求条目为 AI 自造、非用户口径；配置键 `token` / 握手首行 / `endpoint.json` 字段一并移除，见 `protocol.md` §5 |
| 桥内不做任何点击动作（模态框交由外部处置） | `design.md` §5（「桥内不自动点」） | 待桥侧用例落地后复审 |
| 元素寻址原语（`act_click_button` 一族）未声明用例时拒绝执行 | `prd.md` A12b ② | 待 `ctl/` 落地后复审 |

---

## 新条目模板（照抄填写）

```markdown
### SR-<YYYY-MM-DD>-<NN> —— <一句话结论>

- **日期**：<YYYY-MM-DD>
- **复审人**：<人类姓名>
- **改动文件**：<仓库相对路径（可多个）>
- **判定**：<通过 / 有条件通过（写条件） / 拒绝（写理由）>
- **复核命令**：
  ```bash
  <一条可直接复制执行、能独立复现判定的命令>
  ```
  <贴该命令的期望输出>
```
