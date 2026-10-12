param(
 [Parameter(Mandatory=$true)][string]$Library,
 [string]$Packet,
 [Parameter(Mandatory=$true)][string]$Output,
 [switch]$SoftReset
)
# Exclusive CH347 owner. Close the tracker/debug tool before running.
$ErrorActionPreference='Stop'
$dll=(Resolve-Path -LiteralPath $Library).Path
$assembly=[Reflection.Assembly]::LoadFrom($dll)
Add-Type -ReferencedAssemblies $dll -TypeDefinition @'
using System;
using System.Collections.Generic;
using HifMsgDataCollectionLib;
public class CustomCommandSink {
 public Queue<string> Replies = new Queue<string>();
 public int Frames;
 public void OnData(object sender, ReceiveDataEven e) {
  if(e.dataType==4) {Frames++;return;}
  if(e.payloadData==null)return;
  string value="{\"type\":"+e.dataType+",\"payload_base64\":\""+Convert.ToBase64String(e.payloadData)+"\"}";
  lock(Replies) {if(Replies.Count<32)Replies.Enqueue(value);}
 }
 public string Take() {lock(Replies)return Replies.Count>0?Replies.Dequeue():null;}
}
'@
if($SoftReset) {
 if($Packet){throw 'Choose either a packet or soft reset'}
 # SDK msghdl_host_reboot: HIF message 0x04, payload 0x01 = normal reset.
 [byte[]]$bytes=0xA5,0x40,0x15,0x04,0x01,0x00,0x01,0xE9,0xFB,0xFE,0xFF
} else {
 $bytes=[IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $Packet).Path)
 if($bytes.Length -ne 138 -or [BitConverter]::ToUInt32($bytes,6) -ne 0x31525643){throw 'Not a CVR1 request'}
}
$api=[Activator]::CreateInstance($assembly.GetType('HifMsgDataCollectionLib.HifMsgDataCollectionApi'))
$sink=[CustomCommandSink]::new()
$handler=[Delegate]::CreateDelegate([System.EventHandler[HifMsgDataCollectionLib.ReceiveDataEven]],$sink,'OnData')
$api.add_callback($handler)
$opened=$false;$started=$false;$replies=@()
try {
 $opened=$api.OpenSpiDevice(0,3)
 if(-not $opened){throw 'CH347 open failed; close other radar applications'}
 # Vendor API explicitly rejects SendData while CollectionDataing.
 $sendStatus=$api.SendData($bytes)
 $flags=[Reflection.BindingFlags]'Instance,NonPublic,Public'
 $processor=$api.GetType().GetField('hifPrc',$flags).GetValue($api)
 $protocol=$processor.GetType().GetField('hif',$flags).GetValue($processor)
 $ackData=$protocol.mmwMotionGetPayload()
 [byte[]]$ack=if($null -ne $ackData){$ackData.Clone()}else{@()}
 if($SoftReset){Start-Sleep -Seconds 2}
 $started=$api.StartCollectingData()
 if(-not $started){throw 'Collection failed'}
 Start-Sleep -Seconds 2
 while($null -ne ($reply=$sink.Take())) {$replies+=($reply | ConvertFrom-Json)}
 @{send_status=$sendStatus;ack_base64=[Convert]::ToBase64String($ack);frames=$sink.Frames;callbacks=$replies;note='Send status alone does not verify configuration. Require a matching CVR1 ACK.'} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Output -Encoding utf8
} finally {
 if($started){$null=$api.StopCollectingData()}
 if($opened){$null=$api.CloseSpiDevice(0)}
 $api.remove_callback($handler)
}
