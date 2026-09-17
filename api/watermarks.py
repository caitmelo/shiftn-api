"""Local detection + masked LaMa restoration. No remote inference or token billing.

Grounding DINO is a general-purpose detector, not a validated watermark classifier.
This integration is experimental; evaluate it on the customer's marks and negatives.
"""
from dataclasses import dataclass
from pathlib import Path
import math
import os
import numpy as np
from PIL import Image, ImageDraw

@dataclass(frozen=True)
class Detection:
    box: tuple
    confidence: float


def overlap(a,b):
    x=max(0,min(a[2],b[2])-max(a[0],b[0]));y=max(0,min(a[3],b[3])-max(a[1],b[1]))
    inter=x*y
    return inter/max((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-inter,1)


def validated_boxes(detections,size,threshold=.45):
    w,h=size;boxes=[]
    for d in sorted(detections,key=lambda d:d.confidence,reverse=True):
        if not math.isfinite(d.confidence) or d.confidence<threshold:continue
        if len(d.box)!=4 or not all(math.isfinite(v) for v in d.box):continue
        x0,y0,x1,y1=d.box
        if x1<=x0 or y1<=y0:continue
        box=(max(0,int(x0)-3),max(0,int(y0)-3),min(w,math.ceil(x1)+3),min(h,math.ceil(y1)+3))
        if box[2]-box[0]<3 or box[3]-box[1]<3:continue
        if any(overlap(box,b)>.5 for b in boxes):continue
        boxes.append(box)
    if len(boxes)>5:return [],'uncertain'
    mask=Image.new('L',size);draw=ImageDraw.Draw(mask)
    for x0,y0,x1,y1 in boxes:draw.rectangle((x0,y0,x1-1,y1-1),fill=255)
    if np.count_nonzero(np.asarray(mask))>w*h*.08:return [],'uncertain'
    return boxes,'detected' if boxes else 'no_detection'


class GroundingDetector:
    def __init__(self,path,device='cpu'):
        import torch
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        self.torch=torch;self.device=device
        self.processor=AutoProcessor.from_pretrained(str(path),local_files_only=True)
        self.model=AutoModelForZeroShotObjectDetection.from_pretrained(str(path),local_files_only=True,use_safetensors=True).to(device).eval()

    def detect(self,image):
        # Require agreement between watermark-specific descriptions. Do not query
        # generic text/signs/logos: those are legitimate photographed content.
        small=image.copy();small.thumbnail((1400,1400));groups=[]
        for text in ('a watermark.','an overlaid watermark.'):
            inputs=self.processor(images=small,text=text,return_tensors='pt').to(self.device)
            with self.torch.inference_mode():outputs=self.model(**inputs)
            result=self.processor.post_process_grounded_object_detection(outputs,inputs.input_ids,box_threshold=.45,text_threshold=.3,target_sizes=[small.size[::-1]])[0]
            sx,sy=image.width/small.width,image.height/small.height
            groups.append([Detection(tuple(float(v)*scale for v,scale in zip(box,(sx,sy,sx,sy))),float(score)) for box,score in zip(result['boxes'].cpu().tolist(),result['scores'].cpu().tolist())])
        return [d for d in groups[0] if any(overlap(d.box,e.box)>.5 for e in groups[1])]


class LamaInpainter:
    def __init__(self,path):
        import onnxruntime as ort
        options=ort.SessionOptions();options.intra_op_num_threads=int(os.getenv('INPAINT_THREADS','2'))
        self.session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])

    def inpaint(self,image,mask):
        # A context crop, not the whole photograph, is resized for this fixed-size model.
        size=image.size
        arr=np.asarray(image.resize((512,512),Image.Resampling.LANCZOS),dtype=np.float32).transpose(2,0,1)[None]/255
        m=(np.asarray(mask.resize((512,512),Image.Resampling.NEAREST))>0).astype(np.float32)[None,None]
        out=self.session.run(None,{'image':arr,'mask':m})[0]
        out=np.asarray(out)[0].transpose(1,2,0)
        # The pinned Carve export emits RGB values in [0,255].
        return Image.fromarray(np.uint8(np.clip(out,0,255))).resize(size,Image.Resampling.LANCZOS)


class WatermarkCleaner:
    def __init__(self,detector,inpainter):self.detector,self.inpainter=detector,inpainter
    def clean(self,image):
        boxes,status=validated_boxes(self.detector.detect(image),image.size)
        if not boxes:return image.copy(),{'status':status,'removed':0}
        out=image.copy();w,h=image.size
        for x0,y0,x1,y1 in boxes:
            pad=max(48,int(max(x1-x0,y1-y0)*.35))
            crop=(max(0,x0-pad),max(0,y0-pad),min(w,x1+pad),min(h,y1+pad))
            original=out.crop(crop);mask=Image.new('L',original.size)
            ImageDraw.Draw(mask).rectangle((x0-crop[0],y0-crop[1],x1-crop[0]-1,y1-crop[1]-1),fill=255)
            restored=self.inpainter.inpaint(original,mask).convert('RGB')
            if restored.size!=original.size:raise RuntimeError('Inpainting returned an invalid size.')
            # Exact original pixels outside the accepted mask, even if model changes them.
            out.paste(Image.composite(restored,original,mask),crop[:2])
        return out,{'status':'removed','removed':len(boxes),'regions':[list(b) for b in boxes],'model':'LaMa','detector':'Grounding DINO (experimental)'}


def load_cleaner(root):
    root=Path(root)
    return WatermarkCleaner(GroundingDetector(root/'detector',os.getenv('DETECTOR_DEVICE','cpu')),LamaInpainter(root/'inpainting/lama_fp32.onnx'))
