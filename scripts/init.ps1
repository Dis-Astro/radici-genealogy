$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$secretDirectory = Join-Path $projectRoot '.secrets'
$secretPath = Join-Path $secretDirectory 'app_password.txt'
New-Item -ItemType Directory -Force -Path $secretDirectory | Out-Null
if (-not (Test-Path -LiteralPath $secretPath)) {
    $secureValue = Read-Host 'Scegli una password (almeno 12 caratteri)' -AsSecureString
    $secureRepeat = Read-Host 'Ripeti la password' -AsSecureString
    $plainValue = [System.Net.NetworkCredential]::new('', $secureValue).Password
    $plainRepeat = [System.Net.NetworkCredential]::new('', $secureRepeat).Password
    if ($plainValue.Length -lt 12) { throw 'Servono almeno 12 caratteri.' }
    if ($plainValue -cne $plainRepeat) { throw 'Le password non coincidono.' }
    [System.IO.File]::WriteAllText($secretPath, $plainValue + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
    $plainValue = $null
    $plainRepeat = $null
    Write-Host 'Password configurata. Non viene inclusa in Git o nei backup.'
} else { Write-Host 'Password già configurata. Nessuna modifica.' }
$envPath = Join-Path $projectRoot '.env'
if (-not (Test-Path -LiteralPath $envPath)) { Copy-Item -LiteralPath (Join-Path $projectRoot '.env.example') -Destination $envPath }
Write-Host 'Ora esegui: docker compose up --build -d'
