// Browser-only verification, using Chrome's CDP and Node's built-in WebSocket.
// Usage: node scripts/qwen_cast_browser.mjs <port> <absolute index.html path> <receipt path>
import {writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const [port, page, receipt] = process.argv.slice(2);
const base = `http://127.0.0.1:${Number(port)}`;
const target = await (await fetch(`${base}/json/new?${encodeURIComponent(pathToFileURL(page).href)}`, {method:'PUT'})).json();
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { ws.onopen=resolve; ws.onerror=reject; });
let serial=0;
const pending=new Map();
ws.onmessage=event=>{const data=JSON.parse(event.data);if(data.id){const p=pending.get(data.id);pending.delete(data.id);if(data.error)p.reject(Error(JSON.stringify(data.error)));else p.resolve(data.result);}};
function rpc(method,params={}){return new Promise((resolve,reject)=>{const id=++serial;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});}
await rpc('Runtime.enable');
const response=await rpc('Runtime.evaluate',{awaitPromise:true,returnByValue:true,expression:`(async()=>{
  if(document.readyState!=='complete') await new Promise(r=>addEventListener('load',r,{once:true}));
  const audios=[...document.querySelectorAll('audio')];
  if(audios.length!==9)throw Error('Expected nine audio players, got '+audios.length);
  const results=[];
  for(const a of audios){
    a.muted=true;
    if(a.readyState<1)await new Promise((resolve,reject)=>{a.onloadedmetadata=resolve;a.onerror=()=>reject(Error('Metadata failed'));a.load()});
    await a.play();
    await new Promise((resolve,reject)=>{const end=performance.now()+5000;const check=()=>{if(a.currentTime>0.1)resolve();else if(a.error||performance.now()>end)reject(Error('Playback did not advance'));else setTimeout(check,50)};check()});
    results.push({sample:a.closest('section').querySelector('h2').textContent,source:a.getAttribute('src'),duration:a.duration,played:a.currentTime,error:a.error});
    a.pause();a.currentTime=0;
  }
  const selects=[...document.querySelectorAll('select')];
  if(selects.length!==72||selects.some(s=>s.value!==''))throw Error('Ratings not blank');
  const textareas=document.querySelectorAll('textarea');
  if(textareas.length!==9)throw Error('Missing notes');
  return {players:results,ratings:selects.length,blank:true,commonText:!!document.querySelector('details pre'),title:document.title,userAgent:navigator.userAgent};
})()`});
if(response.exceptionDetails)throw Error(JSON.stringify(response.exceptionDetails));
await writeFile(receipt,JSON.stringify({verified_at:new Date().toISOString(),...response.result.value},null,2),'utf8');
console.log(JSON.stringify(response.result.value));
ws.close();
