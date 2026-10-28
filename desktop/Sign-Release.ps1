# MIT. Authenticode signing through an existing publisher identity in Windows.
# Does not create certificates, export keys, change trust stores, or configure AV.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Manifest,
    [Parameter(Mandatory=$true)][string]$Report,
    [string]$CertificateThumbprint,
    [string]$SignTool,
    [switch]$VerifyOnly,
    [switch]$PreflightOnly
)
$ErrorActionPreference='Stop'
$results=@()
try {
    if($VerifyOnly -and $PreflightOnly){throw 'Scegli una sola modalità di verifica.'}
    $thumb=($CertificateThumbprint -replace '\s','').ToUpperInvariant()
    if(-not $VerifyOnly){
        if($thumb -notmatch '^[A-F0-9]{40}$'){throw 'Serve un thumbprint di certificato Authenticode del produttore; non viene creata una firma autoattestata.'}
        $certificate=Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object Thumbprint -EQ $thumb | Select-Object -First 1
        if(-not $certificate){throw 'Certificato di firma del codice non presente nel profilo Windows corrente.'}
        if(-not $certificate.HasPrivateKey){throw 'Il certificato non dispone di una chiave utilizzabile da questo profilo.'}
        if($certificate.NotAfter -le (Get-Date) -or $certificate.NotBefore -gt (Get-Date)){throw 'Il certificato non è attualmente valido.'}
        if($certificate.Subject -eq $certificate.Issuer -or -not $certificate.Verify()){throw 'La catena del certificato non è verificata come attendibile. Il rilascio si interrompe.'}
        if(-not $SignTool){
            $command=Get-Command signtool.exe -ErrorAction SilentlyContinue
            if($command){$SignTool=$command.Source}
            else{$SignTool=Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe' -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName}
        }
        if(-not $SignTool -or -not (Test-Path -LiteralPath $SignTool)){throw 'SignTool del Windows SDK non è disponibile. Non verrà prodotta una release dichiarata firmata.'}
    }
    if(-not $PreflightOnly){
        $inputManifest=Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
        $files=@($inputManifest.files)
        if($files.Count -eq 0){throw 'Nessun eseguibile specificato.'}
        foreach($file in $files){
            $path=(Resolve-Path -LiteralPath ([string]$file)).Path
            if([IO.Path]::GetExtension($path) -notin @('.exe','.dll')){throw 'Sono ammesse soltanto firme di file EXE o DLL esplicitamente indicati.'}
            $signature=Get-AuthenticodeSignature -LiteralPath $path
            $matching=($signature.Status -eq 'Valid' -and $signature.SignerCertificate -and $signature.SignerCertificate.Thumbprint -eq $thumb -and $signature.TimeStamperCertificate)
            if(-not $VerifyOnly -and -not $matching){
                & $SignTool sign /s My /sha1 $thumb /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /d 'Radici Desktop' $path
                if($LASTEXITCODE -ne 0){throw "SignTool non ha completato la firma di $([IO.Path]::GetFileName($path))."}
                $signature=Get-AuthenticodeSignature -LiteralPath $path
            }
            if($signature.Status -ne 'Valid' -or -not $signature.SignerCertificate){throw "Firma non verificata: $([IO.Path]::GetFileName($path)) ($($signature.Status))."}
            if(-not $VerifyOnly -and $signature.SignerCertificate.Thumbprint -ne $thumb){throw 'La firma appartiene a un editore diverso da quello richiesto.'}
            if(-not $signature.TimeStamperCertificate){throw 'La firma non contiene una marca temporale verificabile.'}
            $results+=@{file=$path;status=[string]$signature.Status;publisher=$signature.SignerCertificate.Subject;timestamped=$true;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
        }
    }
    @{success=$true;preflight=[bool]$PreflightOnly;verification_only=[bool]$VerifyOnly;files=$results} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Report -Encoding UTF8
    exit 0
}
catch {
    @{success=$false;error=$_.Exception.Message;files=$results} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Report -Encoding UTF8
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
