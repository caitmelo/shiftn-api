import io
import sys
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dist'/'python'))
import straighten as s

class EngineTests(unittest.TestCase):
    def test_known_camera_rotation(self):
        w,h=500,700;p=dict(s.BASE,roll=-5.,pitch=12.)
        inverse=s.matrix(p).T;f=h*.75
        def back(x,y):
            v=inverse@np.array([(x-w/2)/f,(y-h/2)/f,1]);return v[:2]/v[2]*f+[w/2,h/2]
        lines=[]
        for x in [40,100,170,260,330,410,460]:
            a,b=back(x,100),back(x,600);lines.append(dict(a=a,b=b,length=float(np.linalg.norm(b-a)),mid=x,points=np.linspace(a,b,50)))
        result=s.solve(lines,w,h)
        self.assertEqual(result['status'],'corrected')
        self.assertAlmostEqual(result['params']['roll'],-5,places=4)
        self.assertAlmostEqual(result['params']['pitch'],12,places=4)
    def test_level_and_blank(self):
        self.assertEqual(s.analyse(Image.new('RGB',(320,240),'gray'))['status'],'unresolved')
        lines=[]
        for x in [20,80,140,200,260,300]:
            a,b=np.array([x,20]),np.array([x,220]);lines.append(dict(a=a,b=b,length=200,mid=x,points=np.linspace(a,b,50)))
        self.assertEqual(s.solve(lines,320,240)['status'],'unchanged')
    def test_original_resolution_and_identity(self):
        a=np.random.default_rng(1).integers(0,256,(120,180,3),dtype=np.uint8);im=Image.fromarray(a)
        original=s.png(im);unchanged=s.export_bytes(original,s.BASE)
        np.testing.assert_array_equal(np.asarray(Image.open(io.BytesIO(unchanged))),a)
        changed=Image.open(io.BytesIO(s.export_bytes(original,dict(s.BASE,roll=3,pitch=4))))
        self.assertEqual(changed.size,im.size)
    def test_invalid_file_and_params(self):
        with self.assertRaises(Exception):s.process_bytes(b'not a photograph')
        with self.assertRaises(ValueError):s.export_bytes(b'',dict(s.BASE,roll=float('nan')))
    def test_exif_orientation(self):
        im=Image.new('RGB',(100,150));exif=Image.Exif();exif[274]=6;buf=io.BytesIO();im.save(buf,'JPEG',exif=exif)
        self.assertEqual(s.decode(buf.getvalue()).size,(150,100))

if __name__=='__main__':unittest.main()
