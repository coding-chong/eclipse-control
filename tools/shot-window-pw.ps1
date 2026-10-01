param(
    [Parameter(Mandatory = $true)][string]$TitleLike,
    [Parameter(Mandatory = $true)][string]$Out,
    [int]$Flags = 2,                 # 2 = PW_RENDERFULLCONTENT
    [int]$ProcId = 0,                # 0 = any process
    [string]$Class = ""              # "" = any class
)
# Capture a window by asking IT for its own bitmap (PrintWindow), instead of
# copying screen pixels.  Immune to occlusion and to DPI virtualisation -- the
# two failure modes that broke the CopyFromScreen variant.
#
# Two safeguards, both modelled on `open-computer-use-fixed`
# (`apps/OpenComputerUseWindows/runtime.ps1`, `Capture-WindowPngBase64`), whose
# behaviour was measured against ours on 2026-10-01:
#
#   * **blank detection + fail closed.**  `PrintWindow` returns TRUE even when it
#     painted nothing.  Measured on a GPU-composited Chromium window (Edge,
#     2744x1828): `flags=0` produced a bitmap that was **75.5% zero bytes with 2
#     distinct colours in a 3000-pixel sample** -- i.e. essentially black -- and
#     the old script still printed `ok=True` and wrote the PNG.  A blank shot is
#     worse than no shot: it "proves" the window had nothing in it.
#   * **one retry with the other flag word.**  `PW_RENDERFULLCONTENT` (2) is what
#     paints GPU-composited content; `0` is what painted the SWT modal legibly.
#     Whichever was asked for, the other gets one attempt before failing.
#
# `-ProcId` / `-Class` exist because titles are not unique: two IDE instances can
# show the same title, and `ui.open` puts a file name into the *shell* title.
#
# The C# block stays P/Invoke-only on purpose: `Add-Type -TypeDefinition` cannot
# see `System.Drawing` types unless the assembly is passed by hand, so all bitmap
# work is done in PowerShell below (same split as the reference implementation).
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
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  // Must run BEFORE any rect query: without it Windows virtualises coordinates
  // (this box is ~2.1x scaled, so rects come back ~2x too small and PrintWindow
  // renders into an undersized bitmap -> the dialog gets clipped).
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public static IntPtr Find(string like, uint wantPid, string wantClass) {
    IntPtr found = IntPtr.Zero;
    EnumWindows(delegate(IntPtr h, IntPtr p) {
      if (found != IntPtr.Zero) return true;
      if (!IsWindowVisible(h)) return true;
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      if (t.ToString().IndexOf(like, StringComparison.OrdinalIgnoreCase) < 0) return true;
      if (wantClass.Length > 0) {
        var c = new StringBuilder(512); GetClassNameW(h, c, 512);
        if (!String.Equals(c.ToString(), wantClass, StringComparison.OrdinalIgnoreCase)) return true;
      }
      if (wantPid != 0) {
        uint pid; GetWindowThreadProcessId(h, out pid);
        if (pid != wantPid) return true;
      }
      found = h; return true;
    }, IntPtr.Zero);
    return found;
  }
  public static int[] Rect(IntPtr h) {
    RECT r; GetWindowRect(h, out r);
    return new int[] { r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top };
  }
  public static bool Shot(IntPtr h, IntPtr hdc, uint flags) { return PrintWindow(h, hdc, flags); }
  public static uint PidOf(IntPtr h) { uint pid; GetWindowThreadProcessId(h, out pid); return pid; }
  public static string ClassOf(IntPtr h) { var c = new StringBuilder(512); GetClassNameW(h, c, 512); return c.ToString(); }
  // Returns EVERY visible top-level window that matches.  "First match wins" was
  // wrong: the GS32_Studio launcher console is titled "...\GS32_Studio_v1.2.5.2\
  // GS32_Studio_v1.2.5.2\GS32.exe" -- it *contains* "GS32_Studio", it belongs to
  // the same pid (so -ProcId cannot separate them) and it comes first in
  // EnumWindows order.  Measured 2026-10-01: the main window was captured as a
  // 800x500 black console instead of the 2048x1536 workbench, and the old script
  // reported ok=True for it.
  public static IntPtr[] FindAll(string like, uint wantPid, string wantClass) {
    var hits = new System.Collections.Generic.List<IntPtr>();
    EnumWindows(delegate(IntPtr h, IntPtr p) {
      if (!IsWindowVisible(h)) return true;
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      if (t.ToString().IndexOf(like, StringComparison.OrdinalIgnoreCase) < 0) return true;
      if (wantClass.Length > 0) {
        if (!String.Equals(ClassOf(h), wantClass, StringComparison.OrdinalIgnoreCase)) return true;
      }
      if (wantPid != 0) {
        uint pid; GetWindowThreadProcessId(h, out pid);
        if (pid != wantPid) return true;
      }
      hits.Add(h); return true;
    }, IntPtr.Zero);
    return hits.ToArray();
  }
  public static long Area(IntPtr h) {
    RECT r; GetWindowRect(h, out r);
    return (long)(r.Right - r.Left) * (long)(r.Bottom - r.Top);
  }
}
"@
[void][PW]::SetProcessDPIAware()
$cands = @([PW]::FindAll($TitleLike, [uint32]$ProcId, $Class))
if ($cands.Count -eq 0) {
    $extra = ""
    if ($ProcId -ne 0) { $extra += " pid=$ProcId" }
    if ($Class -ne "") { $extra += " class=$Class" }
    Write-Output "no visible window matching '$TitleLike'$extra"
    exit 1
}
# Largest wins.  Several distinct top-level windows can contain the same title --
# e.g. the launcher console shares the workbench's pid -- and the app's main
# window is by far the biggest of them.
$hwnd = $cands[0]
$best = -1
foreach ($c in $cands) { $a = [PW]::Area($c); if ($a -gt $best) { $best = $a; $hwnd = $c } }
$pickNote = ""
if ($cands.Count -gt 1) {
    $alts = ($cands | ForEach-Object { "$([PW]::ClassOf($_)):$([PW]::Area($_))" }) -join ", "
    $pickNote = " (picked largest of $($cands.Count) matching: $alts)"
}
$r = [PW]::Rect($hwnd)
$w = [int]$r[2]; $ht = [int]$r[3]
$desc = "hwnd=0x$('{0:X}' -f [int64]$hwnd) pid=$([PW]::PidOf($hwnd)) class=$([PW]::ClassOf($hwnd)) rect=$($r -join ',') size=${w}x${ht}$pickNote"
# A minimized window still reports itself visible, and GetWindowRect hands back the
# icon-position sentinel (-32000,-32000) with a tiny restored size.  Measured
# 2026-10-01: `-TitleLike "GS32_Studio"` matched exactly that and produced a
# 353x56 image that is useless as evidence -- yet the old script called it ok.
if ([PW]::IsIconic($hwnd) -or [int]$r[0] -le -30000 -or [int]$r[1] -le -30000) {
    [Console]::Error.WriteLine("target window is minimized/off-screen for '$TitleLike' $desc minimized=$([PW]::IsIconic($hwnd)). Not writing $Out -- restore the window first; a minimized window has no meaningful pixels.")
    Write-Output "minimized: '$TitleLike' $desc"
    exit 1
}
if ($w -le 0 -or $ht -le 0) { Write-Output "empty rect for '$TitleLike'"; exit 1 }

# A real window is never 100% pure black; a blank PrintWindow result always is.
# Sampling ~20k pixels is enough to tell the two apart, and keeps this O(1) in
# window size instead of a 5M-iteration PowerShell loop.
function Test-VisiblePixels($bmp) {
    if ($bmp.PixelFormat -ne [System.Drawing.Imaging.PixelFormat]::Format32bppArgb) { return $true }
    $rect = New-Object System.Drawing.Rectangle(0, 0, $bmp.Width, $bmp.Height)
    $data = $bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly,
                          [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    try {
        $nbytes = [Math]::Abs($data.Stride) * $bmp.Height
        $buf = New-Object byte[] $nbytes
        [System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $buf, 0, $nbytes)
    } finally { $bmp.UnlockBits($data) }
    $step = [int]($nbytes / 80000)
    $step = $step - ($step % 4)
    if ($step -lt 4) { $step = 4 }
    for ($i = 0; $i + 3 -lt $nbytes; $i += $step) {
        if ($buf[$i] -ne 0 -or $buf[$i + 1] -ne 0 -or $buf[$i + 2] -ne 0) { return $true }
    }
    return $false
}

$bmp = New-Object System.Drawing.Bitmap($w, $ht)
$g = [System.Drawing.Graphics]::FromImage($bmp)
function Invoke-Shot([int]$flag) {
    $g.Clear([System.Drawing.Color]::Black)      # reset before repainting
    $hdc = $g.GetHdc()
    try { return [PW]::Shot($hwnd, $hdc, [uint32]$flag) } finally { $g.ReleaseHdc($hdc) }
}

$used = $Flags
$ok = Invoke-Shot $Flags
$blank = -not (Test-VisiblePixels $bmp)
$retried = $false
if ($blank) {
    $other = 0; if ($Flags -eq 0) { $other = 2 }
    $retried = $true
    $ok2 = Invoke-Shot $other
    $ok = ($ok -or $ok2) -and (Test-VisiblePixels $bmp)
    $blank = -not (Test-VisiblePixels $bmp)
    $used = $other
}
if ($blank) {
    $g.Dispose(); $bmp.Dispose()
    [Console]::Error.WriteLine("PrintWindow painted NOTHING (blank/black bitmap) for '$TitleLike' $desc; tried flags=$Flags and $used. Not writing $Out -- a blank shot would falsely 'prove' the window was empty.")
    Write-Output "blank: '$TitleLike' $desc flags=$Flags,$used"
    exit 1
}
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
$note = if ($retried) { " (blank with flags=$Flags -> retried flags=$used)" } else { "" }
Write-Output "PrintWindow ok=$ok$note $desc -> $Out"
