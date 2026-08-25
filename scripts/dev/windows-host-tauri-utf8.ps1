Set-StrictMode -Version Latest

function New-AngmooUtf8NoBomEncoding {
    return [System.Text.UTF8Encoding]::new($false)
}

function Enter-AngmooUtf8NativeCommandScope {
    $outputVariable = Get-Variable -Name OutputEncoding -Scope Global -ErrorAction SilentlyContinue
    $state = [pscustomobject]@{
        input_encoding = [Console]::InputEncoding
        output_encoding = [Console]::OutputEncoding
        pipeline_output_encoding_exists = $null -ne $outputVariable
        pipeline_output_encoding = if ($outputVariable) { $outputVariable.Value } else { $null }
    }
    $utf8 = New-AngmooUtf8NoBomEncoding
    [Console]::InputEncoding = $utf8
    [Console]::OutputEncoding = $utf8
    $global:OutputEncoding = $utf8
    return $state
}

function Exit-AngmooUtf8NativeCommandScope {
    param([Parameter(Mandatory = $true)][object]$State)

    [Console]::InputEncoding = $State.input_encoding
    [Console]::OutputEncoding = $State.output_encoding
    if ($State.pipeline_output_encoding_exists) {
        $global:OutputEncoding = $State.pipeline_output_encoding
    } else {
        Remove-Variable -Name OutputEncoding -Scope Global -ErrorAction SilentlyContinue
    }
}

function ConvertFrom-AngmooJsonText {
    param(
        [Parameter(Mandatory = $true)][string]$Content,
        [switch]$JsonLines,
        [string]$FailureCode = 'compose_json_decode_failed'
    )

    try {
        if ($JsonLines -and -not $Content.TrimStart().StartsWith('[')) {
            return @(
                [regex]::Split($Content.Trim(), '\r?\n') |
                    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
                    ForEach-Object { $_ | ConvertFrom-Json -ErrorAction Stop }
            )
        }
        return @($Content | ConvertFrom-Json -ErrorAction Stop)
    } catch {
        throw [IO.InvalidDataException]::new($FailureCode)
    }
}

function New-AngmooNativeJsonFailure {
    param(
        [string]$FailureCode,
        [string]$CommandType,
        [int]$ExitCode,
        [int]$CharacterLength,
        [int]$ByteLength,
        [int]$Attempt,
        [string]$Reason
    )

    $powerShellVersion = [string]$PSVersionTable.PSVersion
    $codePage = [Console]::OutputEncoding.CodePage
    return (
        "$FailureCode command=$CommandType exit=$ExitCode chars=$CharacterLength " +
        "bytes=$ByteLength attempt=$Attempt powershell=$powerShellVersion " +
        "codepage=$codePage reason=$Reason"
    )
}

function Invoke-AngmooNativeJsonCommand {
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Command,
        [Parameter(Mandatory = $true)][string]$CommandType,
        [switch]$AllowEmpty,
        [switch]$JsonLines,
        [ValidateRange(1, 3)][int]$MaximumAttempts = 2,
        [string]$FailureCode = 'compose_json_decode_failed'
    )

    $lastFailure = $null
    for ($attempt = 1; $attempt -le $MaximumAttempts; $attempt += 1) {
        $raw = @(& $Command)
        $exitCode = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
        $content = ($raw | ForEach-Object { [string]$_ }) -join "`n"
        $content = $content.Trim()
        $characterLength = $content.Length
        $byteLength = [Text.Encoding]::UTF8.GetByteCount($content)

        if ($exitCode -ne 0) {
            $lastFailure = New-AngmooNativeJsonFailure `
                -FailureCode $FailureCode -CommandType $CommandType -ExitCode $exitCode `
                -CharacterLength $characterLength -ByteLength $byteLength -Attempt $attempt `
                -Reason 'native_exit_nonzero'
            continue
        }
        if (-not $content) {
            if ($AllowEmpty) { return @() }
            $lastFailure = New-AngmooNativeJsonFailure `
                -FailureCode $FailureCode -CommandType $CommandType -ExitCode $exitCode `
                -CharacterLength 0 -ByteLength 0 -Attempt $attempt -Reason 'empty_output'
            continue
        }
        try {
            return @(ConvertFrom-AngmooJsonText -Content $content -JsonLines:$JsonLines -FailureCode $FailureCode)
        } catch {
            $lastFailure = New-AngmooNativeJsonFailure `
                -FailureCode $FailureCode -CommandType $CommandType -ExitCode $exitCode `
                -CharacterLength $characterLength -ByteLength $byteLength -Attempt $attempt `
                -Reason 'json_parse_failed'
        }
    }

    throw [IO.InvalidDataException]::new($lastFailure)
}
