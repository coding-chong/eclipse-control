param(
    [Parameter(Mandatory = $true)][string]$TitleLike,
    [string]$Text = '',
    [switch]$ListOnly,
    # 0 = match any process.  Set it whenever more than one instance of the IDE can
    # be on screen: two workbenches each showing "Reset Perspective" are otherwise
    # indistinguishable here, and this tool *presses buttons*.
    [int]$ProcId = 0
)
# Find a top-level window by title, enumerate its child windows (class + text +
# rect), and optionally click the child button whose text matches $Text via
# BM_CLICK -- i.e. press the button the way a user would, without moving the
# mouse.  Prints everything it saw.
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class Btn {
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, EnumProc cb, IntPtr p);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern IntPtr SendMessageW(IntPtr h, uint msg, IntPtr wp, IntPtr lp);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public static IntPtr Dialog = IntPtr.Zero;
  public static uint Only = 0;
  public static IntPtr Find(string like) {
    Dialog = IntPtr.Zero;
    EnumWindows(delegate(IntPtr h, IntPtr p) {
      if (Dialog != IntPtr.Zero) return true;
      if (!IsWindowVisible(h)) return true;
      if (Only != 0) { uint pid; GetWindowThreadProcessId(h, out pid); if (pid != Only) return true; }
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      if (t.ToString().IndexOf(like, StringComparison.OrdinalIgnoreCase) < 0) return true;
      Dialog = h; return true;
    }, IntPtr.Zero);
    return Dialog;
  }
  public static List<string> Children() {
    var outv = new List<string>();
    if (Dialog == IntPtr.Zero) return outv;
    EnumChildWindows(Dialog, delegate(IntPtr h, IntPtr p) {
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      var c = new StringBuilder(256); GetClassNameW(h, c, 256);
      RECT r; GetWindowRect(h, out r);
      outv.Add(string.Format("hwnd=0x{0:X} class={1} vis={2} text=\"{3}\" rect={4},{5},{6},{7}",
        (long)h, c, IsWindowVisible(h), t, r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top));
      return true;
    }, IntPtr.Zero);
    return outv;
  }
  // Collect *every* visible Button whose text contains `want`.  Nothing is clicked
  // here: the old version sent BM_CLICK to the first match and stopped enumerating,
  // so a second identically-labelled Button was invisible to it and a zero-match
  // call was indistinguishable from a hit one (design-project.md section 18.3:
  // text addressing must resolve to exactly one control).
  public static List<IntPtr> MatchButtons(string want) {
    var hits = new List<IntPtr>();
    EnumChildWindows(Dialog, delegate(IntPtr h, IntPtr p) {
      if (!IsWindowVisible(h)) return true;
      var c = new StringBuilder(256); GetClassNameW(h, c, 256);
      if (c.ToString() != "Button") return true;
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      if (t.ToString().IndexOf(want, StringComparison.OrdinalIgnoreCase) < 0) return true;
      hits.Add(h);
      return true;
    }, IntPtr.Zero);
    return hits;
  }
  public static string TextOf(IntPtr h) {
    var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
    return t.ToString();
  }
  public static void Click(IntPtr h) {
    SendMessageW(h, 0x00F5 /*BM_CLICK*/, IntPtr.Zero, IntPtr.Zero);
  }
}
"@
[void][Btn]::SetProcessDPIAware()
[Btn]::Only = [uint32]$ProcId
$d = [Btn]::Find($TitleLike)
if ($d -eq [IntPtr]::Zero) { Write-Output "no visible window matching '$TitleLike'"; exit 1 }
Write-Output ("dialog hwnd=0x{0:X}" -f [int64]$d)
Write-Output "-- child windows --"
[Btn]::Children() | ForEach-Object { Write-Output ("  " + $_) }
if (-not $ListOnly -and $Text -ne '') {
    Write-Output "-- click --"
    # design-project.md section 18.3: text addressing must resolve to exactly one
    # control.  Zero matches used to print a note and still `exit 0` (a silent
    # success, which is what A14 forbids); several matches used to click the first
    # one (a silent pick, which is how two same-labelled Buttons get confused).
    $hits = [Btn]::MatchButtons($Text)
    if ($hits.Count -eq 0) {
        Write-Output "ERR no visible Button matching '$Text'"
        exit 1
    }
    if ($hits.Count -gt 1) {
        Write-Output ("ERR ambiguous: {0} visible Buttons match '{1}' (text addressing must be unique)" -f $hits.Count, $Text)
        $hits | ForEach-Object { Write-Output ("  candidate hwnd=0x{0:X} class=Button text=""{1}""" -f ([int64]$_), [Btn]::TextOf($_)) }
        exit 1
    }
    [Btn]::Click($hits[0])
    Write-Output ("  BM_CLICK sent to hwnd=0x{0:X} text=""{1}""" -f ([int64]$hits[0]), [Btn]::TextOf($hits[0]))
}
exit 0
