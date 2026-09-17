// Actual worker handler + pinned Pyodide, with Node adapters; not full browser UI QA.
// Usage: node tests/worker-flow.cjs /path/to/pyodide /path/to/photo.jpg
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const runtime=path.resolve(process.argv[2]),photo=process.argv[3];
 const {loadPyodide}=require(path.join(runtime,'pyodide.js'));
 const messages=[];let py;
 const ctx={console,Uint8Array,self:{},postMessage:m=>messages.push(m),
  importScripts:url=>assert.equal(url,'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js'),
  loadPyodide:async()=>py=await loadPyodide({indexURL:runtime+'/'}),
  fetch:async(url,options)=>{assert.match(url,/^python\/straighten\.py\?v=\d+$/);assert.equal(options.cache,'no-store');return {ok:true,text:async()=>fs.readFileSync('dist/python/straighten.py','utf8')}}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync('dist/python-worker.js','utf8'),ctx);
 const source=fs.readFileSync(photo),bytes=Uint8Array.from(source).buffer;
 await ctx.self.onmessage({data:{id:1,operation:'process',bytes}});
 const processed=messages.find(m=>m.id===1);assert.ok(processed?.ok,processed?.error);assert.equal(processed.result.status,'corrected');
 await ctx.self.onmessage({data:{id:2,operation:'export',bytes,params:processed.result.params}});
 const exported=messages.find(m=>m.id===2);assert.ok(exported?.ok,exported?.error);
 py.FS.writeFile('/tmp/exported.png',new Uint8Array(exported.bytes));
 const size=JSON.parse(py.runPython("import json\nfrom PIL import Image\njson.dumps(Image.open('/tmp/exported.png').size)"));
 assert.deepEqual(size,[processed.result.width,processed.result.height]);
 console.log(JSON.stringify({status:processed.result.status,engine:processed.result.evidence.engine,inputSHA256:processed.result.evidence.inputSHA256,dimensions:size,exportBytes:exported.bytes.byteLength}));
})().catch(e=>{console.error(e);process.exitCode=1});
