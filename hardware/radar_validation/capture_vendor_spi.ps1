param(
    [Parameter(Mandatory=$true)][string]$Library,
    [Parameter(Mandatory=$true)][string]$Output,
    [ValidateRange(1,60)][int]$Seconds = 10
)
$ErrorActionPreference = 'Stop'
if(Test-Path -LiteralPath $Output) { throw 'Output already exists' }
$radarDll=(Resolve-Path -LiteralPath $Library).Path
$radarAssembly=[Reflection.Assembly]::LoadFrom($radarDll)
Add-Type -ReferencedAssemblies $radarDll -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Diagnostics;
using HifMsgDataCollectionLib;
public class RadarCaptureItem {
 public double elapsed_s;
 public byte data_type;
 public uint frame_index;
 public uint frame_length;
 public string vendor_timestamp;
 public string payload_base64;
}
public class RadarCaptureSink {
 public List<RadarCaptureItem> Items = new List<RadarCaptureItem>();
 public Stopwatch Clock = new Stopwatch();
 public int Dropped = 0;
 public void OnData(object sender, ReceiveDataEven e) {
  byte[] data=e.payloadData;
  var item=new RadarCaptureItem { elapsed_s=Clock.Elapsed.TotalSeconds,
    data_type=e.dataType, frame_index=e.frameIndex, frame_length=e.frameLen,
    vendor_timestamp=e.timeStamp,
    payload_base64=data == null ? null : Convert.ToBase64String(data) };
  lock(Items) { if(Items.Count<10000) Items.Add(item); else Dropped++; }
 }
 public RadarCaptureItem[] Snapshot() { lock(Items) return Items.ToArray(); }
}
"@
$radarApi=[Activator]::CreateInstance($radarAssembly.GetType('HifMsgDataCollectionLib.HifMsgDataCollectionApi'))
$radarSink=[RadarCaptureSink]::new()
$radarHandler=[Delegate]::CreateDelegate([System.EventHandler[HifMsgDataCollectionLib.ReceiveDataEven]], $radarSink, 'OnData')
$radarApi.add_callback($radarHandler)
$radarResult=[ordered]@{utc_start=(Get-Date).ToUniversalTime().ToString('o'); library_version=$radarApi.GetLibVersion(); library_sha256=([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([IO.File]::ReadAllBytes($radarDll))).Replace('-','')); requested_spi_frequency_mode=3; documented_requested_clock_hz=7500000; clock_measured=$false; calls=@(); error=$null}
$radarOpened=$false
$radarStarted=$false
try {
 $radarOpened=$radarApi.OpenSpiDevice(0,3)
 $radarResult.calls+=@{api='OpenSpiDevice(0,3)'; result=$radarOpened}
 if(-not $radarOpened){throw 'SPI device open failed'}
 $radarSink.Clock.Start()
 $radarStarted=$radarApi.StartCollectingData()
 $radarResult.calls+=@{api='StartCollectingData';result=$radarStarted}
 if(-not $radarStarted){throw 'Collection start failed'}
 Start-Sleep -Seconds $Seconds
} catch { $radarResult.error=$_.Exception.ToString() }
finally {
 if($radarStarted){$radarResult.calls+=@{api='StopCollectingData';result=$radarApi.StopCollectingData()}}
 $radarSink.Clock.Stop()
 if($radarOpened){$radarResult.calls+=@{api='CloseSpiDevice(0)';result=$radarApi.CloseSpiDevice(0)}}
 $radarApi.remove_callback($radarHandler)
 $radarResult.duration_s=$radarSink.Clock.Elapsed.TotalSeconds
 $radarResult.callbacks=$radarSink.Snapshot()
 $radarResult.callback_count=$radarResult.callbacks.Count
 $radarResult.dropped_callbacks=$radarSink.Dropped
 $radarResult | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $Output -Encoding utf8
 [pscustomobject]$radarResult | Select-Object utc_start,library_version,calls,error,duration_s,callback_count,dropped_callbacks | ConvertTo-Json -Depth 4
}
