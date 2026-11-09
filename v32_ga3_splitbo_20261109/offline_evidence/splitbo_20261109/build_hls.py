from pathlib import Path
import hashlib,json,subprocess,time
R=Path(__file__).resolve().parent;D=R/'design';B=Path('/home/mark/ga3_splitbo_20261109/hls/r1');E=R/'evidence';E.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert not B.exists();B.mkdir(parents=True)
for top,cosim in [('ct_reader',False),('native_split_chain',True)]:
 d=B/top;d.mkdir();adds=''.join(f'add_files {D}/{n} -cflags "-std=c++14 -I{D}"\n' for n in ['native_reader.cpp','native_reduce.cpp','native_chain.cpp'])
 text=f'''open_project {d}/project
set_top {top}
{adds}add_files -tb {D}/native_tb.cpp -cflags "-std=c++14 -I{D}"
open_solution solution1 -flow_target vitis
set_part xcve2802-vsvh1760-2MP-e-S
create_clock -period 3.2 -name default
csim_design -O
csynth_design
'''
 text+='cosim_design -rtl verilog -tool xsim -O -random_stall -enable_dataflow_profiling -trace_level none\n' if cosim else f'export_design -format xo -rtl verilog -output {d}/{top}.xo\n'
 text+='exit\n';(d/'build.tcl').write_text(text);start=time.monotonic();print('START_HLS',top,flush=True)
 with (d/'build.log').open('w') as log:subprocess.run(['vitis-run','--mode','hls','--tcl',d/'build.tcl'],cwd=d,stdout=log,stderr=subprocess.STDOUT,check=True)
 result=dict(status='PASS_CSIM_SYNTH_RANDOM_STALL_RTL' if cosim else 'PASS_CSIM_SYNTH_XO',build=str(d),source={p.name:sha(p) for p in D.iterdir()},seconds=time.monotonic()-start)
 if not cosim:result['xo_sha256']=sha(d/f'{top}.xo')
 (E/f'{top}.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],top,flush=True)
