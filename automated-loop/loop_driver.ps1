<#
.SYNOPSIS
    Automated Claude Code + Perplexity Research Loop Driver (PowerShell wrapper).

.DESCRIPTION
    Thin wrapper that delegates to the Python loop driver (loop_driver.py).
    Kept for backwards compatibility — the Python driver is the primary entry point.

.PARAMETER ProjectPath
    Target project directory (default: current directory).

.PARAMETER MaxIterations
    Maximum number of loop iterations (default: 50).

.PARAMETER InitialPrompt
    Prompt for the first iteration (default: reads from CLAUDE.md context).

.PARAMETER TimeoutSeconds
    Per-iteration timeout in seconds (default: 300).

.PARAMETER Model
    Claude model to use (default: sonnet).

.PARAMETER MaxBudgetUsd
    Max total budget in USD (default: 50.0).

.PARAMETER DryRun
    Show what would happen without spawning Claude.

.PARAMETER JsonLog
    Output structured JSON logs.

.PARAMETER SmokeTest
    Safe single-iteration production validation.

.PARAMETER ConfigPath
    Path to config.json (default: .workflow/config.json).

.EXAMPLE
    .\loop_driver.ps1 -ProjectPath . -MaxIterations 50 -Verbose
    .\loop_driver.ps1 -ProjectPath . -MaxIterations 1 -DryRun -Verbose
#>

[CmdletBinding()]
param(
    [string]$ProjectPath = ".",
    [int]$MaxIterations = 50,
    [string]$InitialPrompt = "",
    [int]$TimeoutSeconds = 300,
    [string]$Model = "sonnet",
    [double]$MaxBudgetUsd = 50.0,
    [switch]$DryRun,
    [switch]$JsonLog,
    [switch]$SmokeTest,
    [string]$ConfigPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectPath = (Resolve-Path $ProjectPath).Path
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonDriver = Join-Path $ScriptDir "loop_driver.py"

if (-not (Test-Path $PythonDriver)) {
    Write-Error "Python driver not found at $PythonDriver"
    exit 1
}

$pythonArgs = @($PythonDriver, "--project", $ProjectPath, "--max-iterations", $MaxIterations.ToString(), "--model", $Model, "--timeout", $TimeoutSeconds.ToString(), "--max-budget", $MaxBudgetUsd.ToString())

if ($InitialPrompt) {
    $pythonArgs += "--prompt"
    $pythonArgs += $InitialPrompt
}
if ($ConfigPath) {
    $pythonArgs += "--config"
    $pythonArgs += $ConfigPath
}
if ($DryRun) {
    $pythonArgs += "--dry-run"
}
if ($JsonLog) {
    $pythonArgs += "--json-log"
}
if ($SmokeTest) {
    $pythonArgs += "--smoke-test"
}
if ($VerbosePreference -eq "Continue") {
    $pythonArgs += "--verbose"
}

& python @pythonArgs
exit $LASTEXITCODE
