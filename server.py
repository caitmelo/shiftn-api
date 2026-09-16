"""Local-only Python HTTP server for the supplied frontend. Run: python3 server.py."""
import base64
import io
import json
import sys
import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'dist'/'python'))
import straighten

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT/'dist'),**kwargs)
    def json_response(self,value,status=200):
        data=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if urlsplit(self.path).path=='/runtime.json':return self.json_response({'engine':'native-python'})
        return super().do_GET()
    def do_POST(self):
        # Local endpoint only; reject cross-origin uploads and unsupported requests.
        if self.headers.get('Origin') not in (None,'http://127.0.0.1:8080','http://localhost:8080'):
            return self.json_response({'error':'Cross-origin requests are not allowed.'},403)
        if self.path not in ('/api/process','/api/export'):return self.json_response({'error':'Unknown endpoint.'},404)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>40*1024*1024:raise ValueError('Upload must be between 1 byte and 40 MB.')
            raw=self.rfile.read(size)
            if len(raw)!=size:raise ValueError('Incomplete upload.')
            if self.path=='/api/process':
                result,preview=straighten.process_bytes(raw)
                return self.json_response({'result':result,'preview':base64.b64encode(preview).decode()})
            params=json.loads(self.headers.get('X-Correction','{}'))
            image=straighten.export_bytes(raw,params)
            self.send_response(200);self.send_header('Content-Type','image/png');self.send_header('Content-Length',str(len(image)));self.end_headers();self.wfile.write(image)
        except Exception as e:return self.json_response({'error':str(e)},400)

if __name__=='__main__':
    server=HTTPServer(('127.0.0.1',8080),Handler)
    print('Straightline Python: http://127.0.0.1:8080 (Ctrl+C to stop)',flush=True)
    if '--no-browser' not in sys.argv:threading.Timer(.5,lambda:webbrowser.open('http://127.0.0.1:8080')).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
