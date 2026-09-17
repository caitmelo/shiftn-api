/* This worker only transports bytes. All detection and rendering run in Python. */
let ready;
function initialize(){
 if(!ready)ready=(async()=>{
  postMessage({progress:'Loading Python for the first run…'});
  const indexURL='https://cdn.jsdelivr.net/pyodide/v0.27.7/full/';
  importScripts(indexURL+'pyodide.js');
  const py=await loadPyodide({indexURL});
  await py.loadPackage(['numpy','pillow']);
  const response=await fetch('python/straighten.py?v=12',{cache:'no-store'});
  if(!response.ok)throw Error('Could not load the Python straightening engine.');
  py.FS.writeFile('/home/pyodide/straighten.py',await response.text());
  py.runPython("import straighten, json\nassert straighten.VERSION == 'python-1.3', 'Engine version mismatch. Reload the page.'");
  return py;
 })().catch(e=>{ready=null;throw e});
 return ready;
}
self.onmessage=async({data})=>{
 let py;
 try{
  py=await initialize();
  py.FS.writeFile('/tmp/input-photo',new Uint8Array(data.bytes));
  py.globals.set('request_params',JSON.stringify(data.params||{}));
  let result;
  if(data.operation==='export'){
   py.runPython("from pathlib import Path\nPath('/tmp/output-photo').write_bytes(straighten.export_bytes(Path('/tmp/input-photo').read_bytes(), json.loads(request_params)))");
  }else if(data.operation==='process'){
   const metadata=py.runPython("from pathlib import Path\nresult, preview = straighten.process_bytes(Path('/tmp/input-photo').read_bytes())\nPath('/tmp/output-photo').write_bytes(preview)\ndel preview\njson.dumps(result)");
   result=JSON.parse(metadata);
  }else throw Error('Unknown Python operation.');
  const bytes=py.FS.readFile('/tmp/output-photo');
  postMessage({id:data.id,ok:true,result,bytes:bytes.buffer},[bytes.buffer]);
 }catch(e){postMessage({id:data.id,ok:false,error:String(e.message||e)});}
 finally{
  if(py){for(const path of ['/tmp/input-photo','/tmp/output-photo'])try{py.FS.unlink(path)}catch{}
   py.runPython('import gc\ngc.collect()');}
 }
};
