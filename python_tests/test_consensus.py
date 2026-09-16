import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dist/python'))
import straighten as s

class ConsensusTests(unittest.TestCase):
    def fixture(self):
        w,h=900,600;p=dict(s.BASE,roll=.35,pitch=2.85);inverse=s.matrix(p).T;f=w*.75;lines=[]
        for x in [50,140,230,320,450,580,670,760,850]:
            target=np.column_stack((np.full(70,x),np.linspace(80,520,70)))
            rays=np.column_stack(((target-[w/2,h/2])/f,np.ones(70)))@inverse.T
            pts=rays[:,:2]/rays[:,2:]*f+[w/2,h/2]
            lines.append(dict(a=pts[0],b=pts[-1],points=pts,length=440,mid=x,slope=(pts[-1,0]-pts[0,0])/(pts[-1,1]-pts[0,1])))
        for x in [30,420,875]:
            ys=np.linspace(80,520,70);pts=np.column_stack((x-.08*(ys-300),ys))
            lines.append(dict(a=pts[0],b=pts[-1],points=pts,length=440,mid=x,slope=-.08))
        attempts=[(dict(status='corrected',params=dict(p),evidence={}),t) for t in (25,12,8)]
        return lines,attempts,w,h
    def test_agreed_pose_survives_non_upright_edges(self):
        ls,attempts,w,h=self.fixture();r=s.consensus_validation(ls,attempts,w,h)
        self.assertEqual(r['status'],'corrected');self.assertEqual(r['evidence']['rejectedEdges'],3)
        self.assertLess(r['evidence']['sharedScoreAfter'],r['evidence']['sharedScoreBefore']*.1)
    def test_disagreement_or_sparse_support_is_rejected(self):
        ls,a,w,h=self.fixture();a[-1][0]['params']['pitch']=12
        self.assertIsNone(s.consensus_validation(ls,a,w,h))
        self.assertIsNone(s.consensus_validation(ls[:3],a[:2],w,h))
    def test_no_fabricated_blank_consensus(self):
        self.assertIsNone(s.consensus_validation([],[],900,600))

if __name__=='__main__':unittest.main()
