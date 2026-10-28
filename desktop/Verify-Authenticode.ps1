# MIT. Read-only verification; no certificate creation or trust-store changes.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Manifest,
    [Parameter(Mandatory=$true)][string]$CertificateThumbprint
)
$ErrorActionPreference = 'Stop'
$expected = ($CertificateThumbprint -replace '\s','').ToUpperInvariant()
if ($expected -notmatch '^[A-F0-9]{40}$') { throw 'Missing expected production certificate thumbprint.' }
$items = @((Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json).files)
if ($items.Count -eq 0) { throw 'No files to verify.' }
foreach ($path in $items) {
    $signature = Get-AuthenticodeSignature -LiteralPath $path
    if ($signature.Status -ne 'Valid') { throw "Invalid Authenticode signature: $path" }
    if ($signature.SignerCertificate.Thumbprint.ToUpperInvariant() -ne $expected) { throw "Unexpected signing identity: $path" }
    if (-not $signature.TimeStamperCertificate) { throw "Missing trusted timestamp: $path" }
    Write-Output "Verified Authenticode, expected signer and timestamp: $([System.IO.Path]::GetFileName($path))"
}
