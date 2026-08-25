[CmdletBinding()]
param(
    [switch]$EncodingWorker,
    [string]$EmitterPath,
    [int]$InitialCodePage = 65001,
    [string]$CounterRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$utf8Support = Join-Path $repoRoot 'scripts\dev\windows-host-tauri-utf8.ps1'
. $utf8Support

if ($EncodingWorker) {
    $initialEncoding = [Text.Encoding]::GetEncoding($InitialCodePage)
    [Console]::InputEncoding = $initialEncoding
    [Console]::OutputEncoding = $initialEncoding
    $global:OutputEncoding = $initialEncoding
    $beforeInput = [Console]::InputEncoding.CodePage
    $beforeOutput = [Console]::OutputEncoding.CodePage
    $beforePipeline = $global:OutputEncoding.CodePage
    $expectedUnicode = -join @([char]0xD55C, [char]0xAE00, [char]0x2026)
    $scope = $null

    try {
        $scope = Enter-AngmooUtf8NativeCommandScope
        if ([Console]::InputEncoding.CodePage -ne 65001) { throw 'utf8_input_scope_not_applied' }
        if ([Console]::OutputEncoding.CodePage -ne 65001) { throw 'utf8_output_scope_not_applied' }
        if ($global:OutputEncoding.CodePage -ne 65001) { throw 'utf8_pipeline_scope_not_applied' }

        $unicode = @(
            Invoke-AngmooNativeJsonCommand -CommandType 'fixture-unicode' -Command {
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $EmitterPath -Mode unicode
            }
        )
        if ($unicode.Count -ne 1 -or $unicode[0].Message -ne $expectedUnicode) {
            throw 'utf8_unicode_fixture_mismatch'
        }

        $ascii = @(
            Invoke-AngmooNativeJsonCommand -CommandType 'fixture-ascii' -Command {
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $EmitterPath -Mode ascii
            }
        )
        if ($ascii.Count -ne 1 -or $ascii[0].Message -ne 'ascii') {
            throw 'utf8_ascii_fixture_mismatch'
        }

        $retryCounter = Join-Path $CounterRoot "retry-$PID-$InitialCodePage.txt"
        $retried = @(
            Invoke-AngmooNativeJsonCommand -CommandType 'fixture-retry' -MaximumAttempts 2 -Command {
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $EmitterPath `
                    -Mode retry -CounterPath $retryCounter
            }
        )
        if ($retried.Count -ne 1 -or $retried[0].Message -ne $expectedUnicode) {
            throw 'utf8_retry_fixture_mismatch'
        }
        if ([int](Get-Content -LiteralPath $retryCounter -Raw) -ne 2) {
            throw 'utf8_retry_bound_mismatch'
        }

        $failureMessage = ''
        try {
            Invoke-AngmooNativeJsonCommand -CommandType 'fixture-invalid' -MaximumAttempts 2 -Command {
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $EmitterPath -Mode invalid
            } | Out-Null
            throw 'utf8_invalid_fixture_should_fail'
        } catch {
            $failureMessage = $_.Exception.Message
        }
        if ($failureMessage -notmatch '^compose_json_decode_failed ') {
            throw 'utf8_failure_reason_code_missing'
        }
        if ($failureMessage -notmatch 'attempt=2' -or $failureMessage -notmatch 'reason=json_parse_failed') {
            throw 'utf8_failure_diagnostic_incomplete'
        }
        if ($failureMessage -match 'do-not-leak|secret|\{"') {
            throw 'utf8_failure_leaked_raw_json'
        }
    } finally {
        if ($null -ne $scope) {
            Exit-AngmooUtf8NativeCommandScope -State $scope
        }
    }

    if ([Console]::InputEncoding.CodePage -ne $beforeInput) { throw 'utf8_input_scope_not_restored' }
    if ([Console]::OutputEncoding.CodePage -ne $beforeOutput) { throw 'utf8_output_scope_not_restored' }
    if ($global:OutputEncoding.CodePage -ne $beforePipeline) { throw 'utf8_pipeline_scope_not_restored' }
    Write-Output "encoding-worker-pass:ps=$($PSVersionTable.PSVersion);codepage=$InitialCodePage"
    exit 0
}

$fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) "angmoo-host-tauri-utf8-$([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path $fixtureRoot | Out-Null
$emitter = Join-Path $fixtureRoot 'emit-utf8-json.ps1'
$emitterSource = @'
param(
    [ValidateSet('unicode', 'ascii', 'retry', 'invalid')][string]$Mode,
    [string]$CounterPath = ''
)
$ellipsis = [string][char]0x2026
$unicodeMessage = -join @([char]0xD55C, [char]0xAE00, [char]0x2026)
$text = switch ($Mode) {
    'unicode' { '{"Command":"/usr/local/bin/angm' + $ellipsis + '","Message":"' + $unicodeMessage + '"}' }
    'ascii' { '{"Message":"ascii"}' }
    'invalid' { '{"secret":"do-not-leak"' }
    'retry' {
        $count = if (Test-Path -LiteralPath $CounterPath) {
            [int](Get-Content -LiteralPath $CounterPath -Raw)
        } else { 0 }
        $count += 1
        Set-Content -LiteralPath $CounterPath -Value $count -Encoding Ascii
        if ($count -eq 1) { '{"secret":"do-not-leak"' }
        else { '{"Command":"/usr/local/bin/angm' + $ellipsis + '","Message":"' + $unicodeMessage + '"}' }
    }
}
$bytes = [Text.Encoding]::UTF8.GetBytes($text)
$stream = [Console]::OpenStandardOutput()
$stream.Write($bytes, 0, $bytes.Length)
$stream.Flush()
'@
[IO.File]::WriteAllText($emitter, $emitterSource, [Text.UTF8Encoding]::new($true))

try {
    $shells = @(
        [pscustomobject]@{ name = 'windows-powershell-5.1'; path = (Get-Command powershell.exe -ErrorAction Stop).Source },
        [pscustomobject]@{ name = 'powershell-7'; path = (Get-Command pwsh.exe -ErrorAction Stop).Source }
    )
    $cases = @(
        [pscustomobject]@{ name = 'cp949'; code_page = 949 },
        [pscustomobject]@{ name = 'utf8'; code_page = 65001 }
    )
    $passed = 0
    foreach ($shell in $shells) {
        foreach ($case in $cases) {
            $output = @(
                & $shell.path -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath `
                    -EncodingWorker -EmitterPath $emitter -InitialCodePage $case.code_page `
                    -CounterRoot $fixtureRoot
            )
            if ($LASTEXITCODE -ne 0) {
                throw "utf8_worker_failed:shell=$($shell.name);case=$($case.name);exit=$LASTEXITCODE"
            }
            if (($output -join "`n") -notmatch 'encoding-worker-pass:') {
                throw "utf8_worker_output_missing:shell=$($shell.name);case=$($case.name)"
            }
            $passed += 1
        }
    }
} finally {
    Remove-Item -LiteralPath $fixtureRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "windows-host-tauri-utf8-smoke: PASS cases=$passed"
exit 0
