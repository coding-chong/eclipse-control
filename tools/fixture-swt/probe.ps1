# 夹具探针 —— 对 ctl-fixture 发**合成输入**并回读窗口标题。
#
# 定位：`Fixture.java` 的配套**取证装置**，不是产品工具。产品侧契约是
# `ctl act click-button` / `act send-keys` / `act set-text`（三个动作**只做元素寻址**）；
# 本脚本额外覆盖产品**不做**的两档 —— 坐标注入（②a/②b）与空白负例（⑥），
# 它们只用于 P6 的定论记录与证伪（见 `design-project.md` §18.2/§18.4）。
#
# 三条硬纪律（都是踩出来的）：
#
# 1. **stdout 只出 ASCII**。pwsh 的 `Write-Output` 按**控制台码页**（本机 cp936）编码，
#    调用方按 UTF-8 解码会直接抛 `UnicodeDecodeError`、连**已打出的行**一起丢
#    （实测：整段输出变成空，症状是"探针没输出"，极具误导性）。
#    ⇒ 诊断文字一律英文；标题本身由夹具决定，也是 ASCII。
# 2. **选窗 fail closed**。同 pid 下会有多扇顶层 `SWT_Window0`（工作台 / limbo / 阴影），
#    只按标题匹配会**静默选错**（实测出现"before 与上一状态对不上"）。
#    ⇒ 候选 = 标题匹配 ∧ 同 pid ∧ **同时有 Button 与 Edit 子窗**；恰好 1 个才用，
#      0 或 >1 一律报错退出。
# 3. **点类动作要重试**。本夹具实测约 8/9 落地（研究档 §2），不能假定一次必中；
#    对**期望无变化**的负例必须传 `-Retries 1`（重试只会重复发同一条消息）。
#
# 用法：
#   pwsh -NoProfile -File tools/fixture-swt/probe.ps1 -Assertion button -Retries 3
#   pwsh -NoProfile -File tools/fixture-swt/probe.ps1 -Assertion children -WaitSecs 60 -ProcId 1234
#
# 退出码：0 = 取到结论（**不表示标题变了**，变没变看 verdict 行）；1 = 选窗/选控件失败。
param(
    [string]$TitleLike = 'ctl-fixture',
    [ValidateSet('title', 'children', 'button', 'key', 'text',
                 'coord-button', 'coord-shell-at-button', 'coord-blank')]
    [string]$Assertion = 'title',
    [string]$Payload = 'HELLO',
    # 等窗口出现（秒）。首次 pwsh 调用要现场 Add-Type 编译 C# 类（实测 40-50 s），
    # 所以轮询放在**本进程内**，避免每次轮询都重付一次 Add-Type。
    [int]$WaitSecs = 0,
    # 0 = 不限进程。多实例并存时**必须给**，否则会选到别的夹具。
    [int]$ProcId = 0,
    [int]$SettleMs = 900,
    [int]$Retries = 1
)

Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class P6 {
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }

  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumProc cb, IntPtr p);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern IntPtr SendMessageW(IntPtr h, uint m, IntPtr wp, IntPtr lp);
  [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr h, uint m, IntPtr wp, IntPtr lp);
  [DllImport("user32.dll", CharSet=CharSet.Unicode, EntryPoint="SendMessageW")]
  public static extern IntPtr SendMessageStr(IntPtr h, uint m, IntPtr wp, string lp);

  public static IntPtr[] Matching(string like, int wantPid) {
    var list = new List<IntPtr>();
    EnumWindows(delegate(IntPtr h, IntPtr p) {
      if (!IsWindowVisible(h)) return true;
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      if (t.ToString().IndexOf(like, StringComparison.OrdinalIgnoreCase) < 0) return true;
      if (wantPid != 0) { uint pid; GetWindowThreadProcessId(h, out pid); if ((int)pid != wantPid) return true; }
      list.Add(h); return true;
    }, IntPtr.Zero);
    return list.ToArray();
  }

  public static string Title(IntPtr h) {
    var t = new StringBuilder(512); GetWindowTextW(h, t, 512); return t.ToString();
  }

  // 指纹：同时拥有 Button 与 Edit 子窗的才是**夹具本体**。
  // 同 pid 下那几扇辅助 `SWT_Window0`（limbo / 阴影）标题也可能一样，但没有这两个子窗。
  // 返回 -1 = 缺 Button，-2 = 缺 Edit，1 = 命中。
  public static int Fingerprint(IntPtr h, int[] counts) {
    counts[0] = 0; counts[1] = 0;
    EnumChildWindows(h, delegate(IntPtr c, IntPtr p) {
      var k = new StringBuilder(256); GetClassNameW(c, k, 256);
      if (k.ToString() == "Button") counts[0]++;
      else if (k.ToString() == "Edit") counts[1]++;
      return true;
    }, IntPtr.Zero);
    if (counts[0] == 0) return -1;
    if (counts[1] == 0) return -2;
    return 1;
  }

  public static string[] Children(IntPtr root) {
    var res = new List<string>();
    EnumChildWindows(root, delegate(IntPtr h, IntPtr p) {
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      var c = new StringBuilder(256); GetClassNameW(h, c, 256);
      res.Add(h.ToInt64() + "|" + c.ToString() + "|" + t.ToString());
      return true;
    }, IntPtr.Zero);
    return res.ToArray();
  }

  public static IntPtr ChildByClass(IntPtr root, string cls) {
    IntPtr found = IntPtr.Zero;
    EnumChildWindows(root, delegate(IntPtr h, IntPtr p) {
      var c = new StringBuilder(256); GetClassNameW(h, c, 256);
      if (c.ToString() == cls) { found = h; return false; }
      return true;
    }, IntPtr.Zero);
    return found;
  }
}
"@

# ---- ① 选窗：fail closed ---------------------------------------------------- #
$deadline = (Get-Date).AddSeconds($WaitSecs)
$shell = [IntPtr]::Zero
$seen = ''
while ($true) {
    $cands = [P6]::Matching($TitleLike, $ProcId)
    $fits = @()
    $why = @()
    foreach ($h in $cands) {
        $counts = New-Object int[] 2
        $fp = [P6]::Fingerprint($h, $counts)
        if ($fp -eq 1) { $fits += $h }
        elseif ($fp -eq -1) { $why += ("0x{0:X}:no-Button" -f $h.ToInt64()) }
        else { $why += ("0x{0:X}:no-Edit" -f $h.ToInt64()) }
    }
    $seen = "matched=$($cands.Count) fit=$($fits.Count)"
    if ($fits.Count -eq 1) { $shell = $fits[0]; break }
    if ($fits.Count -gt 1) {
        Write-Output "ERR ambiguous-window: $($fits.Count) candidates carry both Button and Edit ($seen)"
        exit 1
    }
    if ((Get-Date) -ge $deadline) { break }
    Start-Sleep -Milliseconds 500
}
if ($shell -eq [IntPtr]::Zero) {
    Write-Output "ERR no-window: title~'$TitleLike' pid=$ProcId $seen rejected=[$($why -join ' ')]"
    exit 1
}

Write-Output ("window=0x{0:X}  {1}" -f $shell.ToInt64(), $seen)

$before = [P6]::Title($shell)
Write-Output "before=[$before]"

if ($Assertion -eq 'children') {
    foreach ($row in [P6]::Children($shell)) {
        $parts = $row -split '\|', 3
        Write-Output ("child=0x{0:X} class={1} text=[{2}]" -f [int64]$parts[0], $parts[1], $parts[2])
    }
    Write-Output "after=[$before]"
    Write-Output 'verdict=UNCHANGED'
    exit 0
}

function Send-One([string]$which) {
    switch ($which) {
        'title' { }
        'button' {
            $btn = [P6]::ChildByClass($shell, 'Button')
            if ($btn -eq [IntPtr]::Zero) { Write-Output 'ERR no Button child'; exit 1 }
            [void][P6]::SendMessageW($btn, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero)   # BM_CLICK
            Write-Output ("sent=BM_CLICK to Button 0x{0:X}" -f $btn.ToInt64())
        }
        'key' {
            $edit = [P6]::ChildByClass($shell, 'Edit')
            if ($edit -eq [IntPtr]::Zero) { Write-Output 'ERR no Edit child'; exit 1 }
            [void][P6]::SendMessageW($edit, 0x0100, [IntPtr]0x0D, [IntPtr]::Zero)    # WM_KEYDOWN VK_RETURN
            Write-Output ("sent=WM_KEYDOWN VK_RETURN to Edit 0x{0:X}" -f $edit.ToInt64())
        }
        'text' {
            $edit = [P6]::ChildByClass($shell, 'Edit')
            if ($edit -eq [IntPtr]::Zero) { Write-Output 'ERR no Edit child'; exit 1 }
            [void][P6]::SendMessageStr($edit, 0x000C, [IntPtr]::Zero, $Payload)      # WM_SETTEXT
            Write-Output ("sent=WM_SETTEXT '$Payload' to Edit 0x{0:X}" -f $edit.ToInt64())
        }
        # ②a 坐标消息发给**按钮自己的 HWND**。
        'coord-button' {
            $btn = [P6]::ChildByClass($shell, 'Button')
            if ($btn -eq [IntPtr]::Zero) { Write-Output 'ERR no Button child'; exit 1 }
            $r = New-Object P6+RECT; [void][P6]::GetClientRect($btn, [ref]$r)
            $x = [int](($r.Right - $r.Left) / 2); $y = [int](($r.Bottom - $r.Top) / 2)
            $lp = [IntPtr](($y -shl 16) -bor ($x -band 0xFFFF))
            [void][P6]::PostMessageW($btn, 0x0201, [IntPtr]1, $lp)                   # WM_LBUTTONDOWN (MK_LBUTTON)
            [void][P6]::PostMessageW($btn, 0x0202, [IntPtr]::Zero, $lp)              # WM_LBUTTONUP
            Write-Output ("sent=coord-click ($x,$y) to Button 0x{0:X}" -f $btn.ToInt64())
        }
        # ②b 对照组：**同一坐标、同一消息**，只把收件人换成顶层 Shell。期望无效。
        #     PostMessage 不做命中测试：顶层窗收到落在子控件区域的鼠标消息不会转给子控件。
        #     ⇒ 这条与 ②a 的差异，正是「决定成败的是寻址」的证据。
        'coord-shell-at-button' {
            $btn = [P6]::ChildByClass($shell, 'Button')
            if ($btn -eq [IntPtr]::Zero) { Write-Output 'ERR no Button child'; exit 1 }
            $br = New-Object P6+RECT; [void][P6]::GetWindowRect($btn, [ref]$br)
            $x = [int](($br.Left + $br.Right) / 2); $y = [int](($br.Top + $br.Bottom) / 2)
            $lp = [IntPtr](($y -shl 16) -bor ($x -band 0xFFFF))
            [void][P6]::PostMessageW($shell, 0x0201, [IntPtr]1, $lp)
            [void][P6]::PostMessageW($shell, 0x0202, [IntPtr]::Zero, $lp)
            Write-Output "sent=coord-click ($x,$y) to Shell (at Button screen center, NOT Button HWND)"
        }
        # ⑥ 坐标点空白 —— 期望无变化。
        'coord-blank' {
            $r = New-Object P6+RECT; [void][P6]::GetClientRect($shell, [ref]$r)
            $x = 5; $y = 5
            $lp = [IntPtr](($y -shl 16) -bor ($x -band 0xFFFF))
            [void][P6]::PostMessageW($shell, 0x0201, [IntPtr]1, $lp)
            [void][P6]::PostMessageW($shell, 0x0202, [IntPtr]::Zero, $lp)
            Write-Output ("sent=coord-click ($x,$y) to Shell blank (client {0}x{1})" -f $r.Right, $r.Bottom)
        }
    }
}

$attempts = 0
$after = $before
while ($true) {
    $attempts++
    Send-One $Assertion
    Start-Sleep -Milliseconds $SettleMs
    $after = [P6]::Title($shell)
    if ($after -ne $before) { break }
    if ($attempts -ge $Retries) { break }
}
Write-Output "attempts=$attempts"
Write-Output "after=[$after]"
if ($after -eq $before) { Write-Output 'verdict=UNCHANGED' } else { Write-Output 'verdict=CHANGED' }
