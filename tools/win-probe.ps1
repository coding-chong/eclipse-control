<#
win-probe.ps1 -- ONE pwsh invocation that yields BOTH a window snapshot and a
frame of pixels (R8: the ~700 ms process start is the expensive part, so the
shadow layer pays for it once per action instead of twice).

stdout is a SINGLE line of JSON and nothing else.  Every diagnostic goes to
stderr, so a caller can parse stdout without guessing which line is the payload.

    { "tool": "win-probe", "ok": true, "reason": null, "pid": 5272,
      "class_filter": ["SWT_Window0", "#32770"],
      "count": 3, "windows": [ {pid,hwnd,class,title,vis,en,rect,area}, ... ],
      "new": ["0x1A0C3E"],
      "candidates": [ {hwnd,class,title,area,new} ],
      "rejected":   [ {hwnd,class,title,reason} ],
      "target": {class,hwnd,title,bounds,pid,en,area},
      "out": "...png", "flags": 2, "bytes": 14057, "retried": false }

`windows` lists the **target pid's visible top-level windows** (the tool
enumerates every process's top-level windows, then scopes the report to
`-ProcId`).  That scoping is deliberate: the window-set delta is only meaningful
for the IDE instance under test, and a whole-desktop list would flip on any
other application's tooltip or popup.

WHY -Class IS MANDATORY AND INDEPENDENT OF -TitleLike
-----------------------------------------------------
Measured 2026-10-01: `shot-window-pw.ps1 -TitleLike ""` fails outright
(`rc=1`, "cannot bind an empty string to parameter 'TitleLike'"), and matching
on the *title* is unsafe anyway -- the GS32_Studio launcher console shares the
workbench's pid and its title also contains "GS32_Studio".  Selection here is by
**class identity** first; `-TitleLike` only narrows an already-valid candidate
set.  `-ProcId` + `-Class` alone must be sufficient.

WHY fail closed
---------------
`PrintWindow` will happily return TRUE and a 35 KB image for the *console*
(measured), and a blank bitmap for a window it could not paint.  A frame from a
window nobody selected -- or a blank one -- is worse than no frame at all: it
will later be read as "this is what the screen looked like".  So: no legal
candidate, a minimized target, or a blank paint each end in rc=1 and **no file**.
`SWT_WindowShadow0` (Key Assist's only window-level trace) is deliberately NOT a
candidate: rejecting it falls back to the workbench, which still yields a real
frame -- that is fail-SAFE, not a misconfiguration.

WHY the aux-title exclusion
---------------------------
A single pid carries THREE top-level `SWT_Window0` windows (workbench,
`PartRenderingEngine's limbo`, `SWT_Window_GS32_Studio`); today the latter two
are separated by `vis=False`, but that is a second condition, not the same
guarantee.  The title exclusion is that second condition, and the chosen
`title` is reported so a mis-selection is auditable rather than invisible.

Safeguards inherited from shot-window-pw.ps1 (same repairs, same reasons):
blank detection (a real window is never 100% pure black) with ONE retry under
the other flag word, and the minimized / off-screen guard (a minimized window
still reports itself visible and hands back the -32000 sentinel rect).
#>
param(
    [Parameter(Mandatory = $true)][string]$Out,
    # Exact Win32 class name(s), comma separated -- `"SWT_Window0,#32770"`.
    [Parameter(Mandatory = $true)][string]$Class,
    [Parameter(Mandatory = $true)][int]$ProcId,
    [int]$Flags = 2,                 # 2 = PW_RENDERFULLCONTENT
    # Optional narrowing only; NEVER required (an empty string is rejected by
    # PowerShell's parameter binder, which is exactly how the old tool broke).
    [string]$TitleLike = '',
    # Comma-separated hwnd list from the PREVIOUS probe ("0x570600,0x230A60").
    # A candidate absent from it is "new" and wins over a bigger old window:
    # when an action pops a dialog, the dialog IS the story.
    [string]$Prev = ''
)

$ErrorActionPreference = 'Stop'
# Redirected stdout is encoded with the *console* code page otherwise (GBK on
# this box), which mangles any non-ASCII window title inside the JSON.
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

function Write-Result($obj, [int]$rc) {
    $json = $obj | ConvertTo-Json -Depth 6 -Compress
    [Console]::Out.WriteLine($json)
    exit $rc
}

#: Classes that must never be selected, whatever -Class says.  Every one of them
#: was observed on a real GS32_Studio instance (2026-10-01) and each is either a
#: console/host window or a decoration of a real window.
$REJECT = @('ConsoleWindowClass', 'PseudoConsoleWindow', 'CASCADIA_HOSTING_WINDOW_CLASS',
            'Shell_TrayWnd', 'Progman', 'tooltips_class32', 'SWT_WindowShadow0',
            'SysShadow', 'Internet Explorer_Hidden')
#: Top-level SWT_Window0 windows that are NOT the workbench (measured titles).
$AUX_TITLE = @("PartRenderingEngine's limbo", 'SWT_Window_GS32_Studio')

Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class WinProbe {
  public delegate bool EnumProc(IntPtr h, IntPtr p);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  // Must run BEFORE any rect query: without it Windows virtualises coordinates
  // (this box is ~2.1x scaled, so rects come back ~2x too small and PrintWindow
  // renders into an undersized bitmap -> the dialog gets clipped).
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public class Win {
    public long Hwnd;
    public uint Pid;
    public string Cls = "";
    public string Title = "";
    public bool Vis;
    public bool En;
    public int X, Y, W, H;
    public long Area;
  }
  public static List<Win> All() {
    var res = new List<Win>();
    EnumWindows(delegate(IntPtr h, IntPtr p) {
      var w = new Win();
      w.Hwnd = h.ToInt64();
      uint pid; GetWindowThreadProcessId(h, out pid); w.Pid = pid;
      var c = new StringBuilder(512); GetClassNameW(h, c, 512); w.Cls = c.ToString();
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512); w.Title = t.ToString();
      w.Vis = IsWindowVisible(h);
      w.En = IsWindowEnabled(h);
      RECT r; GetWindowRect(h, out r);
      w.X = r.Left; w.Y = r.Top; w.W = r.Right - r.Left; w.H = r.Bottom - r.Top;
      w.Area = (long)w.W * (long)w.H;
      res.Add(w);
      return true;
    }, IntPtr.Zero);
    return res;
  }
  public static bool Shot(IntPtr h, IntPtr hdc, uint flags) { return PrintWindow(h, hdc, flags); }
  public static bool Minimized(IntPtr h) { return IsIconic(h); }
}
"@
[void][WinProbe]::SetProcessDPIAware()

function Get-Hwnd([long]$raw) { return [IntPtr][long]$raw }
function Get-Hex($raw) { return ('0x{0:X}' -f [int64]$raw) }

function New-WinObj($w) {
    return [ordered]@{
        pid   = [int]$w.Pid
        hwnd  = (Get-Hex $w.Hwnd)
        class = $w.Cls
        title = $w.Title
        vis   = [bool]$w.Vis
        en    = [bool]$w.En
        rect  = @([int]$w.X, [int]$w.Y, [int]$w.W, [int]$w.H)
        area  = [int64]$w.Area
    }
}
function New-CandObj($w, [bool]$isNew) {
    return [ordered]@{
        hwnd  = (Get-Hex $w.Hwnd)
        class = $w.Cls
        title = $w.Title
        area  = [int64]$w.Area
        new   = [bool]$isNew
    }
}

$want = @()
foreach ($piece in ($Class -split ',')) {
    $name = $piece.Trim()
    if ($name -ne '') { $want += $name }
}

$rejectList = @($REJECT | ForEach-Object { $_.ToLower() })
$auxList = @($AUX_TITLE | ForEach-Object { $_.ToLower() })

$base = [ordered]@{
    tool         = 'win-probe'
    ok           = $false
    reason       = $null
    pid          = $ProcId
    class_filter = @($want)
    title_like   = $TitleLike
    count        = 0
    windows      = @()
    prev         = @()
    new          = @()
    candidates   = @()
    rejected     = @()
    target       = $null
    out          = $Out
    flags        = $Flags
    bytes        = 0
    retried      = $false
    note         = ''
}

if ($want.Count -eq 0) {
    $base.reason = 'bad-class'
    $base.note = '-Class must name at least one exact Win32 class'
    Write-Result $base 1
}
# `-ProcId 0` would mean "any process" -- a frame of some other application's
# dialog stored as "the IDE's screen" is exactly the false evidence R11 forbids.
if ($ProcId -le 0) {
    $base.reason = 'bad-pid'
    $base.note = "-ProcId must be the target instance's pid, got $ProcId"
    [Console]::Error.WriteLine("win-probe: $($base.note); nothing written to $Out")
    Write-Result $base 1
}

$mine = @([WinProbe]::All() | Where-Object { [int]$_.Pid -eq $ProcId })
$visible = @($mine | Where-Object { $_.Vis })
$base.count = $visible.Count
$base.windows = @($visible | ForEach-Object { New-WinObj $_ })

$prevSet = @{}
foreach ($piece in ($Prev -split ',')) {
    $token = $piece.Trim()
    if ($token -ne '') { $prevSet[$token.ToUpper()] = $true }
}
$havePrev = ($prevSet.Count -gt 0)
$base.prev = @($Prev -split ',' | Where-Object { $_.Trim() -ne '' } | ForEach-Object { $_.Trim() })

$cands = @()
$rejected = @()
foreach ($w in $visible) {
    $hex = Get-Hex $w.Hwnd
    $cls = $w.Cls.ToLower()
    $title = $w.Title
    $reason = $null
    if ($rejectList -contains $cls) { $reason = 'class-rejected' }
    elseif (-not ($want | Where-Object { $_.ToLower() -eq $cls })) { $reason = 'class-not-in-whitelist' }
    elseif ($title -eq '') { $reason = 'untitled' }
    elseif ($auxList -contains $title.ToLower()) { $reason = 'aux-title' }
    elseif ($TitleLike -ne '' -and $title.ToLower().IndexOf($TitleLike.ToLower()) -lt 0) { $reason = 'title-narrowed-out' }
    if ($reason) {
        $rejected += [ordered]@{ hwnd = $hex; class = $w.Cls; title = $title; reason = $reason }
    } else {
        $cands += $w
    }
}
$base.rejected = @($rejected)
$base.candidates = @($cands | ForEach-Object { New-CandObj $_ (-not $prevSet.ContainsKey((Get-Hex $_.Hwnd).ToUpper())) })

if ($cands.Count -eq 0) {
    $base.reason = 'no-candidate'
    $base.note = ("no window for pid=$ProcId matched class=[{0}] vis=True" -f ($want -join ', '))
    [Console]::Error.WriteLine("win-probe: $($base.note); nothing written to $Out")
    Write-Result $base 1
}

$fresh = @()
if ($havePrev) {
    $fresh = @($cands | Where-Object { -not $prevSet.ContainsKey((Get-Hex $_.Hwnd).ToUpper()) })
}
$pool = if ($fresh.Count -gt 0) { $fresh } else { $cands }
$base.new = @($fresh | ForEach-Object { Get-Hex $_.Hwnd })
$pick = @($pool | Sort-Object -Property @{Expression = {$_.Area}; Descending = $true},
                                      @{Expression = {$_.Hwnd}; Descending = $false})[0]
$pickHwnd = Get-Hwnd $pick.Hwnd
$pickHex = Get-Hex $pick.Hwnd
$base.target = [ordered]@{
    class  = $pick.Cls
    hwnd   = $pickHex
    title  = $pick.Title
    bounds = ("{0},{1},{2},{3}" -f $pick.X, $pick.Y, $pick.W, $pick.H)
    pid    = [int]$pick.Pid
    en     = [bool]$pick.En
    area   = [int64]$pick.Area
}
$score = "class=$($pick.Cls) hwnd=$pickHex title=""$($pick.Title)"" rect=$($pick.X),$($pick.Y),$($pick.W),$($pick.H) size=$($pick.W)x$($pick.H)"
$pickNote = "picked $(if ($fresh.Count -gt 0) { 'newest' } else { 'largest' }) of $($cands.Count) candidate(s): $score"
$base.note = $pickNote

# A minimized window still reports itself visible and GetWindowRect hands back the
# icon-position sentinel (-32000,-32000) with a tiny restored size -> a useless
# 353x56 image that would still be called "ok".
if ([WinProbe]::Minimized($pickHwnd) -or [int]$pick.X -le -30000 -or [int]$pick.Y -le -30000) {
    $base.reason = 'minimized'
    $base.note = "target is minimized / off-screen: $score"
    [Console]::Error.WriteLine("win-probe: $($base.note); nothing written to $Out")
    Write-Result $base 1
}
if ([int]$pick.W -le 0 -or [int]$pick.H -le 0) {
    $base.reason = 'empty-rect'
    $base.note = "target has an empty rect: $score"
    [Console]::Error.WriteLine("win-probe: $($base.note); nothing written to $Out")
    Write-Result $base 1
}

# A real window is never 100% pure black; a blank PrintWindow result always is.
# Sampling ~20k pixels keeps this O(1) in window size instead of a 5M-iteration
# PowerShell loop.
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

$bmp = New-Object System.Drawing.Bitmap($pick.W, $pick.H)
$g = [System.Drawing.Graphics]::FromImage($bmp)
function Invoke-Shot([int]$flag) {
    $g.Clear([System.Drawing.Color]::Black)      # reset before repainting
    $hdc = $g.GetHdc()
    try { return [WinProbe]::Shot($pickHwnd, $hdc, [uint32]$flag) } finally { $g.ReleaseHdc($hdc) }
}

$used = $Flags
$retried = $false
$ok = Invoke-Shot $Flags
$blank = -not (Test-VisiblePixels $bmp)
if ($blank) {
    $other = 0; if ($Flags -eq 0) { $other = 2 }
    $used = $other
    $retried = $true
    [void](Invoke-Shot $other)
    $ok = Test-VisiblePixels $bmp
    $blank = -not $ok
}
$base.retried = $retried
$base.flags = $used

if ($blank) {
    $g.Dispose(); $bmp.Dispose()
    $base.reason = 'blank'
    $base.ok = $false
    $base.note = "$score; PrintWindow painted NOTHING, tried flags=$Flags,$used"
    [Console]::Error.WriteLine("win-probe: $($base.note); nothing written to $Out")
    Write-Result $base 1
}

$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
$base.ok = $true
$base.reason = $null
$base.bytes = [int64](Get-Item -LiteralPath $Out).Length
$base.note = "$pickNote; PrintWindow ok=$ok flags=$used"
Write-Result $base 0
