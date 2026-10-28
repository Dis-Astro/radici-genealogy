# MIT. This integration test is restricted to disposable GitHub-hosted Windows VMs.
# No private certificate is exported or uploaded. Nothing runs on the user's PC.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Package,[Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSEdition -ne 'Desktop'){throw 'Appx deployment requires Windows PowerShell 5.1; PowerShell 7 is unsupported.'}
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:RUNNER_OS -ne 'Windows'){throw 'This test may run only on a disposable GitHub-hosted Windows runner.'}
$name='Radici.Genealogy.Development'
if(Get-AppxPackage -Name $name){throw 'An existing package must never be replaced by the CI test.'}
$dataPath=Join-Path $env:LOCALAPPDATA 'Radici\Archivio'
if(Test-Path -LiteralPath $dataPath){throw 'The test requires a fresh profile with no genealogy archive.'}
$outputPath=[System.IO.Path]::GetFullPath($Output)
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
$certificate=$null;$trusted=$null;$installed=$null;$appProcess=$null
try {
    # The subject matches only the development identity, never a real publisher.
    $certificate=New-SelfSignedCertificate -Type Custom -Subject 'CN=Radici.Development' -KeyUsage DigitalSignature -KeyExportPolicy NonExportable -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddHours(2) -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3','2.5.29.19={text}')
    $publicCertificate=Join-Path $outputPath 'ci-public-certificate.cer'
    Export-Certificate -Cert $certificate -FilePath $publicCertificate | Out-Null
    $trusted=Import-Certificate -FilePath $publicCertificate -CertStoreLocation Cert:\LocalMachine\TrustedPeople
    $signTool=Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe' | Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
    if(-not $signTool){throw 'Windows SDK SignTool is required for this isolated test.'}
    $testPackage=Join-Path $outputPath 'Radici-CI-TEST.msix'
    Copy-Item -LiteralPath $Package -Destination $testPackage
    & $signTool sign /fd SHA256 /sha1 $certificate.Thumbprint /s My $testPackage
    if($LASTEXITCODE -ne 0){throw 'Development package signing failed.'}
    Add-AppxPackage -Path $testPackage
    $installed=Get-AppxPackage -Name $name
    if(-not $installed){throw 'The test MSIX package was not installed.'}
    # The app uses its normal data directory. The sentinel must survive uninstall.
    New-Item -ItemType Directory -Path $dataPath -Force | Out-Null
    $sentinel=Join-Path $dataPath 'ci-preserve.txt'
    [System.IO.File]::WriteAllText($sentinel,'synthetic archive marker; must survive app uninstall')
    $before=(Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash
    $reportPath=Join-Path $outputPath 'window-ready.json'
    $imagePath=Join-Path $outputPath 'window.png'
    Add-Type -TypeDefinition @'
using System;using System.Runtime.InteropServices;
[ComImport,Guid("45BA127D-10A8-46EA-8AB7-56EA9078943C")]class RadiciActivationManager{}
[ComImport,Guid("2e941141-7f97-4756-ba1d-9decde894a3d"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]interface IRadiciActivationManager {
 [PreserveSig]int ActivateApplication([MarshalAs(UnmanagedType.LPWStr)]string app,[MarshalAs(UnmanagedType.LPWStr)]string args,uint options,out uint process);
}
public static class RadiciActivate {
 public static uint Start(string app,string args){uint process;int result=((IRadiciActivationManager)new RadiciActivationManager()).ActivateApplication(app,args,0,out process);Marshal.ThrowExceptionForHR(result);return process;}
}
'@
    $arguments='--smoke-report "'+$reportPath+'" --smoke-screenshot "'+$imagePath+'" --smoke-exit'
    $appPid=[RadiciActivate]::Start($installed.PackageFamilyName+'!Radici',$arguments)
    $appProcess=Get-Process -Id $appPid -ErrorAction SilentlyContinue
    $limit=(Get-Date).AddSeconds(130)
    while(-not (Test-Path -LiteralPath $reportPath) -and (Get-Date) -lt $limit){Start-Sleep -Milliseconds 500}
    if(-not (Test-Path -LiteralPath $reportPath)){throw 'The packaged desktop window did not report successful navigation.'}
    $window=Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if(-not $window.ready -or -not $window.interface_ready -or $window.package_identity -notlike 'Radici.Genealogy.Development_*'){throw 'The app did not load its interface with the expected package identity.'}
    if([System.IO.Path]::GetFullPath($window.data_root) -ne [System.IO.Path]::GetFullPath($dataPath)){throw 'The app used an unexpected data folder.'}
    if(-not (Test-Path -LiteralPath (Join-Path $dataPath 'Dati\trees.json'))){throw 'The actual archive was hidden in package virtualization.'}
    if($appProcess -and -not $appProcess.WaitForExit(40000)){throw 'Graceful application shutdown did not complete.'}
    Remove-AppxPackage -Package $installed.PackageFullName
    $installed=$null
    if((Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash -ne $before){throw 'Archive sentinel was changed or removed by uninstall.'}
    if(-not (Test-Path -LiteralPath (Join-Path $dataPath 'Dati\trees.json'))){throw 'The genealogy catalogue did not survive uninstall.'}
    [ordered]@{package_install=$true;native_window=$true;webview_navigation=$true;graceful_shutdown=$true;archive_survives_uninstall=$true;certificate_scope='temporary isolated CI only';store_signed=$false;window=$window} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputPath 'integration-report.json') -Encoding utf8
} finally {
    if($appProcess -and -not $appProcess.HasExited){$appProcess.CloseMainWindow() | Out-Null;$null=$appProcess.WaitForExit(10000)}
    if($installed){Remove-AppxPackage -Package $installed.PackageFullName -ErrorAction Continue}
    if($trusted){Remove-Item -LiteralPath ('Cert:\LocalMachine\TrustedPeople\'+$trusted.Thumbprint) -ErrorAction Continue}
    if($certificate){Remove-Item -LiteralPath ('Cert:\CurrentUser\My\'+$certificate.Thumbprint) -ErrorAction Continue}
}
