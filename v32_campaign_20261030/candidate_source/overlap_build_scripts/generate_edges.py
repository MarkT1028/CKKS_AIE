from pathlib import Path
import json,random,sys
R=Path(__file__).resolve().parent;P=R/'board_files';sys.path.insert(0,str(P));import record_io as io
def main():
    parent=R/'build/edge_fixtures';parent.mkdir(exist_ok=True);n=128;l=3;k=16;q=[(1<<44)+1,(1<<59)-1,(1<<60)-1];rng=random.Random(20261029)
    for mode in ('zero','max','random'):
        out=parent/mode;(out/'chunks').mkdir(parents=True,exist_ok=True);data=[]
        for pair in range(k):
            for t in range(l):
                for j in range(n):
                    for c in range(4):data.append(0 if mode=='zero' else q[t]-1 if mode=='max' else rng.randrange(q[t]))
        expected=[]
        for t in range(l):
            for j in range(n):
                s=[0,0,0]
                for pair in range(k):
                    b=((pair*l+t)*n+j)*4;a0,a1,b0,b1=data[b:b+4]
                    s[0]=(s[0]+a0*b0)%q[t];s[1]=(s[1]+a0*b1+a1*b0)%q[t];s[2]=(s[2]+a1*b1)%q[t]
                expected.extend(s)
        if mode=='max':assert all(expected[(t*n+j)*3:(t*n+j+1)*3]==[16,32,16] for t in range(l) for j in range(n))
        io.write(out/'chunks/chunk_0_input.bin',1,n,l,k,q,data);io.write(out/'chunks/chunk_0_expected.bin',2,n,l,k,q,expected)
        (out/'shape.json').write_text(json.dumps(dict(N=n,L=l,K=k,chunks=1,moduli=q))+'\n',encoding='utf-8',newline='\n');(out/'chunks.tsv').write_text('id\ttower_start\tcoefficient_start\tN\tL\tK\nchunk_0\t0\t0\t128\t3\t16\n',encoding='utf-8',newline='\n')
        io.inspect_fixture(out)
    print('EDGE_FIXTURES_READY zero max random; three moduli up to 2^60-1')
if __name__=='__main__':main()
