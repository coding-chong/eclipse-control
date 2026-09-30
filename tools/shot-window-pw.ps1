param(
    [Parameter(Mandatory = $true)][string]$TitleLike,
    [Parameter(Mandatory = $true)][string]$Out,
    [int]$Flags = 2          # 2 = PW_RENDERFULLCONTENT
)
# Capture a window by asking IT for its own bitmap (PrintWindow), instead of
# copying screen pixels.  Immune to occlusion and to DPI virtualisation -- the
# two failure modes that broke the CopyFromScreen variant.
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class PW {
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  // Must run BEFORE any rect query: without it Windows virtualises coordinates
  // (this box is ~2.1x scaled, so rects come back ~2x too small and PrintWindow
  // renders into an undersized bitmap -> the dialog gets clipped).
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public static IntPtr Find(string like) {
    IntPtr found = IntPtr.Zero;
    EnumWindows(delegate(IntPtr h, IntPtr p) {
      if (found != IntPtr.Zero) return true;
      if (!IsWindowVisible(h)) return true;
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      if (t.ToString().IndexOf(like, StringComparison.OrdinalIgnoreCase) < 0) return true;
      found = h; return true;
    }, IntPtr.Zero);
    return found;
  }
  public static int[] Rect(IntPtr h) {
    RECT r; GetWindowRect(h, out r);
    return new int[] { r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top };
  }
  public static bool Shot(IntPtr h, IntPtr hdc, uint flags) { return PrintWindow(h, hdc, flags); }
}
"@
[void][PW]::SetProcessDPIAware()
$hwnd = [PW]::Find($TitleLike)
if ($hwnd -eq [IntPtr]::Zero) { Write-Output "no visible window matching '$TitleLike'"; exit 1 }
$r = [PW]::Rect($hwnd)
$w = [int]$r[2]; $ht = [int]$r[3]
if ($w -le 0 -or $ht -le 0) { Write-Output "empty rect for '$TitleLike'"; exit 1 }
$bmp = New-Object System.Drawing.Bitmap($w, $ht)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
$ok = [PW]::Shot($hwnd, $hdc, [uint32]$Flags)
$g.ReleaseHdc($hdc)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output "PrintWindow ok=$ok hwnd=0x$('{0:X}' -f [int64]$hwnd) rect=$($r -join ',') size=${w}x${ht} -> $Out"
