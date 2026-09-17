import unittest
import numpy as np
from PIL import Image
from api.watermarks import Detection,WatermarkCleaner,validated_boxes
class Detector:
    def __init__(self,marks):self.marks=marks
    def detect(self,image):return self.marks
class Painter:
    def __init__(self):self.calls=0
    def inpaint(self,image,mask):self.calls+=1;return Image.new('RGB',image.size,'red')
class CleanupTests(unittest.TestCase):
    def test_no_detection_does_not_inpaint_or_change_pixels(self):
        im=Image.fromarray(np.random.default_rng(1).integers(0,256,(200,300,3),dtype=np.uint8));paint=Painter()
        out,r=WatermarkCleaner(Detector([]),paint).clean(im)
        self.assertEqual(r['status'],'no_detection');self.assertEqual(paint.calls,0);np.testing.assert_array_equal(out,im)
    def test_only_mask_changes_and_size_is_preserved(self):
        im=Image.new('RGB',(300,200),'blue');paint=Painter()
        out,r=WatermarkCleaner(Detector([Detection((100,90,140,110),.9)]),paint).clean(im)
        a,b=np.asarray(im),np.asarray(out);mask=np.zeros((200,300),bool);x0,y0,x1,y1=r['regions'][0];mask[y0:y1,x0:x1]=True
        np.testing.assert_array_equal(a[~mask],b[~mask]);self.assertTrue(np.any(a[mask]!=b[mask]));self.assertEqual(im.size,out.size)
    def test_uncertain_large_or_many_regions_leave_image_untouched(self):
        boxes,status=validated_boxes([Detection((0,0,200,150),.9)],(300,200));self.assertEqual(status,'uncertain');self.assertFalse(boxes)
        marks=[Detection((i*40,10,i*40+10,20),.9) for i in range(6)]
        self.assertEqual(validated_boxes(marks,(300,200))[1],'uncertain')
    def test_invalid_low_confidence_and_duplicate_boxes(self):
        marks=[Detection((10,10,30,30),.1),Detection((float('nan'),0,10,10),.9),Detection((60,60,20,20),.9)]
        self.assertEqual(validated_boxes(marks,(300,200))[1],'no_detection')
        self.assertEqual(len(validated_boxes([Detection((10,10,30,30),.9)]*2,(300,200))[0]),1)
