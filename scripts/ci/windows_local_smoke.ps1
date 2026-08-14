Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$localScripts = Get-ChildItem -LiteralPath (Join-Path $repoRoot 'scripts\local') -Filter '*.ps1' -File
if (-not $localScripts) {
    throw 'windows_local_scripts_missing'
}

foreach ($script in $localScripts) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $script.FullName,
        [ref]$tokens,
        [ref]$errors
    )
    if ($errors.Count -gt 0) {
        throw "powershell_parse_failed:$($script.Name)"
    }
}

$secretScript = Get-Content -LiteralPath (Join-Path $repoRoot 'scripts\local\neo4j-local-secret.ps1') -Raw -Encoding utf8
foreach ($marker in @(
    'Set-AngmooCurrentUserOnlyAcl',
    'ConvertFrom-SecureString',
    'ConvertFrom-AngmooSecureStringInMemory',
    'Clear-AngmooNeo4jLocalEnvironment'
)) {
    if (-not $secretScript.Contains($marker)) {
        throw "neo4j_secret_contract_missing:$marker"
    }
}

$plain = "synthetic-dpapi-$([Guid]::NewGuid().ToString('N'))"
try {
    $secure = ConvertTo-SecureString -String $plain -AsPlainText -Force
    $ciphertext = ConvertFrom-SecureString -SecureString $secure
    $roundTripSecure = ConvertTo-SecureString -String $ciphertext
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($roundTripSecure)
    try {
        $roundTrip = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    if ($roundTrip -ne $plain) {
        throw 'dpapi_round_trip_mismatch'
    }
} finally {
    $plain = $null
    $roundTrip = $null
    $secure = $null
    $roundTripSecure = $null
    $ciphertext = $null
}

Write-Host "windows_local_smoke=pass scripts=$($localScripts.Count) dpapi=pass"
