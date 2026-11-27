param([Parameter(Mandatory=$true)][string]$Library,[Parameter(Mandatory=$true)][int]$OwnerPid)
$ErrorActionPreference='Stop'
[Console]::Error.WriteLine('Loading vendor assembly')
$dll=(Resolve-Path -LiteralPath $Library).Path
$assembly=[Reflection.Assembly]::LoadFrom($dll)
Add-Type -ReferencedAssemblies $dll -TypeDefinition @'
using System;
using System.Collections.Generic;
using HifMsgDataCollectionLib;
public class LiveSpiSink {
 public volatile bool StopRequested;
 public void WatchInput() { Console.In.ReadLine(); StopRequested=true; }
 public void StartInputWatcher() { var t=new System.Threading.Thread(WatchInput);t.IsBackground=true;t.Start(); }
 public Queue<string> Items = new Queue<string>();
 public int Dropped;
 public void OnData(object sender, ReceiveDataEven e) {
  if(e.dataType!=4 || e.payloadData==null) return;
  long ms=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
  string s="{\"frame\":"+e.frameIndex+",\"words\":"+e.frameLen+",\"timestamp_ms\":"+ms+",\"data\":\""+Convert.ToBase64String(e.payloadData)+"\"}";
  lock(Items) { if(Items.Count>=64){Items.Dequeue();Dropped++;} Items.Enqueue(s); }
 }
 public string Take() { lock(Items) return Items.Count>0?Items.Dequeue():null; }
}
'@
$api=[Activator]::CreateInstance($assembly.GetType('HifMsgDataCollectionLib.HifMsgDataCollectionApi'))
[Console]::Error.WriteLine('Vendor API created')
$sink=[LiveSpiSink]::new()
$handler=[Delegate]::CreateDelegate([System.EventHandler[HifMsgDataCollectionLib.ReceiveDataEven]],$sink,'OnData')
$api.add_callback($handler)
$opened=$false;$started=$false
try {
 $opened=$api.OpenSpiDevice(0,3)
 [Console]::Error.WriteLine('SPI open: '+$opened)
 if(-not $opened){throw 'Cannot open CH347 SPI. Disconnect RadarDebugTool first.'}
 $started=$api.StartCollectingData()
 [Console]::Error.WriteLine('Collecting: '+$started)
 if(-not $started){throw 'SPI acquisition failed to start'}
 [Console]::Out.WriteLine('{"status":"ready","clock_selector":3}')
 $sink.StartInputWatcher()
 $owner=[Diagnostics.Process]::GetProcessById($OwnerPid)
 while(-not $sink.StopRequested) {
  if($owner.HasExited){break}
  while($null -ne ($item=$sink.Take())){[Console]::Out.WriteLine($item)}
  [Console]::Out.Flush()
  Start-Sleep -Milliseconds 5
 }
} catch { [Console]::Out.WriteLine((@{error=$_.Exception.Message}|ConvertTo-Json -Compress)) }
finally {
 if($started){$null=$api.StopCollectingData()}
 if($opened){$null=$api.CloseSpiDevice(0)}
 $api.remove_callback($handler)
 [Console]::Out.WriteLine((@{status='closed';callback_drops=$sink.Dropped}|ConvertTo-Json -Compress))
}
