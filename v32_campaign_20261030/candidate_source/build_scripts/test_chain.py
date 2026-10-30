"""Feed actual cycle-simulator AIE outputs into reducer C and random-stall RTL."""
from pathlib import Path
import hashlib,importlib.util,json,struct,subprocess,time
R=Path(__file__).resolve().parent;W=R.parents[1];B=Path('/home/mark/v32_coreopt_20261029/chain')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    facts=json.loads((R/'evidence/aie_static_real.json').read_text());assert facts['status']=='PASS_ACTUAL_AIE_X86_AND_CYCLE_SIM'
    B.mkdir(parents=True,exist_ok=False);inputs=[]
    for lane,chunk in ((0,0),(1,15)):
        original=Path(facts['build'])/f'hw/aiesimulator_output/data/partials{lane}.txt'
        numbers=[]
        for line in original.read_text().splitlines():
            if line and line[0].isdigit():numbers.extend(map(int,line.split()))
        assert len(numbers)==401408 and all(0<=x<=0xffffffff for x in numbers)
        with (B/f'partials{lane}.txt').open('w') as f:
            for j in range(0,len(numbers),4):f.write(' '.join(map(str,numbers[j:j+4]))+'\n')
        golden=W/f'board_packages/v32_hs4_20261027/fixture/chunks/chunk_{chunk}_expected.bin';raw=golden.read_bytes()
        header=list(struct.unpack_from('<10I',raw,8));assert header[2:5]==[8192,14,16]
        params=raw[64:64+24*14];payload=struct.unpack_from('<'+str(8192*14*3)+'Q',raw,64+24*14)
        start=0 if lane==0 else 8192-64
        expected=[v for t in range(14) for v in payload[(t*8192+start)*3:(t*8192+start+64)*3]]
        header[2]=64
        (B/f'expected{lane}.bin').write_bytes(raw[:8]+struct.pack('<10I',*header)+struct.pack('<QQ',len(expected),0)+params+struct.pack('<'+str(len(expected))+'Q',*expected))
        inputs.append(dict(lane=lane,original_AIE_output_sha256=sha(original),canonical_partials_sha256=sha(B/f'partials{lane}.txt'),golden_chunk=chunk,coefficient_start=start,expected_sha256=sha(B/f'expected{lane}.bin')))
    tb='''#include "record_io.hpp"
#include <sstream>
int main(){try{
  const std::string root="'''+str(B)+'''/";
  for(unsigned lane=0;lane<2;++lane){
    auto expected=read_record(root+"expected"+std::to_string(lane)+".bin");
    param_t params[MAX_L]={};for(unsigned t=0;t<expected.l;++t)params[t]=expected.params[t];
    hls::stream<axis_t> partials;std::ifstream f(root+"partials"+std::to_string(lane)+".txt");check(bool(f),"partials input");
    unsigned beats=0;uint64_t word;
    while(f>>word){axis_t beat=word;check(word<=0xffffffffULL,"lane0 overflow");for(unsigned c=1;c<4;++c){check(bool(f>>word)&&word<=0xffffffffULL,"truncated beat");beat.range(32*c+31,32*c)=uint32_t(word);}partials.write(beat);++beats;}
    check(beats==896*112,"beat count");std::vector<word_t> output(393216,word_t(-1));
    check(ct_reduce_accum(partials,output.data(),params,64,14,16)==OK,"RTL status");check(partials.empty(),"undrained AIE data");
    for(unsigned i=0;i<expected.words.size();++i)check(output[i]==expected.words[i],"AIE->RTL full residue mismatch");
    for(unsigned i=expected.words.size();i<output.size();++i)check(output[i]==word_t(-1),"RTL wrote beyond exact result");
    std::cout<<"PASS ACTUAL_AIE_TO_REDUCER_RTL lane="<<lane<<" beats="<<beats<<" verified_words="<<expected.words.size()<<std::endl;
  }return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<std::endl;return 1;}}
'''
    (B/'chain_tb.cpp').write_text(tb)
    tcl=f'''open_project {B}/project
set_top ct_reduce_accum
add_files {R}/design/reducer_forward.cpp -cflags "-std=c++14 -DPERF_COMPACT=1 -I{R}/design"
add_files -tb {B}/chain_tb.cpp -cflags "-std=c++14 -DPERF_COMPACT=1 -I{R}/design"
open_solution solution1 -flow_target vitis
set_part xcve2802-vsvh1760-2MP-e-S
create_clock -period 3.2 -name default
csim_design -O
csynth_design
cosim_design -rtl verilog -tool xsim -O -random_stall -enable_dataflow_profiling -trace_level none
close_project
exit
'''
    (B/'chain.tcl').write_text(tcl);start=time.monotonic()
    with (B/'chain.log').open('w') as f:subprocess.run(['vitis-run','--mode','hls','--tcl',str(B/'chain.tcl')],cwd=B,stdout=f,stderr=subprocess.STDOUT,check=True)
    rpt=B/'project/solution1/sim/report/ct_reduce_accum_cosim.rpt';assert 'Pass' in rpt.read_text()
    result=dict(status='PASS_ACTUAL_AIE_OUTPUT_TO_NEW_REDUCER_CSIM_AND_RANDOM_STALL_RTL',inputs=inputs,source_sha256=sha(R/'design/reducer_forward.cpp'),AIE_source_sha256=facts['source_sha256'],lanes=2,frames_each=896,beats_each=100352,verified_words_each=2688,all_14_real_towers=True,all_16_real_ciphertext_pairs=True,full_original_ring=False,scope='Actual cycle-simulator AIE output consumed by cycle-accurate reducer RTL with randomized stalls and exact original golden endpoint residues; not concurrent whole-system co-simulation and not board performance',elapsed_seconds=time.monotonic()-start)
    (R/'evidence/chain_rtl.json').write_text(json.dumps(result,indent=2)+'\n')
    import shutil
    shutil.copy2(rpt,R/'evidence/chain_rtl_cosim.rpt');shutil.copy2(B/'chain_tb.cpp',R/'evidence/chain_tb.cpp')
    print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
