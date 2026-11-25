const BASE='https://citraverse-pcb-route-avebsk4vna-el.a.run.app/v1/devices/citra-pcb-68ee8f588598';
export async function radarRoute(request:Request,env:{RADAR_APP_KEY?:string}):Promise<Response|null>{
 const url=new URL(request.url);
 const routes:Record<string,string>={'/api/radar-ws':'/ws','/api/radar-status':'/api/status','/api/archive-status':'/archive/status','/api/radar-tuning':'/api/ota'};
 const path=routes[url.pathname];if(!path)return null;
 const headers={'Cache-Control':'no-store'};
 const tuning=url.pathname==='/api/radar-tuning';
 if(request.method!=='GET'&&!(tuning&&request.method==='POST'))return new Response('Method not allowed',{status:405,headers});
 // Production is owner-private, with an additional identity check on every data route.
 const local=import.meta.env.DEV&&['127.0.0.1','localhost'].includes(url.hostname);
 if(!local&&!request.headers.get('oai-authenticated-user-id'))return new Response('Sign in to view this sensor',{status:401,headers});
 if(!env.RADAR_APP_KEY)return Response.json({error:'Sensor connection is not configured'},{status:503,headers});
 if(url.search)return new Response('Unexpected query',{status:400,headers});
 const auth={Authorization:`Bearer ${env.RADAR_APP_KEY}`};
 try{
  if(path==='/ws'){
   if(request.headers.get('upgrade')?.toLowerCase()!=='websocket')return new Response('WebSocket required',{status:426,headers});
   if(request.headers.get('origin')!==url.origin)return new Response('Origin not allowed',{status:403,headers});
   const response=await fetch(BASE+path,{headers:{...auth,Upgrade:'websocket'},redirect:'manual'});
   if(response.status!==101)return new Response('Radar stream unavailable',{status:502,headers});
   return response;
  }
  if(tuning){
   let body:Record<string,unknown>={action:'status'};
   if(request.method==='POST'){
    if(request.headers.get('origin')!==url.origin)return Response.json({error:'Origin not allowed'},{status:403,headers});
    if(!request.headers.get('content-type')?.startsWith('application/json'))return Response.json({error:'JSON required'},{status:415,headers});
    const text=await request.text();if(text.length>2048)return Response.json({error:'Request too large'},{status:413,headers});
    try{const value=JSON.parse(text);if(!value||Array.isArray(value)||typeof value!=='object')throw Error();body=value;}catch{return Response.json({error:'Invalid JSON'},{status:400,headers});}
    if(!['apply','restore','defaults','save','reboot'].includes(String(body.action)))return Response.json({error:'Unsupported action'},{status:400,headers});
   }
   // Backward-compatible authenticated device-operation transport. The PCB
   // dispatches this operation separately; firmware-update manifests are unchanged.
   const response=await fetch(BASE+path,{method:'POST',headers:{...auth,'Content-Type':'application/json'},body:JSON.stringify({...body,operation:'radar_tuning'}),redirect:'manual',signal:AbortSignal.timeout(12000)});
   return new Response(response.body,{status:response.status,headers:{...headers,'Content-Type':'application/json'}});
  }
  const response=await fetch(BASE+path,{headers:auth,redirect:'manual',signal:AbortSignal.timeout(10000)});
  if(!response.ok)return Response.json({error:'Sensor temporarily unavailable'},{status:response.status===504?504:502,headers});
  return new Response(response.body,{headers:{...headers,'Content-Type':'application/json'}});
 }catch(error){console.warn('Radar upstream failed',error instanceof Error?error.message:'unknown');return Response.json({error:'GCP connection interrupted'},{status:502,headers});}
}
