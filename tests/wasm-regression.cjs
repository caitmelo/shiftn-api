// Usage: node tests/wasm-regression.cjs /path/to/pyodide-0.27.7 /path/to/photo.jpg
// Runtime directory must contain Pyodide and its NumPy/Pillow wheels.
const fs=require('node:fs'),path=require('node:path');
(async()=>{
 const runtime=path.resolve(process.argv[2]),photo=process.argv[3];
 const {loadPyodide}=require(path.join(runtime,'pyodide.js'));
 const py=await loadPyodide({indexURL:runtime+'/'});
 await py.loadPackage(['numpy','pillow']);
 py.FS.writeFile('/home/pyodide/straighten.py',fs.readFileSync('dist/python/straighten.py'));
 for(const name of ['test_engine','test_consensus','test_horizontal'])py.FS.writeFile('/home/pyodide/'+name+'.py',fs.readFileSync('python_tests/'+name+'.py'));
 py.runPython("import unittest, test_engine, test_consensus, test_horizontal\nsuite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(m) for m in (test_engine,test_consensus,test_horizontal)])\nassert unittest.TextTestRunner().run(suite).wasSuccessful()");
 if(photo){
  py.FS.writeFile('/tmp/input-photo',fs.readFileSync(photo));
  const result=py.runPython("import straighten,json,io\nfrom pathlib import Path\nraw=Path('/tmp/input-photo').read_bytes()\nr,preview=straighten.process_bytes(raw)\nassert r['status']=='corrected',r\noutput=straighten.export_bytes(raw,r['params'])\nassert straighten.Image.open(io.BytesIO(output)).size==(r['width'],r['height'])\nPath('/tmp/corrected.png').write_bytes(output)\njson.dumps(r)");
  console.log(result);
  if(process.env.REGRESSION_OUTPUT)fs.writeFileSync(process.env.REGRESSION_OUTPUT,py.FS.readFile('/tmp/corrected.png'));
 }
})().catch(e=>{console.error(e);process.exitCode=1});
