"""Synthetic full grid with hard-linked records; never a real v32 result."""
from pathlib import Path
import json, os, struct, sys

def record(p, kind, l):
    qs=[(1<<59)-55-2*t for t in range(l)]
    words=8192*l*(3 if kind==2 else 32)
    with p.open('xb') as f:
        f.write(b'CKKSMAC1'+struct.pack('<10I2Q',1,kind,8192,l,16,3 if kind==2 else 2,1,64,0,0,words,0))
        for q in qs:
            mu=((1<<128)-1)//q; f.write(struct.pack('<3Q',q,mu&((1<<64)-1),mu>>64))
        if kind==2:
            for q in qs:
                a,b,c,d=q-1,q-2,q-3,q-4
                f.write(struct.pack('<3Q',16*a*c%q,16*(a*d+b*c)%q,16*b*d%q)*8192)
        else:
            for _ in range(16):
                for q in qs:
                    f.write(struct.pack('<2Q',q-(1 if kind==3 else 3),q-(2 if kind==3 else 4))*8192)

def main(dest,full_l=17,pilot=False):
    root=Path(dest);root.mkdir(parents=True)
    for l in sorted({min(16,full_l-t) for t in range(0,full_l,16)}):
        for k in (2,3,4):record(root/f'record_{k}_{l}.bin',k,l)
    rows=[]
    for ct in range(16):
        for g in range(3,-1,-1):
            for t in range(0,full_l,16):
                for c in ((0,122880) if pilot else range(0,131072,8192)):
                    l=min(16,full_l-t)
                    rows.append([len(rows),ct,g,t,c,8192,l,16,f'record_3_{l}.bin',f'record_4_{l}.bin',f'record_2_{l}.bin'])
    (root/'jobs.tsv').write_text('id\toutput_ct\tgroup\ttower_start\tcoefficient_start\tN\tL\tK\tA\tB\texpected\n'+''.join('\t'.join(map(str,r))+'\n' for r in rows),encoding='ascii',newline='\n')
    (root/'shape.json').write_text(json.dumps(dict(N=131072,L=full_l,K=16,output_ciphertexts=16,groups_per_output=4,jobs=len(rows),coefficient_windows=2 if pilot else 16)),encoding='ascii')
    print('SYNTHETIC_TEST_ONLY',root,len(rows))

if __name__=='__main__':main(sys.argv[1],int(sys.argv[2]) if len(sys.argv)>2 else 17,len(sys.argv)>3 and sys.argv[3]=='pilot')
