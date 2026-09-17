import io
import sys
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dist'/'python'))
import straighten as s

class HorizontalTests(unittest.TestCase):
    def lines(self, a=-.012, q=.16, count=10):
        w,h=900,600;f=w*.75;lines=[]
        for b in np.linspace(-.35,.35,count):
            x=np.linspace(-.5,.1,100);y=(a+q*b)*x+b
            lines.append(dict(points=np.column_stack((x,y))*f+[w/2,h/2]))
        return lines

    def test_recovers_horizontal_vanishing_direction(self):
        r=s.horizontal_fit(self.lines(),900,600,s.BASE)
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r['params']['horizontalSlope'],-.012,places=8)
        self.assertAlmostEqual(r['params']['horizontalPerspective'],.16,places=8)
        for line in self.lines():
            p=s.project(line['points'],r['params'],900,600)
            self.assertLess(np.ptp(p[:,1]),1e-8)
        vertical=s.project([[120,40],[120,560]],r['params'],900,600)
        self.assertAlmostEqual(vertical[0,0],vertical[1,0],places=8)

    def test_rejects_flat_sparse_and_conflicting_directions(self):
        self.assertIsNone(s.horizontal_fit(self.lines(0,0),900,600,s.BASE))
        self.assertIsNone(s.horizontal_fit(self.lines(count=3),900,600,s.BASE))
        self.assertIsNone(s.horizontal_fit(self.lines(-.02,.2)+self.lines(.02,-.2),900,600,s.BASE))

    def test_projective_inverse_and_full_resolution_export(self):
        p=dict(s.BASE,horizontalSlope=-.012,horizontalPerspective=.16)
        box,sample=s.mapping(900,600,p)
        points=np.array([[200.,200.],[400.,350.],[600.,450.]])
        mapped=s.project(points,p,900,600);back,_=sample(mapped[:,0],mapped[:,1])
        np.testing.assert_allclose(back,points,atol=1e-8)
        im=Image.fromarray(np.random.default_rng(2).integers(0,256,(120,180,3),dtype=np.uint8))
        raw=s.png(im);out=Image.open(io.BytesIO(s.export_bytes(raw,p)))
        self.assertEqual(out.size,im.size)
        self.assertFalse(np.array_equal(np.asarray(out),np.asarray(im)))

    def test_invalid_horizontal_parameters(self):
        for key,value in [('horizontalSlope',float('nan')),('horizontalPerspective',.8),('horizontalPerspective','0.1')]:
            with self.assertRaises(ValueError):s.export_bytes(b'',dict(s.BASE,**{key:value}))

if __name__=='__main__':unittest.main()
