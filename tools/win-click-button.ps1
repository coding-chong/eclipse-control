param(
    [Parameter(Mandatory = $true)][string]$TitleLike,
    [string]$Text = '',
    [switch]$ListOnly
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
  [DllImport("user32.dll")] public static extern IntPtr SendMessageW(IntPtr h, uint msg, IntPtr wp, IntPtr lp);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public static IntPtr Dialog = IntPtr.Zero;
  public static IntPtr Find(string like) {
    Dialog = IntPtr.Zero;
    EnumWindows(delegate(IntPtr h, IntPtr p) {
      if (Dialog != IntPtr.Zero) return true;
      if (!IsWindowVisible(h)) return true;
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
  public static string ClickByText(string want) {
    string hit = null;
    EnumChildWindows(Dialog, delegate(IntPtr h, IntPtr p) {
      if (hit != null || !IsWindowVisible(h)) return true;
      var c = new StringBuilder(256); GetClassNameW(h, c, 256);
      if (c.ToString() != "Button") return true;
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      if (t.ToString().IndexOf(want, StringComparison.OrdinalIgnoreCase) < 0) return true;
      SendMessageW(h, 0x00F5 /*BM_CLICK*/, IntPtr.Zero, IntPtr.Zero);
      hit = string.Format("BM_CLICK sent to hwnd=0x{0:X} text=\"{1}\"", (long)h, t);
      return true;
    }, IntPtr.Zero);
    return hit;
  }
}
"@
[void][Btn]::SetProcessDPIAware()
$d = [Btn]::Find($TitleLike)
if ($d -eq [IntPtr]::Zero) { Write-Output "no visible window matching '$TitleLike'"; exit 1 }
Write-Output ("dialog hwnd=0x{0:X}" -f [int64]$d)
Write-Output "-- child windows --"
[Btn]::Children() | ForEach-Object { Write-Output ("  " + $_) }
if (-not $ListOnly -and $Text -ne '') {
    Write-Output "-- click --"
    $r = [Btn]::ClickByText($Text)
    if ($r) { Write-Output ("  " + $r) } else { Write-Output ("  no visible Button matching '$Text'") }
}
