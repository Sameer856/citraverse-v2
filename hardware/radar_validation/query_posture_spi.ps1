param([string]$Library,[string]$Output)
$ErrorActionPreference='Stop'
$assembly=[Reflection.Assembly]::LoadFrom((Resolve-Path -LiteralPath $Library).Path)
$api=[Activator]::CreateInstance($assembly.GetType('HifMsgDataCollectionLib.HifMsgDataCollectionApi'))
$results=@()
$opened=$false
try {
 $opened=$api.OpenSpiDevice(0,3)
 if(-not $opened){throw 'SPI open failed'}
 # Exact read-only examples from HIF Reference Manual V1.2 appendix, pp108-109.
 foreach($query in @(
   @{name='code_and_configuration_version';hex='A5 04 15 00 01 40 42 A8 FF FE BF'},
   @{name='heartbeat_tick';hex='A5 D3 15 01 01 70 40 AA FE FE 8F'},
   @{name='configuration_version';hex='A5 24 15 00 01 20 40 AA FF FE DF'},
   @{name='code_version_retry';hex='A5 04 15 00 01 40 42 A8 FF FE BF'}
 )) {
  [byte[]]$packet=$query.hex.Split(' ') | ForEach-Object {[Convert]::ToByte($_,16)}
  $status=$api.SendData($packet)
  $results+=@{query=$query.name;packet=$query.hex;status=$status;utc=[DateTime]::UtcNow.ToString('o')}
  Write-Output ($results[-1] | ConvertTo-Json -Compress)
 }
} finally {
 if($opened){$null=$api.CloseSpiDevice(0)}
 @{transport='CH347 SPI';clock_selector=3;results=$results} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Output -Encoding utf8
}
