param(
    [Parameter(Mandatory = $true)][string]$TitleLike,
    [ValidateSet('key', 'text')][string]$Action = 'key',
    # Target child window class.  'Edit' is what a text field reports in SWT; the
    # callers that need another class pass it explicitly.
    [string]$Class = 'Edit',
    # -1 = "the class must be unambiguous": 0 or >1 matches fail closed.  This is
    # the same rule the text addressing of win-click-button.ps1 follows, and it is
    # what stops two Edit fields from being silently confused for one another.
    [int]$Index = -1,
    # Key name for -Action key (RETURN / TAB / ESCAPE / F5 / A / 1 ...).
    [string]$Key = 'RETURN',
    # Payload for -Action text.
    [string]$Payload = '',
    [switch]$ListOnly,
    # 0 = match any process.  Set it whenever more than one instance of the IDE can
    # be on screen: two workbenches each showing an Edit field are otherwise
    # indistinguishable here, and this tool *types into things*.
    [int]$ProcId = 0
)
# Find a top-level window by title, enumerate its child windows (class + text +
# rect), and optionally drive the matching child: send WM_KEYDOWN/WM_KEYUP
# (a real key press the widget sees, without owning the keyboard) or WM_SETTEXT
# (replace the control's text outright, independent of focus and keyboard layout).
#
# Both are *element addressed*: the message goes to the control's own HWND, so
# nothing depends on where the control happens to be on screen or on which window
# is in the foreground.  See design-project.md §18.3 (原语与寻址).
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class Inp {
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
  [DllImport("user32.dll")] public static extern IntPtr SendMessageW(IntPtr h, uint msg, IntPtr wp, IntPtr lp);
  [DllImport("user32.dll", CharSet=CharSet.Unicode, EntryPoint="SendMessageW")]
  public static extern IntPtr SendMessageStr(IntPtr h, uint msg, IntPtr wp, string lp);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public static IntPtr Top = IntPtr.Zero;
  public static uint Only = 0;
  public static IntPtr Find(string like) {
    Top = IntPtr.Zero;
    EnumWindows(delegate(IntPtr h, IntPtr p) {
      if (Top != IntPtr.Zero) return true;
      if (!IsWindowVisible(h)) return true;
      if (Only != 0) { uint pid; GetWindowThreadProcessId(h, out pid); if (pid != Only) return true; }
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      if (t.ToString().IndexOf(like, StringComparison.OrdinalIgnoreCase) < 0) return true;
      Top = h; return true;
    }, IntPtr.Zero);
    return Top;
  }
  public static List<string> Children() {
    var outv = new List<string>();
    if (Top == IntPtr.Zero) return outv;
    EnumChildWindows(Top, delegate(IntPtr h, IntPtr p) {
      var t = new StringBuilder(512); GetWindowTextW(h, t, 512);
      var c = new StringBuilder(256); GetClassNameW(h, c, 256);
      RECT r; GetWindowRect(h, out r);
      outv.Add(string.Format("hwnd=0x{0:X} class={1} vis={2} text=\"{3}\" rect={4},{5},{6},{7}",
        (long)h, c, IsWindowVisible(h), Esc(t.ToString()), r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top));
      return true;
    }, IntPtr.Zero);
    return outv;
  }
  // Handles of visible children whose class equals ``cls``, in enumeration order.
  public static List<IntPtr> ByClass(string cls) {
    var outv = new List<IntPtr>();
    if (Top == IntPtr.Zero) return outv;
    EnumChildWindows(Top, delegate(IntPtr h, IntPtr p) {
      var c = new StringBuilder(256); GetClassNameW(h, c, 256);
      if (c.ToString() == cls && IsWindowVisible(h)) outv.Add(h);
      return true;
    }, IntPtr.Zero);
    return outv;
  }
  // One listing field (`text="…"`) is a JSON string body: `\` and `"` doubled, and
  // CR/LF/TAB plus every other control character (and U+0085/U+2028/U+2029, which
  // Python's str.splitlines() also breaks on) written as `\r`/`\n`/`\t`/`\uXXXX`.
  // Without it a control's text containing a line break would forge a whole extra
  // `hwnd=… class=…` line for the Python readers, which count lines.
  public static string Esc(string s) {
    var b = new StringBuilder(s.Length + 8);
    foreach (char ch in s) {
      switch (ch) {
        case '\\': b.Append("\\\\"); break;
        case '"': b.Append("\\\""); break;
        case '\r': b.Append("\\r"); break;
        case '\n': b.Append("\\n"); break;
        case '\t': b.Append("\\t"); break;
        default:
          if (ch < ' ' || ch == '\u0085' || ch == '\u2028' || ch == '\u2029')
            b.Append("\\u").Append(((int)ch).ToString("x4"));
          else b.Append(ch);
          break;
      }
    }
    return b.ToString();
  }
  public static string SendKey(IntPtr h, uint vk) {
    SendMessageW(h, 0x0100, (IntPtr)vk, IntPtr.Zero);   // WM_KEYDOWN
    SendMessageW(h, 0x0101, (IntPtr)vk, IntPtr.Zero);   // WM_KEYUP
    return string.Format("sent WM_KEYDOWN/WM_KEYUP vk=0x{0:X} -> hwnd=0x{1:X}", vk, (long)h);
  }
  public static string SetText(IntPtr h, string s) {
    SendMessageStr(h, 0x000C, IntPtr.Zero, s);          // WM_SETTEXT
    return string.Format("sent WM_SETTEXT \"{0}\" -> hwnd=0x{1:X}", Esc(s), (long)h);
  }
}
"@
[void][Inp]::SetProcessDPIAware()
[Inp]::Only = [uint32]$ProcId
$d = [Inp]::Find($TitleLike)
if ($d -eq [IntPtr]::Zero) { Write-Output "no visible window matching '$TitleLike'"; exit 1 }
Write-Output ("window hwnd=0x{0:X}" -f [int64]$d)
Write-Output "-- child windows --"
[Inp]::Children() | ForEach-Object { Write-Output ("  " + $_) }

if ($ListOnly) { exit 0 }

# Addressing rule (design-project.md §18.3): the class must resolve to exactly one
# visible child, unless the caller pinned an index.  A silent pick is what makes
# two same-labelled controls click the wrong one.
$handles = [Inp]::ByClass($Class)
if ($handles.Count -eq 0) { Write-Output ("ERR no visible child of class '$Class'"); exit 1 }
if ($Index -lt 0 -and $handles.Count -gt 1) {
    Write-Output ("ERR $($handles.Count) visible children of class '$Class' -- addressing must be unique; pass -Index")
    exit 1
}
if ($Index -ge $handles.Count) { Write-Output ("ERR -Index $Index out of range ($($handles.Count) match(es))"); exit 1 }
$target = if ($Index -ge 0) { $handles[$Index] } else { $handles[0] }

$vk = @{
    'RETURN' = 0x0D; 'ENTER' = 0x0D; 'ESCAPE' = 0x1B; 'ESC' = 0x1B; 'TAB' = 0x09; 'SPACE' = 0x20
    'BACK' = 0x08; 'DELETE' = 0x2E; 'UP' = 0x26; 'DOWN' = 0x28; 'LEFT' = 0x25; 'RIGHT' = 0x27
}
foreach ($i in 1..12) { $vk["F$i"] = 0x6F + $i }

Write-Output "-- send --"
switch ($Action) {
    'key' {
        $name = $Key.ToUpper()
        $code = $null
        if ($vk.ContainsKey($name)) { $code = $vk[$name] }
        elseif ($name.Length -eq 1) {
            $ch = [char]$name[0]
            if ([char]::IsLetterOrDigit($ch)) { $code = [int][char]::ToUpper($ch) }
        }
        if ($null -eq $code) { Write-Output "ERR unknown key name '$Key'"; exit 1 }
        Write-Output ("  " + [Inp]::SendKey($target, [uint32]$code))
    }
    'text' {
        Write-Output ("  " + [Inp]::SetText($target, $Payload))
    }
}
exit 0
