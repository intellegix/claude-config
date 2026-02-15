Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class Win {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

$p = Get-Process chrome | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if ($p) {
    # SW_MAXIMIZE = 3 — maximize the window
    [Win]::ShowWindow($p.MainWindowHandle, 3) | Out-Null
    [Win]::SetForegroundWindow($p.MainWindowHandle) | Out-Null
}
