from pathlib import Path
import hashlib,json,subprocess,time
R=Path(__file__).resolve().parent;W=R.parents[1];B=Path('/home/mark/v32_coreopt_20261029/models')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    B.mkdir(parents=True,exist_ok=False)
    args=['g++','-std=c++17','-O2','-Wno-unknown-pragmas','-DPERF_COMPACT=1','-I'+str(R/'design'),'-I/home/mark/AMDDesignTools/2025.2/Vitis/include',str(R/'design/test_reducer.cpp'),str(R/'design/ct_reader.cpp'),str(R/'design/reducer_forward.cpp'),'-l:libgmp.so.10','-pthread','-o',str(B/'test_reducer')]
    with (B/'compile.log').open('w') as f:subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,check=True)
    start=time.monotonic();cases=[]
    with (B/'synthetic.log').open('w') as f:subprocess.run([str(B/'test_reducer')],stdout=f,stderr=subprocess.STDOUT,check=True)
    print((B/'synthetic.log').read_text(),flush=True)
    fixture=W/'board_packages/v32_hs4_20261027/fixture/chunks'
    for i in range(16):
        output=B/f'chunk_{i}_output.bin';log=B/f'chunk_{i}.log'
        with log.open('w') as f:subprocess.run([str(B/'test_reducer'),str(fixture/f'chunk_{i}_input.bin'),str(fixture/f'chunk_{i}_expected.bin'),str(output)],stdout=f,stderr=subprocess.STDOUT,check=True)
        # Same complete output record, not a subset or hash-only numerical check.
        expected=fixture/f'chunk_{i}_expected.bin'
        assert output.read_bytes()==expected.read_bytes()
        cases.append(dict(chunk=i,output_sha256=sha(output),expected_sha256=sha(expected),bytes=output.stat().st_size))
        print('PASS_FULL_REAL_C_MODEL',i,flush=True)
    facts=dict(status='PASS_FORWARD_REDUCER_SYNTHETIC_AND_ALL_16_REAL_CHUNKS',cases=cases,output_words=131072*14*3,elapsed_seconds=time.monotonic()-start,board_performance='PENDING')
    (R/'evidence/full_models.json').write_text(json.dumps(facts,indent=2)+'\n')
if __name__=='__main__':main()
