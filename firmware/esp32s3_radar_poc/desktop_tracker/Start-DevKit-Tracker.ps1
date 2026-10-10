param([string]$Recording,[switch]$DirectSpi)
if(-not $DirectSpi -and -not $Recording){
    $storage=Join-Path $env:USERPROFILE 'Downloads\mmwave\RadarDebugTool_EN_V1.0.0.9\DataStorage'
    $latest=Get-ChildItem -LiteralPath $storage -Recurse -Filter '*_rawData.bin' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if(-not $latest){throw 'No recording found. Use -DirectSpi only after closing the vendor SPI connection.'}
    $Recording=$latest.FullName
}
if($DirectSpi -and $Recording){throw 'Choose either direct SPI or a recording, not both.'}
$trackerPython = 'C:\Python314\pythonw.exe'
if (-not (Test-Path $trackerPython)) { $trackerPython = (Get-Command python.exe -ErrorAction Stop).Source }
$trackerArgs=@(('"' + (Join-Path $PSScriptRoot 'launch_devkit.py') + '"'))
if($Recording){$trackerArgs+=@('--recording',('"'+$Recording+'"'))}
Start-Process -FilePath $trackerPython -ArgumentList $trackerArgs -WorkingDirectory $PSScriptRoot
