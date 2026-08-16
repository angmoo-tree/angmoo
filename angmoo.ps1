[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Command = 'help',

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$LauncherArguments = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$modulePath = Join-Path $PSScriptRoot 'launcher\windows\Angmoo.Launcher.psm1'
Import-Module -Name $modulePath -Force

$invocationResult = Invoke-AngmooLauncher -Command $Command -Arguments $LauncherArguments
if ($invocationResult.json_requested) {
    $invocationResult.result | ConvertTo-Json -Depth 12 -Compress
} else {
    Write-AngmooLauncherHumanResult -Result $invocationResult.result
}
exit [int]$invocationResult.result.exit_code
