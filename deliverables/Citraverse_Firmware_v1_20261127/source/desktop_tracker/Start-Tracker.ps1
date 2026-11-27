param([string]$HostAddress='192.168.1.9',[string]$Port='COM8')
$trackerPython='C:\Python314\pythonw.exe'
if(-not(Test-Path $trackerPython)){$trackerPython=(Get-Command python.exe -ErrorAction Stop).Source}
Start-Process -FilePath $trackerPython -ArgumentList @(('"'+(Join-Path $PSScriptRoot 'launch.py')+'"'),'--connect','--host',$HostAddress,'--port',$Port) -WorkingDirectory $PSScriptRoot -WindowStyle Normal
