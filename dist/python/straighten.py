"""Straightline: Python/NumPy structural-edge estimation and Pillow rendering.

Runs unmodified in CPython or Pyodide. No JavaScript image-analysis fallback,
AI model, network calls, or filesystem persistence is required by this module.
"""
from __future__ import annotations
import io
import math
import warnings
import numpy as np
from PIL import Image, ImageOps

VERSION = 'python-1.1'
BASE = dict(roll=0., pitch=0., yaw=0., focal=.75)
MAX_PIXELS = 60_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def decode(raw):
    if len(raw) > 40 * 1024 * 1024:
        raise ValueError('This file exceeds 40 MB.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        im = Image.open(io.BytesIO(raw))
        if im.format not in ('JPEG', 'PNG', 'WEBP'):
            raise ValueError('Use JPEG, PNG or WebP.')
        w, h = im.size
        if w*h > MAX_PIXELS or max(w,h) > 20000 or min(w,h) < 80:
            raise ValueError('Use an image between 80 pixels per side and 60 megapixels (maximum side 20,000 pixels).')
        im = ImageOps.exif_transpose(im)
        if im.mode in ('RGBA', 'LA') or 'transparency' in im.info:
            rgba = im.convert('RGBA')
            rgb = Image.new('RGB', im.size, 'white')
            rgb.paste(rgba, mask=rgba.getchannel('A'))
            return rgb
        return im.convert('RGB')


def matrix(p):
    a,b,c = np.deg2rad([p.get('roll',0), p.get('pitch',0), p.get('yaw',0)])
    ca,sa,cb,sb,cc,sc = np.cos(a),np.sin(a),np.cos(b),np.sin(b),np.cos(c),np.sin(c)
    return np.array([[cc,0,sc],[0,1,0],[-sc,0,cc]]) @ np.array([[1,0,0],[0,cb,-sb],[0,sb,cb]]) @ np.array([[ca,-sa,0],[sa,ca,0],[0,0,1]])


def mesh_offset(x, y, p, w, h):
    anchors = p.get('mesh', [])
    if not anchors:
        return np.zeros_like(x, dtype=float)
    nx,ny=np.asarray(x)/w,np.asarray(y)/h
    out=np.zeros(np.broadcast_shapes(nx.shape,ny.shape));lx=-.5;ld=np.zeros_like(ny)
    for a in [*anchors,None]:
        rx=a['x'] if a else 1.5
        if a:
            t=np.clip(ny,a['low'],a['high']);c=a['coef'];rd=np.clip(c[0]+c[1]*t+c[2]*t*t,-.006,.006)
        else: rd=np.zeros_like(ny)
        t=np.clip((nx-lx)/(rx-lx),0,1);t=t*t*(3-2*t)
        out=np.where((nx>=lx)&(nx<=rx),w*(ld*(1-t)+rd*t),out)
        lx,ld=rx,rd
    return out


def project(points,p,w,h):
    pts=np.asarray(points,dtype=float);f=max(w,h)*p.get('focal',.75)
    v=np.concatenate(((pts-[w/2,h/2])/f,np.ones((*pts.shape[:-1],1))),axis=-1) @ matrix(p).T
    out=v[...,:2]/v[...,2:3]*f+[w/2,h/2]
    out[...,0]+=mesh_offset(out[...,0],out[...,1],p,w,h)
    return out


def detect(im, threshold):
    """Gradient-directed Hough proposals with continuous subpixel edge tracing."""
    gray=np.asarray(im.convert('RGB'),dtype=np.float32)@np.array([.299,.587,.114],dtype=np.float32)
    h,w=gray.shape;gx=np.zeros_like(gray);gy=np.zeros_like(gray)
    gx[:,1:-1]=gray[:,2:]-gray[:,:-2];gy[1:-1]=gray[2:]-gray[:-2]
    ys,xs=np.mgrid[2:h-2:2,2:w-2:2];mag=np.hypot(gx[ys,xs],gy[ys,xs]);keep=mag>threshold
    yy,xx=ys[keep],xs[keep]
    if len(xx)<20:return []
    angle=(np.rad2deg(np.arctan2(gy[yy,xx],gx[yy,xx]))+180)%180
    d=int(np.ceil(np.hypot(w,h)));cols=2*d+1;acc=np.zeros((180,cols),dtype=np.int32)
    theta=np.rint(angle).astype(int)
    for dt in range(-3,4):
        t=(theta+dt)%180;rad=np.deg2rad(t);rho=np.rint(xx*np.cos(rad)+yy*np.sin(rad)).astype(int)+d
        np.add.at(acc,(t,rho),1)
    tt,rr=np.nonzero(acc>=12);order=np.lexsort((rr,tt,-acc[tt,rr]))
    chosen=[];proposals=[]
    for k in order:
        t,r=int(tt[k]),int(rr[k]-d)
        if any((abs(t-a)<5 and abs(r-b)<10) or (abs(t-a)>175 and abs(r+b)<10) for a,b in chosen):continue
        chosen.append((t,r))
        if t<30 or t>150:
            cs,sn=np.cos(np.deg2rad(t)),np.sin(np.deg2rad(t));diff=np.abs(angle-t)
            mask=(np.abs(xx*cs+yy*sn-r)<2.5)&(np.minimum(diff,180-diff)<12)
            along=np.sort(-xx[mask]*sn+yy[mask]*cs)
            for run in np.split(along,np.flatnonzero(np.diff(along)>18)+1):
                if len(run)<9 or run[-1]-run[0]<min(w,h)*.12:continue
                a=np.array([r*cs-run[0]*sn,r*sn+run[0]*cs]);b=np.array([r*cs-run[-1]*sn,r*sn+run[-1]*cs])
                if a[1]>b[1]:a,b=b,a
                proposals.append((a,b))
        if len(chosen)>=90:break
    gradient=np.zeros_like(gray)
    gradient[2:-2,2:-2]=(gray[2:-2,4:]-gray[2:-2,:-4])*.25+(gray[3:-1,4:]-gray[3:-1,:-4]+gray[1:-3,4:]-gray[1:-3,:-4])*.125
    lines=[]
    for a,b in proposals:
        slope=(b[0]-a[0])/(b[1]-a[1]);points=[]
        for y in range(max(3,int(np.ceil(a[1]-h*.25))),min(h-3,int(b[1]+h*.25)),3):
            expected=a[0]+slope*(y-a[1]);xs=np.arange(max(3,round(expected)-7),min(w-3,round(expected)+8))
            if not len(xs):continue
            strength=np.abs(gradient[y,xs]);j=int(np.argmax(strength/(1+.08*np.abs(xs-expected))))
            if strength[j]<=3:continue
            x=xs[j];aa,bb,cc=np.abs(gradient[y,x-1:x+2]);den=aa-2*bb+cc
            off=np.clip(.5*(aa-cc)/den,-.5,.5) if den<-.01 else 0;points.append([x+off,y])
        if len(points)<12:continue
        pts=np.array(points);delta=np.diff(pts,axis=0)
        runs=np.split(pts,np.flatnonzero((delta[:,1]>12)|(np.abs(delta[:,0]-slope*delta[:,1])>3))+1);pts=max(runs,key=len)
        if len(pts)<12 or pts[-1,1]-pts[0,1]<h*.08:continue
        coef=np.polyfit(pts[:,1],pts[:,0],1);res=np.abs(pts[:,0]-np.polyval(coef,pts[:,1]))
        if np.quantile(res,.8)>3.5:continue
        middle=float(np.polyval(coef,h/2));slope=float(coef[0]);length=float(pts[-1,1]-pts[0,1])
        if any(abs(middle-l['mid'])<5 and abs(slope-l['slope'])<.03 for l in lines):continue
        a=np.array([np.polyval(coef,pts[0,1]),pts[0,1]]);b=np.array([np.polyval(coef,pts[-1,1]),pts[-1,1]])
        lines.append(dict(a=a,b=b,points=pts,length=length,mid=middle,slope=slope))
    return sorted(lines,key=lambda l:l['length'],reverse=True)[:55]


def fit(lines,w,h):
    f=max(w,h)*.75
    a=np.array([l['a'] for l in lines]);b=np.array([l['b'] for l in lines])
    a=np.column_stack(((a-[w/2,h/2])/f,np.ones(len(a))))
    b=np.column_stack(((b-[w/2,h/2])/f,np.ones(len(b))))
    normals=np.cross(a,b);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-9)
    _,_,vh=np.linalg.svd(normals,full_matrices=True);g=vh[-1]
    if g[1]<0:g=-g
    return dict(BASE,roll=float(np.rad2deg(np.arctan2(g[0],g[1]))),pitch=float(-np.rad2deg(np.arctan2(g[2],np.hypot(g[0],g[1])))))


def errors(lines,p,w,h):
    a=project(np.array([l['a'] for l in lines]),p,w,h);b=project(np.array([l['b'] for l in lines]),p,w,h)
    delta=b-a
    return np.rad2deg(np.arctan2(np.abs(delta[:,0]),np.abs(delta[:,1])))


def spread(lines,w):
    return float(np.ptp([(l['a'][0]+l['b'][0])/2 for l in lines])/w) if lines else 0.


def solve(lines,w,h):
    unresolved=dict(status='unresolved',params=dict(BASE),message='Could not find a reliable correction. The original is preserved.')
    if len(lines)<4 or spread(lines,w)<.25:return dict(unresolved,reason='insufficient-spatial-support')
    best=None;trials=0
    for i in range(len(lines)):
        for j in range(i+1,len(lines)):
            pair=[lines[i],lines[j]]
            if spread(pair,w)<.22:continue
            trials+=1
            p=fit(pair,w,h)
            if abs(p['roll'])>24 or abs(p['pitch'])>28:continue
            good=errors(lines,p,w,h)<1.2
            ls=[l for l,k in zip(lines,good) if k]
            score=sum(min(l['length'],h*.35) for l in ls)
            if len(ls)>=4 and spread(ls,w)>.28 and (best is None or score>best[0]):best=(score,ls)
            if trials>=180:break
        if trials>=180:break
    if best is None:return dict(unresolved,reason='no-consensus')
    ls=best[1];p=fit(ls,w,h)
    before=float(np.sqrt(np.mean(errors(ls,BASE,w,h)**2)));after=float(np.sqrt(np.mean(errors(ls,p,w,h)**2)))
    if len(ls)<len(lines)*.3:return dict(unresolved,reason='weak-consensus')
    ordered=sorted(ls,key=lambda l:l['mid']);halves=[ordered[::2],ordered[1::2]]
    if any(len(part)<2 or spread(part,w)<.18 for part in halves):return dict(unresolved,reason='unstable-support')
    p1,p2=[fit(part,w,h) for part in halves]
    if abs(p1['roll']-p2['roll'])>1.5 or abs(p1['pitch']-p2['pitch'])>7:return dict(unresolved,reason='unstable-fit')
    evidence=dict(lines=len(ls),before=before,after=after)
    if before<.7:return dict(status='unchanged',params=dict(BASE),message='Detected structural edges are close to upright. No correction applied.',evidence=evidence)
    if after>before*.8 or after>1.2 or abs(p['roll'])>24 or abs(p['pitch'])>28:return dict(unresolved,reason='insufficient-improvement')
    # Bounded local polynomial refinement, validated on alternating edge samples.
    anchors=[]
    for l in ls:
        if l['length']<h*.25:continue
        pts=project(l['points'],p,w,h);target=float(pts[:,0].mean()/w);ny=pts[:,1]/h;dx=target-pts[:,0]/w
        coef=np.polynomial.polynomial.polyfit(ny[::2],dx[::2],2)
        prediction=np.polynomial.polynomial.polyval(ny,coef)
        if np.max(np.abs(prediction))>.006 or np.sqrt(np.mean((prediction[1::2]-dx[1::2])**2))*w>1:continue
        anchors.append(dict(x=target,low=float(ny.min()),high=float(ny.max()),coef=coef.tolist()))
    anchors.sort(key=lambda a:a['x']);selected=[]
    for a in anchors:
        if not selected or a['x']-selected[-1]['x']>.06:selected.append(a)
    if len(selected)>=2 and selected[-1]['x']-selected[0]['x']>.25:
        candidate=dict(p,mesh=selected)
        ranges=lambda q:np.array([np.ptp(project(l['points'],q,w,h)[:,0]) for l in ls if l['length']>h*.25])
        old,new=ranges(p),ranges(candidate)
        if len(old) and new.max()<old.max()*.9 and np.all(new<old+.7):p=candidate
    return dict(status='corrected',params=p,message='Python corrected the camera tilt. Review the result for remaining edge deviations.',evidence=evidence)


def trace_refinement(lines,w,h):
    """Fit continuous tracks, with spatially held-out agreement and worst-edge checks."""
    lines=[l for l in lines if abs(l['slope'])<.08]
    if len(lines)<6 or spread(lines,w)<.3:return None
    def optimize(group):
        # Vectorize variable-length tracks, retaining their grouping for demeaning.
        pts=np.concatenate([l['points'] for l in group]);ids=np.concatenate([np.full(len(l['points']),i) for i,l in enumerate(group)])
        counts=np.bincount(ids);weights=np.array([l['length'] for l in group])
        def objective(p):
            x=project(pts,p,w,h)[:,0];means=np.bincount(ids,weights=x)/counts
            variance=np.bincount(ids,weights=(x-means[ids])**2)/counts
            return float(np.average(np.minimum(variance,36),weights=weights))
        p=dict(BASE);initial=objective(p);best=initial
        for step in (1,.3,.1,.03):
            for _ in range(30):
                change=None
                for key in ('roll','pitch'):
                    for sign in (-1,1):
                        q=dict(p);q[key]+=sign*step
                        if abs(q['roll'])>8 or abs(q['pitch'])>15:continue
                        value=objective(q)
                        if value<best-1e-8:best=value;change=q
                if change is None:break
                p=change
        return p,initial,best
    p,before,after=optimize(lines)
    if after>before*.75 or before<.2:return None
    ordered=sorted(lines,key=lambda l:l['mid']);halves=[ordered[::2],ordered[1::2]]
    if any(spread(part,w)<.2 for part in halves):return None
    p1,_,_=optimize(halves[0]);p2,_,_=optimize(halves[1])
    if abs(p1['roll']-p2['roll'])>1 or abs(p1['pitch']-p2['pitch'])>5:return None
    long=[l for l in lines if l['length']>h*.25]
    if long:
        old=np.array([np.ptp(project(l['points'],BASE,w,h)[:,0]) for l in long]);new=np.array([np.ptp(project(l['points'],p,w,h)[:,0]) for l in long])
        if new.max()>old.max()+.5 or np.any(new>old+1.5):return None
    return dict(status='corrected',params=p,message='Python refined the camera tilt using continuous structural edges. Review the result.',evidence=dict(traceRefinement=True,sharedScoreBefore=before,sharedScoreAfter=after))


def consensus_validation(lines, attempts, w, h):
    """Validate agreed camera poses on a fixed, distributed structural consensus.

    Roof edges and other non-uprights must not veto a pose solely by being long.
    This fallback requires repeated pose agreement, majority edge support, and
    improvement on both alternating spatial subsets. Thresholds are unchanged
    for the existing all-edge validation path.
    """
    poses=[r for r,t in attempts if t and r['status']=='corrected']
    if len(poses)<2 or len(lines)<6:return None
    for r in poses:
        p=r['params']
        if abs(p['roll']-poses[0]['params']['roll'])>1 or abs(p['pitch']-poses[0]['params']['pitch'])>5:return None
    masks=[errors(lines,{k:v for k,v in r['params'].items() if k!='mesh'},w,h)<1.2 for r in poses]
    support=np.sum(masks,axis=0)>=max(2,len(poses)-1)
    trusted=[l for l,ok in zip(lines,support) if ok]
    if len(trusted)<6 or len(trusted)<len(lines)*.6 or spread(trusted,w)<.3:return None
    if sum(l['length'] for l in trusted)<sum(l['length'] for l in lines)*.55:return None
    ordered=sorted(trusted,key=lambda l:l['mid']);parts=[ordered[::2],ordered[1::2]]
    if any(len(part)<3 or spread(part,w)<.2 for part in parts):return None
    def score(group,p):
        return float(np.average([min(float(np.var(project(l['points'],p,w,h)[:,0])),36) for l in group],weights=[l['length'] for l in group]))
    before=score(trusted,BASE);whole_before=score(lines,BASE);eligible=[]
    for r in poses:
        p=r['params'];after=score(trusted,p)
        if after>=before*.8 or score(lines,p)>whole_before*1.1:continue
        if any(score(part,p)>=score(part,BASE)*.9 for part in parts):continue
        long=[l for l in trusted if l['length']>h*.25]
        if not long:continue
        old=max(float(np.ptp(project(l['points'],BASE,w,h)[:,0])) for l in long)
        new=max(float(np.ptp(project(l['points'],p,w,h)[:,0])) for l in long)
        if new>old+.5:continue
        eligible.append((after,r))
    if not eligible:return None
    after,result=min(eligible,key=lambda x:x[0]);result=dict(result)
    result['evidence']=dict(result.get('evidence',{}),consensusValidation=True,structuralEdges=len(trusted),rejectedEdges=len(lines)-len(trusted),sharedScoreBefore=before,sharedScoreAfter=after)
    return result


def analyse(im):
    small=im.copy();small.thumbnail((900,900),Image.Resampling.LANCZOS);w,h=small.size
    attempts=[];all_lines=[]
    for threshold in (25,12,8):
        lines=detect(small,threshold);r=solve(lines,w,h);attempts.append((r,threshold))
        for l in lines:
            if not any(abs(l['mid']-x['mid'])<6 and abs(l['slope']-x['slope'])<.015 for x in all_lines):all_lines.append(l)
    all_lines=[l for l in all_lines if abs(l['slope'])<.1]
    def score(p):
        total=weight=0
        for l in all_lines:
            pts=project(l['points'],p,w,h);err=float(np.var(pts[:,0]));wt=l['length']
            total+=min(err,36)*wt;weight+=wt
        return total/max(weight,1)
    original=score(BASE);eligible=[]
    refined=trace_refinement(all_lines,w,h)
    if refined:attempts.append((refined,0))
    for r,t in attempts:
        if r['status']=='corrected':
            value=score(r['params'])
            if value<original*.9:eligible.append((value,r,t))
    if eligible:
        value,result,threshold=min(eligible,key=lambda x:x[0]);result=dict(result)
        result['evidence']=dict(result.get('evidence',{}),sharedScoreBefore=original,sharedScoreAfter=value,threshold=threshold)
    elif (consensus := consensus_validation(all_lines,attempts,w,h)) is not None:
        result=consensus
    else:
        flat=[r for r,t in attempts if r['status']=='unchanged']
        if len(flat)>=2:result=dict(flat[0])
        else:result=dict(status='unresolved',params=dict(BASE),message='Could not establish a consistent correction. The original is preserved.')
    result['evidence']=dict(result.get('evidence',{}),engine=VERSION,analysisPixelHash=__import__('hashlib').sha256(small.tobytes()).hexdigest(),numpyVersion=np.__version__,pillowVersion=Image.__version__,attempts=[dict(threshold=t,status=r['status'],reason=r.get('reason')) for r,t in attempts])
    return result


def mapping(w,h,p):
    inv=matrix(p).T;f=max(w,h)*p.get('focal',.75)
    def sample(x,y):
        x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float));u=x.copy()
        for _ in range(5):u=x-mesh_offset(u,y,p,w,h)
        v=np.stack(((u-w/2)/f,(y-h/2)/f,np.ones_like(u)),axis=-1)@inv.T
        return v[...,:2]/v[...,2:3]*f+[w/2,h/2],v[...,2]
    center=project([[w/2,h/2]],p,w,h)[0];ts=np.linspace(-1,1,65)
    boundary=np.concatenate((np.column_stack((ts,np.ones(65))),np.column_stack((ts,-np.ones(65))),np.column_stack((np.ones(65),ts)),np.column_stack((-np.ones(65),ts))))
    lo,hi=0.,1.5
    for _ in range(30):
        s=(lo+hi)/2;points,z=sample(center[0]+boundary[:,0]*w*s/2,center[1]+boundary[:,1]*h*s/2)
        if np.all((z>.15)&(points[:,0]>=2)&(points[:,0]<w-3)&(points[:,1]>=2)&(points[:,1]<h-3)):lo=s
        else:hi=s
    if lo*lo<.48:raise ValueError('The correction would crop too much of the photo.')
    return [center[0]-w*lo/2,center[1]-h*lo/2,center[0]+w*lo/2,center[1]+h*lo/2],sample


def render(im,p,preview=False):
    w,h=im.size
    if not any(abs(p.get(k,0))>1e-9 for k in ('roll','pitch','yaw')) and not p.get('mesh'):
        out=im.copy()
        if preview:out.thumbnail((1600,1600),Image.Resampling.LANCZOS)
        return out
    box,sample=mapping(w,h,p);x0,y0,x1,y1=box
    scale=min(1,1600/max(w,h)) if preview else 1
    ow,oh=round(w*scale),round(h*scale)
    # Tile the inverse map to bound memory. Bicubic interpolation samples original pixels once.
    src=np.asarray(im);out=np.empty((oh,ow,3),dtype=np.uint8)
    def cubic(t):return np.stack((-.5*t+t*t-.5*t*t*t,1-2.5*t*t+1.5*t*t*t,.5*t+2*t*t-1.5*t*t*t,-.5*t*t+.5*t*t*t))
    xs=x0+(np.arange(ow)+.5)*(x1-x0)/ow
    for row in range(0,oh,32):
        ys=y0+(np.arange(row,min(row+32,oh))+.5)*(y1-y0)/oh
        pts,_=sample(xs[None,:],ys[:,None]);sx=pts[...,0]-.5;sy=pts[...,1]-.5
        ix=np.floor(sx).astype(int);iy=np.floor(sy).astype(int);wx=cubic(sx-ix);wy=cubic(sy-iy)
        tile=np.zeros((*sx.shape,3),dtype=np.float64)
        for j in range(4):
            for i in range(4):tile+=src[np.clip(iy+j-1,0,h-1),np.clip(ix+i-1,0,w-1)]*(wx[i]*wy[j])[...,None]
        out[row:row+len(ys)]=np.clip(np.rint(tile),0,255).astype(np.uint8)
    return Image.fromarray(out)


def png(im):
    buf=io.BytesIO();im.save(buf,format='PNG');return buf.getvalue()


def process_bytes(raw):
    im=decode(raw);result=analyse(im)
    if result['status']=='corrected':
        try:mapping(*im.size,result['params'])
        except ValueError as e:result=dict(status='unresolved',params=dict(BASE),message=str(e)+' The original is preserved.',evidence=dict(engine=VERSION,reason='unsafe-crop'))
    preview=render(im,result['params'],preview=True)
    result['width'],result['height']=im.size
    return result,png(preview)


def export_bytes(raw,params):
    for key in ('roll','pitch','yaw','focal'):
        if not isinstance(params.get(key),(float,int)) or not math.isfinite(params[key]):raise ValueError('Invalid correction parameters.')
    if abs(params['roll'])>30 or abs(params['pitch'])>35 or abs(params['yaw'])>20 or not .2<=params['focal']<=2:raise ValueError('Correction outside supported range.')
    anchors=params.get('mesh',[])
    if not isinstance(anchors,list) or len(anchors)>55:raise ValueError('Invalid local correction.')
    previous=-.5
    for a in anchors:
        if not isinstance(a,dict) or len(a.get('coef',[]))!=3:raise ValueError('Invalid local correction.')
        values=[a.get('x'),a.get('low'),a.get('high'),*a['coef']]
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in values):raise ValueError('Invalid local correction.')
        if not previous<a['x']<1.5 or not -1<=a['low']<=a['high']<=2:raise ValueError('Invalid local correction.')
        previous=a['x']
    return png(render(decode(raw),params))
