param(
    [Parameter(Mandatory=$true)][string]$HostSample,
    [string]$IdfPath = 'C:\Espressif\frameworks\esp-idf-v5.5.5',
    [string]$ToolsPath = 'C:\Espressif',
    [ValidateSet('build','menuconfig','flash','monitor')][string]$Action = 'build',
    [string]$Port
)
$ErrorActionPreference='Stop'
$radarCandidates=@(
    (Join-Path $HostSample 'host_driver'),
    (Join-Path $HostSample 'ESP32\ESP32S3Host\host_driver'),
    (Join-Path $HostSample 'HostSample_V1.0.1\ESP32\ESP32S3Host\host_driver')
)
$radarDriver=$radarCandidates | Where-Object {Test-Path (Join-Path $_ 'cmd_api\host_driver.h')} | Select-Object -First 1
if(-not $radarDriver){throw 'Cannot locate ESP32S3Host/host_driver under HostSample'}
if(($Action -eq 'flash' -or $Action -eq 'monitor') -and -not $Port){throw 'Provide the identified ESP32 port, not the radar COM port'}
$env:IDF_PATH=$IdfPath
$env:IDF_TOOLS_PATH=$ToolsPath
$radarPython=Join-Path $ToolsPath 'python_env\idf5.5_py3.11_env\Scripts\python.exe'
if(-not(Test-Path $radarPython)){throw 'ESP-IDF 5.5 Python environment missing; use an installed IDF 5.5 environment'}
$env:IDF_PYTHON_ENV_PATH=Split-Path (Split-Path $radarPython)
$env:PYTHONPATH=$null
$env:PYTHONNOUSERSITE='1'
$env:CCACHE_ENABLE='0'
$env:RADAR_HOST_DRIVER=(Resolve-Path $radarDriver).Path
$radarBins=@((Split-Path $radarPython))
foreach($tool in @(@('cmake','cmake.exe'),@('ninja','ninja.exe'),@('xtensa-esp-elf','xtensa-esp-elf-gcc.exe'))) {
    $binary=Get-ChildItem (Join-Path $ToolsPath ('tools\'+$tool[0])) -Recurse -Filter $tool[1] | Sort-Object FullName -Descending | Select-Object -First 1
    if(-not $binary){throw ('Missing tool '+$tool[1])}
    $radarBins+=$binary.DirectoryName
    if($tool[0] -eq 'ninja'){$radarNinja=$binary.FullName}
}
$env:PATH=($radarBins -join ';')+';'+$env:PATH
# Process-local ownership exceptions only; never changes global Git configuration.
$radarGitCount=0
if($env:GIT_CONFIG_COUNT){$radarGitCount=[int]$env:GIT_CONFIG_COUNT}
foreach($safe in @($IdfPath,(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path)) {
    [Environment]::SetEnvironmentVariable("GIT_CONFIG_KEY_$radarGitCount",'safe.directory','Process')
    [Environment]::SetEnvironmentVariable("GIT_CONFIG_VALUE_$radarGitCount",$safe.Replace('\','/'),'Process')
    $radarGitCount++
}
$env:GIT_CONFIG_COUNT=[string]$radarGitCount
Push-Location $PSScriptRoot
try {
    $radarArgs=@((Join-Path $IdfPath 'tools\idf.py'),'-DIDF_TARGET=esp32s3',('-DCMAKE_MAKE_PROGRAM='+$radarNinja.Replace('\','/')))
    if($Port){$radarArgs+=@('-p',$Port)}
    $radarArgs+=$Action
    & $radarPython @radarArgs
    if($LASTEXITCODE -ne 0){throw "idf.py failed with exit code $LASTEXITCODE"}
} finally {Pop-Location}
