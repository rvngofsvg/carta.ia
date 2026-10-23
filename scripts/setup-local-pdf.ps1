# Official portable WeasyPrint, isolated to this checkout. No global install.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$archivePath = Join-Path $runtimeDir 'weasyprint-windows.zip'
Invoke-WebRequest 'https://github.com/Kozea/WeasyPrint/releases/download/v69.0/weasyprint-windows.zip' -OutFile $archivePath
Expand-Archive -LiteralPath $archivePath -DestinationPath (Join-Path $runtimeDir 'weasyprint-69') -Force
& (Join-Path $runtimeDir 'weasyprint-69/dist/weasyprint.exe') --version
