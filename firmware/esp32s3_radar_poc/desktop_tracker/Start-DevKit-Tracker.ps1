param([string]$Recording)
if (-not $Recording) {
    $storage = Join-Path $env:USERPROFILE 'Downloads\mmwave\RadarDebugTool_EN_V1.0.0.9\DataStorage'
    $latest = Get-ChildItem -LiteralPath $storage -Recurse -Filter '*_rawData.bin' |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { throw 'Enable Auto save data in RadarDebugTool first.' }
    $Recording = $latest.FullName
}
$trackerPython = 'C:\Python314\pythonw.exe'
if (-not (Test-Path $trackerPython)) { $trackerPython = (Get-Command python.exe -ErrorAction Stop).Source }
Start-Process -FilePath $trackerPython -ArgumentList @(
    ('"' + (Join-Path $PSScriptRoot 'launch_devkit.py') + '"'),
    '--recording', ('"' + $Recording + '"')
) -WorkingDirectory $PSScriptRoot
