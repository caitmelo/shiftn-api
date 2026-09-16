import sys,threading,unittest,json,io
from pathlib import Path
from urllib.request import Request,urlopen
from http.server import HTTPServer
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Handler

class LocalApiTests(unittest.TestCase):
    def test_frontend_process_and_full_resolution_export(self):
        srv=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{srv.server_port}'
        try:
            self.assertIn(b'python-bridge.js',urlopen(url).read())
            self.assertEqual(json.load(urlopen(url+'/runtime.json'))['engine'],'native-python')
            buf=io.BytesIO();Image.new('RGB',(320,240),'gray').save(buf,'PNG');raw=buf.getvalue()
            r=json.load(urlopen(Request(url+'/api/process',data=raw,headers={'Content-Type':'application/octet-stream'})))
            self.assertEqual(r['result']['status'],'unresolved')
            result=urlopen(Request(url+'/api/export',data=raw,headers={'X-Correction':json.dumps(r['result']['params'])})).read()
            self.assertEqual(Image.open(io.BytesIO(result)).size,(320,240))
        finally:srv.shutdown();thread.join();srv.server_close()

if __name__=='__main__':unittest.main()
