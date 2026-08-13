Set-StrictMode -Version Latest

$script:AngmooNeo4jVolumeName = 'angmoo-p7-neo4j-data'
$script:AngmooNeo4jSecretPath = Join-Path $env:LOCALAPPDATA 'angmoo\secrets\neo4j-local-password.dpapi'

function Test-AngmooNeo4jNamedVolume {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'docker_command_not_found'
    }
    $names = @(
        & docker volume ls --filter "name=^$($script:AngmooNeo4jVolumeName)$" --format '{{.Name}}' 2>$null
    )
    if ($LASTEXITCODE -ne 0) {
        throw 'docker_volume_list_failed'
    }
    return $names -contains $script:AngmooNeo4jVolumeName
}

function Set-AngmooCurrentUserOnlyAcl {
    param([Parameter(Mandatory)][string]$LiteralPath)

    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $acl = Get-Acl -LiteralPath $LiteralPath
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($rule in @($acl.Access)) {
        [void]$acl.RemoveAccessRuleAll($rule)
    }
    $inheritance = if ((Get-Item -LiteralPath $LiteralPath).PSIsContainer) {
        [System.Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
    } else {
        [System.Security.AccessControl.InheritanceFlags]::None
    }
    $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
        $identity,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        $inheritance,
        [System.Security.AccessControl.PropagationFlags]::None,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    [void]$acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $LiteralPath -AclObject $acl
}

function ConvertFrom-AngmooSecureStringInMemory {
    param([Parameter(Mandatory)][Security.SecureString]$SecureValue)

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

function New-AngmooNeo4jLocalSecretCiphertext {
    $secretDirectory = Split-Path -Parent $script:AngmooNeo4jSecretPath
    if (-not (Test-Path -LiteralPath $secretDirectory)) {
        New-Item -ItemType Directory -Path $secretDirectory -Force | Out-Null
    }
    Set-AngmooCurrentUserOnlyAcl -LiteralPath $secretDirectory

    $bytes = [byte[]]::new(32)
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    $plain = -join ($bytes | ForEach-Object { $_.ToString('x2') })
    [Array]::Clear($bytes, 0, $bytes.Length)
    try {
        $secure = ConvertTo-SecureString -String $plain -AsPlainText -Force
        $ciphertext = ConvertFrom-SecureString -SecureString $secure
        [IO.File]::WriteAllText(
            $script:AngmooNeo4jSecretPath,
            $ciphertext,
            [Text.UTF8Encoding]::new($false)
        )
        Set-AngmooCurrentUserOnlyAcl -LiteralPath $script:AngmooNeo4jSecretPath
    } finally {
        $plain = $null
        $secure = $null
        $ciphertext = $null
    }
    Write-Host 'neo4j_local_secret_created=true'
}

function Initialize-AngmooNeo4jLocalEnvironment {
    $volumeExists = Test-AngmooNeo4jNamedVolume
    $cipherExists = Test-Path -LiteralPath $script:AngmooNeo4jSecretPath
    if ($volumeExists -and -not $cipherExists) {
        throw 'neo4j_volume_exists_but_dpapi_cipher_is_missing'
    }
    if (-not $cipherExists) {
        New-AngmooNeo4jLocalSecretCiphertext
    }

    try {
        $ciphertext = Get-Content -LiteralPath $script:AngmooNeo4jSecretPath -Raw -Encoding utf8
        $secure = ConvertTo-SecureString -String $ciphertext
        $plain = ConvertFrom-AngmooSecureStringInMemory -SecureValue $secure
        if ([string]::IsNullOrWhiteSpace($plain)) {
            throw 'neo4j_dpapi_cipher_decrypted_empty'
        }
        $env:NEO4J_PASSWORD = $plain
        $env:NEO4J_AUTH = "neo4j/$plain"
        $env:NEO4J_URI = 'bolt://127.0.0.1:7687'
        $env:NEO4J_DATABASE = 'neo4j'
        $env:NEO4J_USERNAME = 'neo4j'
        $env:GRAPH_PROJECTION_ENABLED = 'true'
    } catch {
        if ($volumeExists) {
            throw 'neo4j_volume_exists_but_dpapi_cipher_is_invalid'
        }
        throw
    } finally {
        $plain = $null
        $secure = $null
        $ciphertext = $null
    }
    Write-Host 'neo4j_local_secret_reused=true'
}

function Clear-AngmooNeo4jLocalEnvironment {
    Remove-Item Env:NEO4J_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:NEO4J_AUTH -ErrorAction SilentlyContinue
    Remove-Item Env:NEO4J_URI -ErrorAction SilentlyContinue
    Remove-Item Env:NEO4J_DATABASE -ErrorAction SilentlyContinue
    Remove-Item Env:NEO4J_USERNAME -ErrorAction SilentlyContinue
    Remove-Item Env:GRAPH_PROJECTION_ENABLED -ErrorAction SilentlyContinue
}
