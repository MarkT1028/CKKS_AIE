from pathlib import Path
import argparse,json,subprocess,hashlib,time
R=Path(__file__).resolve().parent;B=Path('/home/mark/v32_coreopt_20261029/hls')
def main():
    p=argparse.ArgumentParser();p.add_argument('unit',choices=['reducer_forward']);a=p.parse_args();out=B/a.unit;out.mkdir(parents=True,exist_ok=False)
    src=R/'design/reducer_forward.cpp'
    script=f'''open_project {out}/project
set_top ct_reduce_accum
add_files {src} -cflags "-std=c++14 -DPERF_COMPACT=1 -I{R}/design"
add_files -tb {R}/design/rtl_tb.cpp -cflags "-std=c++14 -DPERF_COMPACT=1 -I{R}/design"
open_solution solution1 -flow_target vitis
set_part xcve2802-vsvh1760-2MP-e-S
create_clock -period 3.2 -name default
csim_design -O
csynth_design
cosim_design -rtl verilog -tool xsim -O -random_stall -enable_dataflow_profiling -trace_level none
export_design -format xo -rtl verilog -output {out}/ct_reduce_accum.xo
close_project
exit
'''
    (out/'build.tcl').write_text(script);start=time.monotonic()
    with (out/'hls.log').open('w') as log:subprocess.run(['vitis-run','--mode','hls','--tcl',str(out/'build.tcl')],cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True)
    facts=dict(unit=a.unit,status='PASS_HLS_CSIM_SYNTH_RANDOM_STALL_COSIM_XO',source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),xo_sha256=hashlib.sha256((out/'ct_reduce_accum.xo').read_bytes()).hexdigest(),elapsed_seconds=time.monotonic()-start,build=str(out),board_performance='PENDING')
    (R/'evidence'/f'hls_{a.unit}.json').write_text(json.dumps(facts,indent=2)+'\n');print(json.dumps(facts,indent=2),flush=True)
if __name__=='__main__':main()
