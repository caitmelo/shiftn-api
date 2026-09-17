import base64
import io
import unittest
from PIL import Image
from fastapi.testclient import TestClient
from api.app import create_app
from api.watermarks import WatermarkCleaner,Detection
class Detector:
    def detect(self,image):return [Detection((80,80,100,95),.9)]
class Painter:
    def inpaint(self,image,mask):return Image.new('RGB',image.size,'red')
class ApiTests(unittest.TestCase):
    def raw(self):
        b=io.BytesIO();Image.new('RGB',(200,180),'blue').save(b,'PNG');return b.getvalue()
    def test_authentication_and_cross_origin(self):
        with TestClient(create_app(api_key='test-key')) as c:
            self.assertEqual(c.get('/runtime.json').status_code,401)
            self.assertEqual(c.get('/runtime.json',auth=('straightline','bad')).status_code,401)
            self.assertEqual(c.get('/runtime.json',auth=('straightline','test-key')).status_code,200)
            self.assertEqual(c.post('/api/process',auth=('straightline','test-key'),headers={'Origin':'https://other.example'}).status_code,403)
    def test_cleanup_export_reuses_output_and_delete_expires(self):
        with TestClient(create_app(cleaner=WatermarkCleaner(Detector(),Painter()),api_key='',local_only=True)) as c:
            r=c.post('/api/process',content=self.raw(),headers={'Content-Type':'application/octet-stream','X-Remove-Watermarks':'true'})
            self.assertEqual(r.status_code,200,r.text);result=r.json()['result'];self.assertEqual(result['status'],'cleaned');self.assertEqual(result['watermark']['removed'],1)
            url='/api/results/'+result['exportId'];first=c.get(url);second=c.get(url)
            self.assertEqual(first.content,second.content);self.assertEqual(Image.open(io.BytesIO(first.content)).size,(200,180))
            self.assertEqual(c.delete(url).status_code,204);self.assertEqual(c.get(url).status_code,410)
    def test_unavailable_models_are_explicit_not_silent(self):
        with TestClient(create_app(api_key='',local_only=True)) as c:
            self.assertFalse(c.get('/runtime.json').json()['watermarkRemoval'])
            self.assertEqual(c.post('/api/process',content=self.raw(),headers={'Content-Type':'application/octet-stream','X-Remove-Watermarks':'true'}).status_code,503)
            self.assertEqual(c.post('/api/process',content=b'bad',headers={'Content-Type':'application/octet-stream'}).status_code,400)
            self.assertEqual(c.post('/api/process',content=self.raw(),headers={'Content-Type':'text/plain'}).status_code,415)
    def test_no_unauthenticated_public_configuration(self):
        with self.assertRaises(RuntimeError):create_app(api_key='',local_only=False)
