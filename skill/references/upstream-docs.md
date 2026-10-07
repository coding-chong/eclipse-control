# 上游出处（外部权威）

本技能依赖的机制里，有一部分**只有上游写了**，有一部分**上游没写**。这里只放
**指针 + 逐字引用 + 取回办法** —— 不放转述、不放整篇副本
（`measurement-hygiene` §13.9：镜像 / 快照类内容要么绑定它描述的那一次，要么只留一条可复跑的漂移检查）。

> **每条都要带身份。** 「官方文档」不是一个对象：`help.eclipse.org/latest` 是 CDT **上游最新**，
> 与 CCS 12.8.1 自带的那套 CDT（`5.4.1100`）**不是同一份** —— 实测（2026-10-07）后者的
> `org.eclipse.cdt.doc.user` jar 里**没有** `cbs_*` 页。

## 一、本机发行版里就有（与所装版本对齐，优先用这些）

（`<CCS>` = CCS 根目录 = 该 target `install_dir` 的上一级；本机取值见 `python -m ctl targets show ccs12`。）

| 内容 | 路径 |
|---|---|
| TI CCS 用户指南 —— 调试章（Target Configuration Files / Debug Configurations / …） | `<CCS>/eclipse/plugins/com.ti.ccstudio.usersguide.doc_<ver>/html/users_guide/ccs_debug-main.html` |
| TI 用户指南的章节目录（纯 XML，可直接搜） | **插件根目录**（不在 `html/` 下）`toc.xml`、`toc_debug-*.xml` |
| Eclipse 平台 / CDT 用户指南（zip，成员是 HTML） | `<CCS>/eclipse/plugins/org.eclipse.platform.doc.user_*.jar`、`org.eclipse.cdt.doc.user_*.jar` |
| LaunchBar 的扩展点契约（它能贡献什么，由这几份定义） | `org.eclipse.launchbar.core_*.jar!/schema/launchBarContributions.exsd`、`launchTargetTypes.exsd`、`org.eclipse.launchbar.ui_*.jar!/schema/launchBarUIContributions.exsd`、`launchTargetTypeUI.exsd` |

**它们没写的**（实测 2026-10-07）：TI 用户指南的调试章节目录只有
`Target Configuration Files / Debug Configurations / Debug Properties / Program/Memory Load Options /
Auto Run and Launch Options / Misc/Other Options / Disassembly Style Options / Flash Settings / MSP430 Debugger Options`
—— **没有一项**讲「LaunchBar 的活动启动模式」。两个 launchbar 插件包的文档类条目**各只有 1 个
`about.html`**（EPL 许可证文本），其余全是 `pom` / i18n 串 / `.exsd` schema。

## 二、只在上游站点（本机没有）

| 事实 | 出处（带身份） | 逐字 | 取回 |
|---|---|---|---|
| Run / Debug 两个按钮，以及模式选择器 | Eclipse Help *Using the Launch Bar*（`help.eclipse.org/latest`，CDT 上游） | "Run button, to launch a run. This button will change to a Debug button in Debug mode." ／ "Launch mode selector. To change between Run and Debug mode." | URL A |
| 每个描述符各有活动模式，且**持久化在偏好存储里** | Eclipsepedia `CDT/LaunchBar`（2014-07-17 最后修改；该 wiki 已只读） | "Each descriptor has an active mode and active target. This is persisted in preference store." | URL B |
| 模式决定装哪个二进制、开哪个视角 | QNX IDE 用户指南 *Launch modes*（QNX 是 LaunchBar 的贡献方） | "the launch mode determines ... which perspective is opened" ／ "Run: Launch an application on a target. No IDE tool is run ... and no debugger is attached to it." | URL C |

```
URL A  https://help.eclipse.org/latest/topic/org.eclipse.cdt.doc.user/getting_started/cbs_launchbar.htm
URL B  https://wiki.eclipse.org/CDT/LaunchBar
URL C  http://qnx.com/developers/docs/7.1///com.qnx.doc.ide.userguide/topic/launch_modes.html
```

## 三、上游**没有**写的（本仓自己测出来的）

权威处是**用例自己的 H2 注释**（`board.led_chase`，见 `ctl/` 下的用例目录；R11 要求知识写在用例注释里）：

- LaunchBar 自建那状态时，描述符的活动模式默认记 **`run`**；
- `run` 模式下 `launchActive` 回**干净 `OK` 且零效果** —— 无弹框、无报错、无会话；
- 偏好里**键名 / 键值的形状**（`…descriptorType.default\<node>/activeLaunchMode=<run|debug>`，冒号按 `.prefs` 格式转义）——
  wiki 只说"存偏好里"，**没说键名**；那是从三个真实工作区读出来的。
