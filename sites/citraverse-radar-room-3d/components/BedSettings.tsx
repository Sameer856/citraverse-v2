'use client';
import {useEffect,useState} from 'react';
import {normalizeBed,bedPlacement} from '../lib/radar/bed.mjs';
import type {Mount} from './RadarScene';
export type Bed={enabled:boolean;width:number;length:number;height:number;inset:number};
export default function BedSettings({value,room,onSave}:{value:Bed;room:Mount;onSave:(value:Bed)=>void}){
 const [draft,setDraft]=useState(value),[message,setMessage]=useState('');const fitted=bedPlacement(value,room);
 useEffect(()=>setDraft(value),[value]);
 const save=()=>{try{onSave(normalizeBed(draft));setMessage('Bed layout saved in this browser.');}catch(e){setMessage((e as Error).message);}};
 return <details className="bed-settings"><summary>Room layout · bed along the right wall</summary><div><p>The headboard is at the far-right corner. The foot extends toward the near-right corner. This is a visual reference; it does not hide radar points or change fall thresholds.</p><label className="checkbox"><input type="checkbox" checked={draft.enabled} onChange={e=>setDraft(d=>({...d,enabled:e.target.checked}))}/>Show bed in the room</label><div className="form-grid">{([['width','Bed width (m)',.6,2.5],['length','Bed length (m)',1,2.5],['height','Mattress top above floor (m)',.2,1],['inset','Gap from right and far walls (m)',0,1]] as const).map(([key,label,min,max])=><label key={key}>{label}<input type="number" min={min} max={max} step={.05} value={Number.isFinite(draft[key])?draft[key]:''} onChange={e=>setDraft(d=>({...d,[key]:e.target.valueAsNumber}))}/></label>)}</div><p className="fine">{fitted.fitted?`Bed fitted to room: ${fitted.width.toFixed(2)} × ${fitted.length.toFixed(2)} m. `:''}Default size is a placeholder. Enter the real bed dimensions for an accurate room reference.</p><button className="outline" onClick={save}>Save bed layout</button>{message&&<p role="status">{message}</p>}</div></details>;
}
