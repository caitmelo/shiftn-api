"""Self-hosted single-worker API + frontend. Configure HTTPS at the reverse proxy."""
import asyncio
import base64
from contextlib import asynccontextmanager
import hmac
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
from PIL import UnidentifiedImageError
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from api.watermarks import load_cleaner
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'dist/python'))
import straighten


class ResultStore:
    def __init__(self,root,ttl=3600,max_bytes=1024**3):
        self.root=Path(root);self.ttl=ttl;self.max_bytes=max_bytes;self.items={}
    def purge(self):
        now=time.monotonic()
        for key in list(self.items):
            if self.items[key]['expires']<=now:self.delete(key)
    def put(self,content):
        self.purge()
        if sum(i['bytes'] for i in self.items.values())+len(content)>self.max_bytes:raise ValueError('Result storage is full. Download/clear earlier results or wait for expiry.')
        key=secrets.token_urlsafe(32);path=self.root/(key+'.png');path.write_bytes(content);path.chmod(0o600)
        self.items[key]={'path':path,'bytes':len(content),'expires':time.monotonic()+self.ttl}
        return key
    def get(self,key):
        self.purge();return self.items.get(key)
    def delete(self,key):
        record=self.items.pop(key,None)
        if record:record['path'].unlink(missing_ok=True)


def create_app(cleaner=None,api_key=None,local_only=None):
    key=os.getenv('STRAIGHTLINE_API_KEY','') if api_key is None else api_key
    local=os.getenv('STRAIGHTLINE_LOCAL_ONLY')=='1' if local_only is None else local_only
    if not key and not local:raise RuntimeError('Set STRAIGHTLINE_API_KEY, or STRAIGHTLINE_LOCAL_ONLY=1 and bind only to 127.0.0.1.')
    @asynccontextmanager
    async def lifespan(app):
        with tempfile.TemporaryDirectory(prefix='straightline-') as directory:
            app.state.store=ResultStore(directory);app.state.gate=asyncio.Lock();app.state.cleaner=cleaner
            app.state.watermark_error=None
            if cleaner is None and os.getenv('WATERMARK_ENABLED')=='1':
                try:app.state.cleaner=await run_in_threadpool(load_cleaner,ROOT/'models')
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).exception('Watermark models failed to load')
                    app.state.watermark_error='Watermark models are not ready. Check server setup.'
            async def sweep():
                while True:
                    await asyncio.sleep(60);app.state.store.purge()
            task=asyncio.create_task(sweep())
            try:yield
            finally:
                task.cancel()
                try:await task
                except asyncio.CancelledError:pass
    app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)

    @app.middleware('http')
    async def access(request,call_next):
        if key:
            value=request.headers.get('Authorization','');valid=False
            if value.startswith('Basic '):
                try:
                    credentials=base64.b64decode(value[6:],validate=True).decode();user,secret=credentials.split(':',1)
                    valid=user=='straightline' and hmac.compare_digest(secret.encode(),key.encode())
                except (ValueError,UnicodeError):pass
            if not valid:return Response('Authentication required',401,headers={'WWW-Authenticate':'Basic realm="Straightline", charset="UTF-8"'})
        elif request.client and request.client.host not in ('127.0.0.1','::1','testclient'):
            return JSONResponse({'error':'Local-only mode rejects remote clients.'},403)
        if request.method not in ('GET','HEAD','OPTIONS'):
            # Same origin only. JSON/octet-stream requests prevent simple-form CSRF.
            origin=request.headers.get('Origin')
            expected=os.getenv('PUBLIC_ORIGIN') or str(request.base_url).rstrip('/')
            if origin and origin.rstrip('/')!=expected:return JSONResponse({'error':'Cross-origin requests are not allowed.'},403)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff'
        return response

    @app.get('/runtime.json')
    async def runtime():
        return {'engine':'server-python','version':straighten.VERSION,'watermarkRemoval':app.state.cleaner is not None,'watermarkMessage':app.state.watermark_error or 'Watermark removal is not enabled on this server.'}

    @app.get('/api/health')
    async def health():return {'ok':True,'watermarkReady':app.state.cleaner is not None}

    def process(raw,remove):
        im=straighten.decode(raw);wm={'status':'disabled','removed':0}
        if remove:im,wm=app.state.cleaner.clean(im)
        result=straighten.analyse(im);geometry=result['status']
        if geometry=='corrected':
            try:straighten.mapping(*im.size,result['params'])
            except ValueError as exc:result=dict(status='unresolved',params=dict(straighten.BASE),message=str(exc));geometry='unresolved'
        output=straighten.render(im,result['params'])
        preview=output.copy();preview.thumbnail((1600,1600),straighten.Image.Resampling.LANCZOS)
        result.update(width=im.width,height=im.height,watermark=wm,straighteningStatus=geometry)
        if wm['status']=='removed':
            result['status']='corrected' if geometry=='corrected' else 'cleaned'
            result['message']='Watermark area restored. '+result['message']
        elif wm['status']=='uncertain':result['message']='Watermark detection was uncertain; no watermark removal applied. '+result['message']
        elif wm['status']=='no_detection':result['message']='No confident watermark detected. '+result['message']
        return result,straighten.png(preview),straighten.png(output)

    @app.post('/api/process')
    async def process_photo(request:Request):
        if app.state.gate.locked():return JSONResponse({'error':'Server is busy. Please retry shortly.'},429,headers={'Retry-After':'5'})
        async with app.state.gate:
            remove=request.headers.get('X-Remove-Watermarks','false')
            if remove not in ('true','false'):return JSONResponse({'error':'Invalid watermark option.'},400)
            if remove=='true' and app.state.cleaner is None:return JSONResponse({'error':'Watermark removal is unavailable; no cleanup was performed.'},503)
            if request.headers.get('Content-Type','').split(';')[0]!='application/octet-stream':return JSONResponse({'error':'Send image bytes as application/octet-stream.'},415)
            data=bytearray()
            async for chunk in request.stream():
                if len(data)+len(chunk)>40*1024*1024:return JSONResponse({'error':'Upload exceeds 40 MB.'},413)
                data.extend(chunk)
            if not data:return JSONResponse({'error':'Empty upload.'},400)
            try:
                result,preview,output=await run_in_threadpool(process,bytes(data),remove=='true')
                result['exportId']=app.state.store.put(output)
                return {'result':result,'preview':base64.b64encode(preview).decode()}
            except (ValueError,UnidentifiedImageError) as exc:return JSONResponse({'error':str(exc)},400)
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Image processing failed')
                return JSONResponse({'error':'Processing failed. No cleaned result was produced.'},500)

    @app.get('/api/results/{job_id}')
    async def result_image(job_id:str):
        record=app.state.store.get(job_id)
        if not record:raise HTTPException(410,'Result expired. Re-upload the photo to process it again.')
        # Read before returning so concurrent cleanup cannot unlink a streamed file.
        return Response(record['path'].read_bytes(),media_type='image/png')

    @app.delete('/api/results/{job_id}')
    async def delete_result(job_id:str):app.state.store.delete(job_id);return Response(status_code=204)

    app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='frontend')
    return app
