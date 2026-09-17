const PythonEngine=(()=>{
 let worker=null,next=1,mode=null,pending=new Map();
 async function nativeMode(){
  if(!mode)mode=fetch('runtime.json').then(r=>r.ok?r.json():{}).then(r=>r.engine==='native-python').catch(()=>false);
  return mode;
 }
 function start(){
  if(worker)return;
  worker=new Worker('python-worker.js?v=10');
  worker.onmessage=({data})=>{
   if(data.progress){const status=document.getElementById('detail');if(status)status.textContent=data.progress;return;}
   const job=pending.get(data.id);if(!job)return;pending.delete(data.id);clearTimeout(job.timer);
   data.ok?job.resolve({result:data.result,blob:new Blob([data.bytes],{type:'image/png'})}):job.reject(Error(data.error));
  };
  worker.onerror=()=>reset('Python could not start. Check your internet connection and reload to retry.');
 }
 function reset(reason){if(worker)worker.terminate();worker=null;for(const job of pending.values()){clearTimeout(job.timer);job.reject(Error(reason));}pending.clear();}
 async function request(operation,file,params){
  if(await nativeMode()){
   const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),300000);
   try{
    const response=await fetch('/api/'+operation,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-Correction':JSON.stringify(params||{})},body:file,signal:controller.signal});
    if(!response.ok){const error=await response.json();throw Error(error.error||'Python processing failed.');}
    if(operation==='export')return {blob:await response.blob()};
    const data=await response.json(),bytes=Uint8Array.from(atob(data.preview),c=>c.charCodeAt(0));return {result:data.result,blob:new Blob([bytes],{type:'image/png'})};
   }finally{clearTimeout(timer);}
  }
  const bytes=await file.arrayBuffer();start();const id=next++;
  return new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>reset('Python processing timed out. Try one photo at a time; full-resolution output was not reduced.'),300000);
   pending.set(id,{resolve,reject,timer});worker.postMessage({id,operation,bytes,params},[bytes]);
  });
 }
 return {process:file=>request('process',file),export:(file,params)=>request('export',file,params),reset};
})();
