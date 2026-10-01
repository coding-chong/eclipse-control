param(
    [Parameter(Mandatory = $true)][string]$TitleLike,
    [string]$Class = '',
    [int]$ProcId = 0
)
# Find a visible top-level window whose title contains $TitleLike (optionally
# matching $Class, optionally limited to process $ProcId) and post WM_CLOSE to it.
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class WinClose {
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool PostMessageW(IntPtr h, uint msg, IntPtr w, IntPtr l);
  public static List<string> Close(string like, string cls, uint only) {
    var hits = new List<string>();
    EnumWindows(delegate(IntPtr h, IntPtr p) {
      if (!IsWindowVisible(h)) return true;
      uint pid; GetWindowThreadProcessId(h, out pid);
      if (only != 0 && pid != only) return true;
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      var c = new StringBuilder(256); GetClassNameW(h, c, 256);
      if (t.ToString().IndexOf(like, StringComparison.OrdinalIgnoreCase) < 0) return true;
      if (cls.Length != 0 && c.ToString() != cls) return true;
      bool ok = PostMessageW(h, 0x0010 /*WM_CLOSE*/, IntPtr.Zero, IntPtr.Zero);
      hits.Add(string.Format("pid={0} hwnd=0x{1:X} class={2} title={3} WM_CLOSE posted={4}",
        pid, h.ToInt64(), c.ToString(), t.ToString(), ok));
      return true;
    }, IntPtr.Zero);
    return hits;
  }
}
"@
$r = [WinClose]::Close($TitleLike, $Class, [uint32]$ProcId)
if ($r.Count -eq 0) {
    # Non-zero on "nothing matched": the caller must not read this as "closed".
    # `win-click-button.ps1` already behaved this way; this one returned 0, so a
    # script doing `win-close; if rc==0 then assume closed` would silently believe
    # a stubborn dialog was gone.  Measured 2026-10-01.
    Write-Output "no window matched '$TitleLike'"
    exit 1
}
$r | ForEach-Object { Write-Output $_ }
