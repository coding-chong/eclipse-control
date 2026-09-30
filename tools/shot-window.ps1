param(
    [Parameter(Mandatory = $true)][string]$TitleLike,
    [Parameter(Mandatory = $true)][string]$Out
)
# Find a visible top-level window whose title contains $TitleLike, capture its
# rectangle from the screen and save it as PNG.  Self-contained: no browser, no
# MCP, no focus stealing.
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class Shot {
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  public static string FindRect(string like) {
    string found = null;
    EnumWindows(delegate(IntPtr h, IntPtr p) {
      if (found != null || !IsWindowVisible(h)) return true;
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      if (t.ToString().IndexOf(like, StringComparison.OrdinalIgnoreCase) < 0) return true;
      RECT r; GetWindowRect(h, out r);
      found = r.Left + "," + r.Top + "," + (r.Right - r.Left) + "," + (r.Bottom - r.Top);
      return true;
    }, IntPtr.Zero);
    return found;
  }
}
"@
$rect = [Shot]::FindRect($TitleLike)
if (-not $rect) { Write-Output "no visible window matching '$TitleLike'"; exit 1 }
$parts = $rect.Split(',')
$l = [int]$parts[0]; $t = [int]$parts[1]; $w = [int]$parts[2]; $h = [int]$parts[3]
if ($w -le 0 -or $h -le 0) { Write-Output "window has empty rect: $rect"; exit 1 }
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($l, $t, 0, 0, (New-Object System.Drawing.Size($w, $h)))
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output "saved $Out  rect=$rect  size=${w}x${h}"
