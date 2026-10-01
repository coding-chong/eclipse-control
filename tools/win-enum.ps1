param(
    # 0 = enumerate every process's top-level windows.
    # Named `-ProcId` to match win-close / win-click-button / shot-window-pw;
    # `-Target` still works via the alias (older notes and recipes use it).
    [Alias('Target')][int]$ProcId = 0,
    [string]$TitleLike = '',
    # Exact Win32 class match.  `-Class "#32770"` is how the docs say "dialogs only";
    # the class really is exact here (WindowClass names carry no wildcards).
    [string]$Class = ''
)
# Enumerate top-level Win32 windows (optionally for one PID) and print
# pid / hwnd / visible / enabled / class / title.  Used to capture a modal
# dialog that blocks an SWT UI thread.
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class WinEnum2 {
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, uint cmd);
  public static List<string> Dump(uint target) {
    var res = new List<string>();
    EnumWindows(delegate(IntPtr h, IntPtr p) {
      uint pid; GetWindowThreadProcessId(h, out pid);
      if (target != 0 && pid != target) return true;
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      var c = new StringBuilder(256); GetClassNameW(h, c, 256);
      IntPtr owner = GetWindow(h, 4 /*GW_OWNER*/);
      res.Add(string.Format("pid={0} hwnd=0x{1:X} vis={2} en={3} owner=0x{4:X} class={5} title={6}",
        pid, h.ToInt64(), IsWindowVisible(h), IsWindowEnabled(h), owner.ToInt64(), c.ToString(), t.ToString()));
      return true;
    }, IntPtr.Zero);
    return res;
  }
}
"@
[WinEnum2]::Dump([uint32]$ProcId) | Where-Object {
    ($TitleLike -eq '' -or $_ -like "*$TitleLike*") -and
    ($Class -eq '' -or $_ -like "* class=$Class *")
} | ForEach-Object { Write-Output $_ }
